"""Round-loop controller for the LLM device-parameter optimizer.

Each round: ask the LLM (on its own QThread, see ``llm_worker.py``) for N
candidate parameter sets; validate every candidate against the same
dataclass validation the CLI/GUI already enforce (``workflow.config``)
before spawning anything; run the valid candidates through a dedicated
:class:`~gui.run_queue.RunQueue` (one solver subprocess per candidate,
the same mechanism a manual per-row "Run" already uses); fold the
results back into the LLM's next-round context.  Everything here is
driven by Qt signals -- no method blocks the GUI thread.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, QThread, QTimer, Signal

from ..gui.experiment_table import ExperimentModel
from ..gui.run_queue import RunQueue
from ..workflow.config import (
    apply_overrides,
    build_config,
    check_sim_structure,
    resolve_external_mesh,
)
from ..workflow.sweep import flatten_fom
from .llm_provider import LLMProvider, RoundRecord
from .llm_worker import LLMWorker
from .objective import ObjectiveSpec, ObjectiveTracker
from .schema import FIELD_BOUNDS

#: seconds to wait between retries of a failed (retryable) LLM call
_RETRY_BACKOFF_S = (1, 3, 9)


@dataclass
class OptimizeSpec:
    base_config: Path
    objective: ObjectiveSpec
    n_candidates: int = 4
    max_rounds: int = 8
    max_repairs_per_round: int = 2
    max_validation_failed_rounds: int = 3
    #: total elapsed budget across the whole run, checked between rounds
    #: only (never interrupts a round already in flight); None = unlimited
    total_wall_clock_budget_s: float | None = 3600.0
    max_parallel: int = 4
    max_retries: int = 3

    def __post_init__(self):
        self.base_config = Path(self.base_config)
        if self.n_candidates < 1:
            raise ValueError("n_candidates must be >= 1")
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")
        if self.max_repairs_per_round < 0:
            raise ValueError("max_repairs_per_round must be >= 0")
        if self.max_validation_failed_rounds < 1:
            raise ValueError("max_validation_failed_rounds must be >= 1")
        if self.max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")


def _get_dotted(cfg, path: str):
    section, name = path.split(".", 1)
    return getattr(getattr(cfg, section), name)


class Orchestrator(QObject):
    #: 1-based round index about to run (never fired again for a
    #: within-round repair request)
    round_started = Signal(int)
    #: 1-based round index whose candidates have all finished
    round_completed = Signal(int)
    #: a candidate Experiment was just registered (add()'d to self.model)
    candidate_added = Signal(object)
    #: terminal event: "max_rounds" | "stopped" | "budget" |
    #: "validation_failed" | "error: <message>"
    finished = Signal(str)
    #: human-readable progress text for a status bar / log panel
    status_message = Signal(str)

    #: internal - request the LLMWorker (on its own QThread) to call
    #: provider.propose(**kwargs).  Never call LLMWorker.run_propose
    #: directly: emitting this signal is what marshals the call onto the
    #: worker thread via Qt's auto queued-connection.
    _request_propose = Signal(object)

    def __init__(self, spec: OptimizeSpec, provider: LLMProvider,
                out_dir: Path, parent=None, model_factory=None):
        super().__init__(parent)
        self.spec = spec
        self.provider = provider
        self.out_dir = Path(out_dir)

        # a dedicated queue/model, independent of any MainWindow.queue:
        # its own max_parallel, and shutdown() here never touches
        # experiments the user queued manually elsewhere.  model_factory
        # lets the GUI substitute a model subclass (e.g. one that adds a
        # Score column) without this module importing anything from gui.
        # optimize_dialog.py -- the factory receives this Orchestrator.
        self.model = (model_factory or
                     (lambda orch: ExperimentModel(parent=orch)))(self)
        self.queue = RunQueue(self.model, max_parallel=spec.max_parallel,
                              parent=self)
        self.queue.idle.connect(self._on_queue_idle)

        self.tracker = ObjectiveTracker(spec.objective)
        self.history: list[RoundRecord] = []
        self.best: RoundRecord | None = None
        #: Experiment -> score, for a GUI results table's Score column
        #: (kept off the shared Experiment dataclass; RoundRecord stays
        #: PySide6-free so optimize.* keeps importing without the [gui]
        #: extra -- this dict is how the two get reassociated)
        self.exp_scores: dict = {}
        self._exp_by_record: dict = {}  # RoundRecord -> Experiment
        self.round_index = 0

        self._base_raw = yaml.safe_load(
            spec.base_config.read_text(encoding="utf-8")) or {}
        base_cfg = build_config(self._base_raw)
        #: every FIELD_BOUNDS key's value in the base config, shown to the
        #: LLM as each parameter's starting point
        self.base_values = {path: _get_dotted(base_cfg, path)
                            for path in FIELD_BOUNDS}

        self._repairs_left = 0
        self._round_invalid: list = []  # (CandidateProposal, reason) this round
        self._retry_count = 0
        self._validation_failed_rounds = 0
        self._pending: dict = {}  # Experiment -> CandidateProposal
        self._last_kwargs: dict | None = None
        self._start_time: float | None = None
        self._running = False
        self._stopping = False

        self._thread = QThread(self)
        self._worker = LLMWorker(provider)
        self._worker.moveToThread(self._thread)
        self._request_propose.connect(self._worker.run_propose)
        self._worker.proposal_ready.connect(self._on_proposal_ready)
        self._worker.proposal_failed.connect(self._on_proposal_failed)
        self._thread.start()

    # --- lifecycle -----------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def best_experiment(self):
        """The gui.experiment_table.Experiment behind self.best, or None
        (e.g. before any candidate has finished)."""
        if self.best is None:
            return None
        return self._exp_by_record.get(self.best)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stopping = False
        self._start_time = time.monotonic()
        self.round_index = 0
        self._begin_round()

    def stop(self, reason: str = "stopped") -> None:
        """User- or window-close-triggered stop.  Safe to call more than
        once and safe to call after the run has already finished."""
        self._finish(reason)

    def _finish(self, reason: str) -> None:
        if not self._running:
            return
        self._running = False
        self._stopping = True
        # the LLM thread cannot forcibly cancel an in-flight HTTP call;
        # quit()+wait() stops it once the current call returns, and
        # _stopping makes any late proposal_ready/proposal_failed a no-op
        self._thread.quit()
        self._thread.wait(5000)
        self.queue.shutdown()
        self.finished.emit(reason)

    # --- round loop ------------------------------------------------------

    def _begin_round(self, repair_context: str | None = None) -> None:
        if self._stopping:
            return
        if repair_context is None:
            self.round_index += 1
            self._repairs_left = self.spec.max_repairs_per_round
            self._round_invalid = []
            if self.round_index > self.spec.max_rounds:
                self._finish("max_rounds")
                return
            budget = self.spec.total_wall_clock_budget_s
            if (budget is not None and self._start_time is not None
                    and (time.monotonic() - self._start_time) > budget):
                self._finish("budget")
                return
            self.round_started.emit(self.round_index)

        self._retry_count = 0
        what = ("repair candidate(s)" if repair_context
               else f"{self.spec.n_candidates} candidate(s)")
        self.status_message.emit(
            f"round {self.round_index}: requesting {what} from the LLM...")
        kwargs = dict(
            objective=self.spec.objective, base_values=self.base_values,
            history=list(self.history), best_so_far=self.best,
            n_candidates=self.spec.n_candidates,
            repair_context=repair_context)
        self._last_kwargs = kwargs
        self._request_propose.emit(kwargs)

    def _validate_candidate(self, proposal) -> str | None:
        """Pure-Python pre-check (no DEVSIM/gmsh): reject before ever
        spawning a solver subprocess for this candidate.

        Two layers: FIELD_BOUNDS min/max is the optimizer's own search-
        space contract (build_config has no notion of it -- most of its
        checks are just "> 0"), then build_config()/check_sim_structure()
        catch everything else (cross-field constraints, unit sanity,
        sim-type/structure mismatches)."""
        unknown = sorted(k for k in proposal.overrides if k not in FIELD_BOUNDS)
        if unknown:
            return f"unknown/non-tunable parameter(s): {unknown}"
        for key, value in proposal.overrides.items():
            bounds = FIELD_BOUNDS[key]
            try:
                value = float(value)
            except (TypeError, ValueError):
                return f"{key}={value!r} is not numeric"
            if not (bounds["min"] <= value <= bounds["max"]):
                return (f"{key}={value} is outside [{bounds['min']}, "
                       f"{bounds['max']}]")
        try:
            raw = apply_overrides(self._base_raw, proposal.overrides)
            resolve_external_mesh(raw, self.spec.base_config.parent)
            cfg = build_config(raw)
            check_sim_structure(cfg)
        except ValueError as exc:
            return str(exc)
        return None

    def _on_proposal_ready(self, proposals: list) -> None:
        if self._stopping:
            return
        valid, invalid = [], []
        for p in proposals:
            reason = self._validate_candidate(p)
            if reason is None:
                valid.append(p)
            else:
                invalid.append((p, reason))
        valid = valid[: self.spec.n_candidates]
        # accumulate across repair attempts -- a candidate rejected on the
        # *first* pass must still be recorded even though the round only
        # concludes (and writes to history) after a later repair succeeds
        self._round_invalid.extend(invalid)

        if invalid and self._repairs_left > 0:
            self._repairs_left -= 1
            context = "\n".join(
                f"- overrides={p.overrides!r} rejected: {reason}"
                for p, reason in invalid)
            self._begin_round(repair_context=context)
            return

        # repair budget exhausted (or nothing left to repair): every
        # invalid candidate seen this round (across all repair attempts)
        # is now permanently rejected -- record it once, so the next
        # round's history shows the LLM its own mistake
        for p, reason in self._round_invalid:
            self.history.append(RoundRecord(
                overrides=p.overrides, status=f"rejected: {reason}"))

        if not valid:
            self._validation_failed_rounds += 1
            if (self._validation_failed_rounds
                    >= self.spec.max_validation_failed_rounds):
                self._finish("validation_failed")
                return
            self._begin_round()  # try a fresh round from scratch
            return

        self._launch_round(valid)

    def _on_proposal_failed(self, message: str, retryable: bool) -> None:
        if self._stopping:
            return
        if not retryable or self._retry_count >= self.spec.max_retries:
            self._finish(f"error: {message}")
            return
        self._retry_count += 1
        delay_s = _RETRY_BACKOFF_S[
            min(self._retry_count - 1, len(_RETRY_BACKOFF_S) - 1)]
        self.status_message.emit(
            f"LLM call failed ({message}); retrying in {delay_s}s "
            f"(attempt {self._retry_count}/{self.spec.max_retries})...")
        QTimer.singleShot(
            delay_s * 1000,
            lambda: self._request_propose.emit(self._last_kwargs))

    def _launch_round(self, candidates: list) -> None:
        round_dir = self.out_dir / f"round{self.round_index:02d}"
        self._pending = {}
        for i, cand in enumerate(candidates):
            out = round_dir / f"c{i:02d}"
            exp = self.queue.make_experiment(
                f"r{self.round_index}c{i}", self.spec.base_config, out,
                overrides=cand.overrides, base_config=self.spec.base_config)
            self._pending[exp] = cand
            self.queue.add(exp)
            self.candidate_added.emit(exp)
            # start() this one experiment, NOT queue.run_all(): run_all()
            # would also re-launch any earlier round's *failed* rows still
            # sitting in the (shared, whole-run) model
            self.queue.start(exp)
        self.status_message.emit(
            f"round {self.round_index}: running {len(candidates)} "
            f"candidate(s)...")

    def _on_queue_idle(self) -> None:
        if self._stopping or not self._pending:
            return
        pending, self._pending = self._pending, {}
        for exp, cand in pending.items():
            flat_fom: dict = {}
            if exp.status == "done":
                fom_path = exp.out_dir / "fom.json"
                if fom_path.exists():
                    flat_fom = flatten_fom(
                        json.loads(fom_path.read_text(encoding="utf-8")))
                self.tracker.observe(flat_fom)
            record = RoundRecord(overrides=cand.overrides,
                                 status=exp.status, fom=flat_fom)
            self.history.append(record)
            self._exp_by_record[record] = exp

        # re-score every "done" record against the now-current tracker
        # ranges, not just this round's: normalization ranges only grow
        # over a run, so a scalar computed earlier under a narrower range
        # is not comparable to one computed later (a fresh max always
        # self-normalizes to 1.0, which would otherwise tie with -- and
        # lose to strict '>' against -- an earlier, worse max).  Rescoring
        # the whole history is O(rounds x candidates), trivially cheap.
        self.best = None
        for record in self.history:
            if record.status != "done":
                continue
            record.score = self.tracker.score(record.fom).scalar
            if self.best is None or record.score > self.best.score:
                self.best = record
            exp = self._exp_by_record.get(record)
            if exp is not None:
                self.exp_scores[exp] = record.score

        self.round_completed.emit(self.round_index)
        self._begin_round()
