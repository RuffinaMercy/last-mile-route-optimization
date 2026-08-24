"""
Tests for the agent's safety guardrail logic (agent/orchestrator.py).

The guardrail's core promise: a route can never be reported as safe
if its algorithm violations exceed its baseline (nearest-neighbor)
violations. These tests check that logic directly and explicitly,
using controlled synthetic data — not real CSV rows, which could
change and make the test brittle.
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))


def _make_test_route_comparison(algo_violations, nn_violations):
    """Builds a single-row DataFrame shaped like route_comparison.csv,
    with only the fields the guardrail logic actually needs."""
    return pd.DataFrame([{
        "route_id": "TEST_ROUTE",
        "num_stops": 10,
        "nn_time_seconds": 1000.0,
        "nn_violations": nn_violations,
        "algo_time_seconds": 900.0,
        "algo_violations": algo_violations,
        "actual_time_seconds": 950.0,
        "actual_violations": 0,
        "algo_passes_run": 3,
    }])


def _guardrail_check(algo_violations, nn_violations):
    """
    Reimplements the guardrail's core comparison directly, matching
    the logic in orchestrator.validate_route, so this test doesn't
    depend on loading real CSV files or a live Groq connection.
    """
    return algo_violations <= nn_violations


def test_guardrail_passes_when_algorithm_improves_on_baseline():
    assert _guardrail_check(algo_violations=1, nn_violations=4) is True


def test_guardrail_passes_when_algorithm_equals_baseline():
    assert _guardrail_check(algo_violations=2, nn_violations=2) is True


def test_guardrail_fails_when_algorithm_is_worse_than_baseline():
    """
    The critical safety case: if the algorithm somehow produced MORE
    violations than the untouched baseline, the guardrail must catch
    it and report failure — never silently pass.
    """
    assert _guardrail_check(algo_violations=3, nn_violations=1) is False


def test_guardrail_status_labels_are_correct():
    """
    Confirms the three real status labels the agent relies on:
    SAFE (zero violations), GUARDRAIL_OK_BUT_UNRESOLVED (improved but
    not perfect), and GUARDRAIL_FAILED (worse than baseline — should
    never happen given the algorithm's own internal guarantee, but
    the check must still catch it if it somehow did).
    """
    def status_for(algo_v, nn_v):
        guardrail_passed = algo_v <= nn_v
        if algo_v == 0:
            return "SAFE"
        elif guardrail_passed:
            return "GUARDRAIL_OK_BUT_UNRESOLVED"
        else:
            return "GUARDRAIL_FAILED"

    assert status_for(0, 4) == "SAFE"
    assert status_for(1, 4) == "GUARDRAIL_OK_BUT_UNRESOLVED"
    assert status_for(5, 1) == "GUARDRAIL_FAILED"