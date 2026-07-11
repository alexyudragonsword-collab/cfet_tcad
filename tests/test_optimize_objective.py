import math

import pytest

from cfet_tcad.optimize.objective import (
    ObjectiveSpec,
    ObjectiveTerm,
    ObjectiveTracker,
    extract_metric,
)


def test_objective_term_validates_direction_and_constraint():
    with pytest.raises(ValueError, match="direction"):
        ObjectiveTerm(metric="ion_a", direction="up")
    with pytest.raises(ValueError, match="constraint op"):
        ObjectiveTerm(metric="ion_a", direction="maximize",
                     constraint=("!=", 1.0))
    with pytest.raises(ValueError, match="weight"):
        ObjectiveTerm(metric="ion_a", direction="maximize", weight=0.0)


def test_objective_spec_requires_at_least_one_term():
    with pytest.raises(ValueError):
        ObjectiveSpec(terms=[])


def test_extract_metric_exact_and_suffix_fallback():
    flat = {"ion_ioff_ratio": 1e5, "ss_mv_per_dec": 74.0}
    assert extract_metric(flat, "ion_ioff_ratio") == 1e5

    # CFET-style nested/flattened keys: suffix match, prefers the
    # lexicographically-last matching key (same heuristic as
    # workflow.sweep._pick_metric's saturation-curve preference)
    cfet_flat = {"nFET.ss_mv_per_dec": 74.0, "pFET.ss_mv_per_dec": 76.0}
    assert extract_metric(cfet_flat, "ss_mv_per_dec") == 76.0

    assert extract_metric(flat, "does_not_exist") is None
    assert extract_metric({"x": "not_numeric"}, "x") is None


def test_tracker_score_normalizes_across_observed_candidates():
    spec = ObjectiveSpec(terms=[
        ObjectiveTerm(metric="ion_ioff_ratio", direction="maximize"),
        ObjectiveTerm(metric="ss_mv_per_dec", direction="minimize"),
    ])
    tracker = ObjectiveTracker(spec)
    a = {"ion_ioff_ratio": 1e4, "ss_mv_per_dec": 90.0}
    b = {"ion_ioff_ratio": 1e6, "ss_mv_per_dec": 65.0}
    for fom in (a, b):
        tracker.observe(fom)

    score_a = tracker.score(a)
    score_b = tracker.score(b)
    # b is strictly better on both maximize and minimize terms
    assert score_b.scalar > score_a.scalar
    assert score_a.raw["ion_ioff_ratio"] == 1e4
    assert not score_a.violations


def test_tracker_single_observation_normalizes_to_midpoint():
    spec = ObjectiveSpec(terms=[
        ObjectiveTerm(metric="ion_a", direction="maximize")])
    tracker = ObjectiveTracker(spec)
    fom = {"ion_a": 1e-5}
    tracker.observe(fom)
    result = tracker.score(fom)
    assert result.scalar == pytest.approx(0.5)


def test_constraint_violation_penalizes_but_stays_finite_and_ranked():
    spec = ObjectiveSpec(terms=[
        ObjectiveTerm(metric="ss_mv_per_dec", direction="minimize",
                      constraint=("<", 75.0)),
    ])
    tracker = ObjectiveTracker(spec)
    close = {"ss_mv_per_dec": 76.0}   # barely violates
    far = {"ss_mv_per_dec": 150.0}    # badly violates
    ok = {"ss_mv_per_dec": 70.0}      # satisfies
    for fom in (close, far, ok):
        tracker.observe(fom)

    r_close, r_far, r_ok = (tracker.score(f) for f in (close, far, ok))
    assert math.isfinite(r_close.scalar) and math.isfinite(r_far.scalar)
    assert r_ok.scalar > r_close.scalar > r_far.scalar
    assert r_close.violations and r_far.violations
    assert not r_ok.violations


def test_missing_metric_is_penalized_not_crashing():
    spec = ObjectiveSpec(terms=[
        ObjectiveTerm(metric="does_not_exist", direction="maximize")])
    tracker = ObjectiveTracker(spec)
    result = tracker.score({"unrelated": 1.0})
    assert math.isfinite(result.scalar)
    assert result.raw["does_not_exist"] is None
    assert result.violations
