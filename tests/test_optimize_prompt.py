from cfet_tcad.optimize.llm_provider import RoundRecord
from cfet_tcad.optimize.objective import ObjectiveSpec, ObjectiveTerm
from cfet_tcad.optimize.prompt import RESPONSE_JSON_SCHEMA, build_round_prompt
from cfet_tcad.optimize.schema import FIELD_BOUNDS

SPEC = ObjectiveSpec(terms=[
    ObjectiveTerm(metric="ion_ioff_ratio", direction="maximize"),
    ObjectiveTerm(metric="ss_mv_per_dec", direction="minimize",
                 constraint=("<", 75.0)),
])


def test_round1_prompt_has_no_history_and_lists_objective():
    system, user, schema = build_round_prompt(
        objective=SPEC, base_values={"device.l_gate_nm": 15.0},
        history=[], best_so_far=None, n_candidates=4)
    assert "maximize ion_ioff_ratio" in user
    assert "ss_mv_per_dec < 75.0" in user
    assert "round 1" in user
    assert "Propose 4 new candidate" in user
    assert schema is RESPONSE_JSON_SCHEMA
    assert "structured JSON" in system


def test_prompt_lists_all_tunable_bounds_with_current_value():
    _, user, _ = build_round_prompt(
        objective=SPEC, base_values={"device.l_gate_nm": 15.0},
        history=[], best_so_far=None, n_candidates=2)
    for path in FIELD_BOUNDS:
        assert path in user
    assert "current=15.0" in user


def test_prompt_includes_history_and_best_so_far():
    history = [
        RoundRecord(overrides={"device.l_gate_nm": 12.0}, status="ok",
                   fom={"ion_ioff_ratio": 1e4}, score=0.3),
        RoundRecord(overrides={"device.l_gate_nm": 999.0},
                   status="rejected: l_gate_nm must be <= 50.0"),
    ]
    best = history[0]
    _, user, _ = build_round_prompt(
        objective=SPEC, base_values={"device.l_gate_nm": 15.0},
        history=history, best_so_far=best, n_candidates=2)
    assert "rejected: l_gate_nm must be <= 50.0" in user
    assert "Best result so far" in user


def test_repair_context_asks_for_replacements_only():
    _, user, _ = build_round_prompt(
        objective=SPEC, base_values={"device.l_gate_nm": 15.0},
        history=[], best_so_far=None, n_candidates=4,
        repair_context="candidate 2: device.t_ox_nm=10.0 rejected"
                       " (must be <= 3.0)")
    assert "Repair needed" in user
    assert "must be <= 3.0" in user
    assert "replacement candidates ONLY" in user
    # a repair round doesn't re-ask for a fresh full batch
    assert "Propose 4 new candidate" not in user
