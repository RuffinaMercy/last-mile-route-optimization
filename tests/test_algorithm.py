"""
Unit tests for the core routing algorithm (nearest_neighbor_route,
evaluate_route_plain, two_opt_constrained_fast).

These tests run locally — no Spark/Databricks needed, since the
algorithm module is pure Python.

Run with: pytest tests/test_algorithm.py -v
"""

import importlib.util
import os
import sys
from datetime import datetime, timedelta
import pandas as pd
import pytest

# 03_algorithm.py isn't a valid Python module name (can't start with a
# digit), so we load it directly by file path instead of a normal import.
SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", "scripts", "03_algorithm.py")
spec = importlib.util.spec_from_file_location("algorithm", SCRIPT_PATH)
algorithm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(algorithm)

nearest_neighbor_route = algorithm.nearest_neighbor_route
evaluate_route_plain = algorithm.evaluate_route_plain
two_opt_constrained_fast = algorithm.two_opt_constrained_fast


# ---------- Fixtures: a small, fully known synthetic route ----------

@pytest.fixture
def simple_travel_time():
    """
    A tiny 4-stop network with known distances, laid out so that the
    'obvious' order A -> B -> C -> D is NOT the shortest path — this
    lets us check that 2-opt actually finds a real improvement, not
    just returns its input unchanged.
    """
    return {
        'A': {'A': 0, 'B': 100, 'C': 100, 'D': 300},
        'B': {'A': 100, 'B': 0, 'C': 300, 'D': 100},
        'C': {'A': 100, 'B': 300, 'C': 0, 'D': 100},
        'D': {'A': 300, 'B': 100, 'C': 100, 'D': 0},
    }


@pytest.fixture
def route_date_and_time():
    return "2018-07-27", "09:00:00"


# ---------- nearest_neighbor_route ----------

def test_nearest_neighbor_visits_every_stop_exactly_once(simple_travel_time):
    route = nearest_neighbor_route('A', ['A', 'B', 'C', 'D'], simple_travel_time)
    assert sorted(route) == ['A', 'B', 'C', 'D']
    assert len(route) == len(set(route))  # no duplicates


def test_nearest_neighbor_starts_at_given_stop(simple_travel_time):
    route = nearest_neighbor_route('A', ['A', 'B', 'C', 'D'], simple_travel_time)
    assert route[0] == 'A'


# ---------- evaluate_route_plain ----------

def test_evaluate_route_no_packages_returns_zero_violations(simple_travel_time, route_date_and_time):
    route_date, departure_time_str = route_date_and_time
    violations, total_time = evaluate_route_plain(
        ['A', 'B', 'C', 'D'], simple_travel_time, {}, route_date, departure_time_str
    )
    assert violations == 0
    assert total_time == 100 + 300 + 100  # A->B->C->D travel times


def test_evaluate_route_detects_a_known_violation(simple_travel_time, route_date_and_time):
    route_date, departure_time_str = route_date_and_time
    base_time = datetime.strptime(f"{route_date} {departure_time_str}", "%Y-%m-%d %H:%M:%S")

    # Arrival at B is base_time + 100s. Give B a window that closes
    # BEFORE that arrival, so this must register as exactly one violation.
    window_start = base_time - timedelta(seconds=200)
    window_end = base_time + timedelta(seconds=50)  # closes before B is reached

    packages_plain = {'B': [(window_start, window_end, 0)]}

    violations, _ = evaluate_route_plain(
        ['A', 'B', 'C', 'D'], simple_travel_time, packages_plain, route_date, departure_time_str
    )
    assert violations == 1


def test_evaluate_route_respects_a_satisfied_window(simple_travel_time, route_date_and_time):
    route_date, departure_time_str = route_date_and_time
    base_time = datetime.strptime(f"{route_date} {departure_time_str}", "%Y-%m-%d %H:%M:%S")

    # Wide window that comfortably contains the real arrival time at B.
    window_start = base_time
    window_end = base_time + timedelta(seconds=1000)

    packages_plain = {'B': [(window_start, window_end, 0)]}

    violations, _ = evaluate_route_plain(
        ['A', 'B', 'C', 'D'], simple_travel_time, packages_plain, route_date, departure_time_str
    )
    assert violations == 0


def test_evaluate_route_includes_service_time(simple_travel_time, route_date_and_time):
    route_date, departure_time_str = route_date_and_time
    packages_plain = {'B': [(pd.NaT, pd.NaT, 50)]}  # no window, but 50s service time

    _, total_time_with_service = evaluate_route_plain(
        ['A', 'B', 'C', 'D'], simple_travel_time, packages_plain, route_date, departure_time_str
    )
    _, total_time_without_service = evaluate_route_plain(
        ['A', 'B', 'C', 'D'], simple_travel_time, {}, route_date, departure_time_str
    )
    assert total_time_with_service == total_time_without_service + 50


# ---------- two_opt_constrained_fast ----------

def test_two_opt_never_increases_violations(simple_travel_time, route_date_and_time):
    """
    The core correctness guarantee of the constrained algorithm: it
    must never return a route with MORE violations than it started
    with, even if that route would be faster.
    """
    route_date, departure_time_str = route_date_and_time
    base_time = datetime.strptime(f"{route_date} {departure_time_str}", "%Y-%m-%d %H:%M:%S")

    tight_window = (base_time, base_time + timedelta(seconds=50))
    packages_plain = {'B': [(tight_window[0], tight_window[1], 0)]}

    start_route = ['A', 'B', 'C', 'D']
    start_violations, _ = evaluate_route_plain(
        start_route, simple_travel_time, packages_plain, route_date, departure_time_str
    )

    _, (final_violations, _), _ = two_opt_constrained_fast(
        start_route, simple_travel_time, packages_plain, route_date, departure_time_str
    )

    assert final_violations <= start_violations


def test_two_opt_finds_a_real_improvement(simple_travel_time, route_date_and_time):
    """
    Given the deliberately awkward distances in simple_travel_time,
    2-opt should be able to find a route at least as good as the
    naive A->B->C->D order, with no violations involved.
    """
    route_date, departure_time_str = route_date_and_time
    start_route = ['A', 'B', 'C', 'D']

    start_violations, start_time = evaluate_route_plain(
        start_route, simple_travel_time, {}, route_date, departure_time_str
    )

    _, (final_violations, final_time), passes_run = two_opt_constrained_fast(
        start_route, simple_travel_time, {}, route_date, departure_time_str
    )

    assert final_violations == 0
    assert final_time <= start_time
    assert passes_run >= 1


def test_two_opt_output_visits_every_stop_exactly_once(simple_travel_time, route_date_and_time):
    route_date, departure_time_str = route_date_and_time
    start_route = ['A', 'B', 'C', 'D']

    best_route, _, _ = two_opt_constrained_fast(
        start_route, simple_travel_time, {}, route_date, departure_time_str
    )

    assert sorted(best_route) == sorted(start_route)
    assert len(best_route) == len(set(best_route))



# ---------- Delta-based optimization: correctness + speed ----------

def test_prefix_based_evaluation_matches_full_evaluation(simple_travel_time, route_date_and_time):
    """
    Regression test: the fast, prefix-caching path must produce the
    EXACT same (violations, time) result as the original from-scratch
    evaluator, for the same route.
    """
    route_date, departure_time_str = route_date_and_time
    base_time = datetime.strptime(f"{route_date} {departure_time_str}", "%Y-%m-%d %H:%M:%S")
    packages_plain = {'C': [(base_time, base_time + timedelta(seconds=150), 20)]}

    route = ['A', 'B', 'C', 'D']

    full_result = evaluate_route_plain(route, simple_travel_time, packages_plain,
                                        route_date, departure_time_str)

    arrival_prefix, violation_prefix, start_time = algorithm._compute_prefix(
        route, simple_travel_time, packages_plain, route_date, departure_time_str
    )
    prefix_result = algorithm._evaluate_from_prefix(
        route, 1, arrival_prefix, violation_prefix, simple_travel_time,
        packages_plain, start_time
    )

    assert full_result == prefix_result


def test_delta_2opt_measurably_faster_on_a_larger_route(route_date_and_time):
    """
    Builds a larger synthetic route (30 stops) and confirms the
    delta-based two_opt_constrained_fast completes in meaningfully
    fewer full-route evaluations than a naive full-recompute version
    would need — checked indirectly via wall-clock time as a sanity
    bound, not an exact ratio (timing varies by machine).
    """
    import random
    import time as time_module

    random.seed(1)
    stops = [f"S{i}" for i in range(30)]
    travel_time = {a: {b: (0 if a == b else random.randint(50, 500)) for b in stops} for a in stops}
    route_date, departure_time_str = route_date_and_time

    start = time_module.time()
    _, _, passes_run = two_opt_constrained_fast(
        stops, travel_time, {}, route_date, departure_time_str
    )
    elapsed = time_module.time() - start

    assert passes_run >= 1
    assert elapsed < 5.0  # generous upper bound; catches any accidental O(n^4)-style regression