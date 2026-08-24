"""
Core routing algorithm: a nearest-neighbor construction heuristic
improved with constrained 2-opt local search. The 2-opt only accepts
a swap if it improves (violation_count, total_time) as a pair —
violations are compared first, so speed can never be gained by
breaking a delivery-time promise.

Performance note: 2-opt tests every pair of positions (i, j) as a
candidate swap. For any swap starting at position i, the route BEFORE
position i is identical to the current best route — there is no need
to re-simulate it from scratch on every candidate. This module caches
that unchanged prefix (arrival times + violation counts) once per
accepted swap, and only re-simulates from position i onward for each
candidate — roughly halving the average work per evaluation compared
to recomputing the whole route every time.
"""

import pandas as pd
from datetime import datetime, timedelta


def nearest_neighbor_route(start_stop, all_stops, travel_time):
    """Greedy construction: always move to the closest unvisited stop."""
    unvisited = set(all_stops) - {start_stop}
    route = [start_stop]
    current = start_stop
    while unvisited:
        nearest_stop = min(unvisited, key=lambda c: travel_time[current][c])
        route.append(nearest_stop)
        unvisited.remove(nearest_stop)
        current = nearest_stop
    return route


def _count_violations_at_stop(stop_id, arrival, packages_plain):
    """How many delivery-time promises are broken by arriving at
    `stop_id` at time `arrival`."""
    if stop_id not in packages_plain:
        return 0
    arrival_ts = pd.Timestamp(arrival)
    count = 0
    for window_start, window_end, _ in packages_plain[stop_id]:
        if pd.isna(window_start) or pd.isna(window_end):
            continue
        if arrival_ts < pd.Timestamp(window_start) or arrival_ts > pd.Timestamp(window_end):
            count += 1
    return count


def evaluate_route_plain(route, travel_time, packages_plain, route_date, departure_time_str):
    """
    Simulates a route's clock (travel time + package service time) and
    counts how many delivery time-window promises are broken.

    packages_plain: dict of stop_id -> list of (window_start, window_end,
    service_seconds) tuples — deliberately plain Python (no pandas calls)
    inside this hot loop, since repeated small pandas operations here
    were measured to be ~5,000x slower.

    This is the full, from-scratch evaluator — used as the baseline
    for correctness (see tests/test_algorithm.py) and for the very
    first evaluation of a route. The 2-opt loop itself uses the faster
    prefix-based path below once a starting route has been evaluated once.
    """
    current_time = datetime.strptime(f"{route_date} {departure_time_str}", "%Y-%m-%d %H:%M:%S")
    start_time = current_time
    arrival_times = {route[0]: current_time}

    for i in range(len(route) - 1):
        cur, nxt = route[i], route[i + 1]
        current_time += timedelta(seconds=float(travel_time[cur][nxt]))
        if cur in packages_plain:
            service_seconds = sum(p[2] for p in packages_plain[cur])
            current_time += timedelta(seconds=float(service_seconds))
        arrival_times[nxt] = current_time

    total_time = (current_time - start_time).total_seconds()

    violation_count = 0
    for stop_id, arrival in arrival_times.items():
        violation_count += _count_violations_at_stop(stop_id, arrival, packages_plain)

    return violation_count, total_time


def _compute_prefix(route, travel_time, packages_plain, route_date, departure_time_str):
    """
    Precomputes, for every position k in `route`:
      - arrival_prefix[k]: the arrival time at route[k]
      - violation_prefix[k]: the CUMULATIVE violation count for stops
        route[0..k] inclusive

    This lets any future candidate swap that shares the same prefix
    (positions 0..i-1) skip re-simulating that part entirely.
    """
    start_time = datetime.strptime(f"{route_date} {departure_time_str}", "%Y-%m-%d %H:%M:%S")
    current_time = start_time

    arrival_prefix = [current_time]
    violation_count = _count_violations_at_stop(route[0], current_time, packages_plain)
    violation_prefix = [violation_count]

    for k in range(len(route) - 1):
        cur, nxt = route[k], route[k + 1]
        current_time += timedelta(seconds=float(travel_time[cur][nxt]))
        if cur in packages_plain:
            service_seconds = sum(p[2] for p in packages_plain[cur])
            current_time += timedelta(seconds=float(service_seconds))
        arrival_prefix.append(current_time)

        violation_count += _count_violations_at_stop(nxt, current_time, packages_plain)
        violation_prefix.append(violation_count)

    return arrival_prefix, violation_prefix, start_time


def _evaluate_from_prefix(new_route, start_index, arrival_prefix, violation_prefix,
                           travel_time, packages_plain, start_time_overall):
    """
    Evaluates `new_route`, reusing everything already known about
    positions 0..start_index-1 (identical to the route the prefix was
    computed from), and only simulating positions start_index..end fresh.
    """
    current_time = arrival_prefix[start_index - 1]
    violation_count = violation_prefix[start_index - 1]

    for k in range(start_index - 1, len(new_route) - 1):
        cur, nxt = new_route[k], new_route[k + 1]
        current_time += timedelta(seconds=float(travel_time[cur][nxt]))
        if cur in packages_plain:
            service_seconds = sum(p[2] for p in packages_plain[cur])
            current_time += timedelta(seconds=float(service_seconds))
        violation_count += _count_violations_at_stop(nxt, current_time, packages_plain)

    total_time = (current_time - start_time_overall).total_seconds()
    return violation_count, total_time


def two_opt_constrained_fast(route, travel_time, packages_plain, route_date,
                              departure_time_str, max_passes=10):
    """
    2-opt improvement: tries every pair of positions, reversing the
    segment between them. A swap is kept only if the resulting
    (violations, time) tuple is strictly better — violations compared
    first, time second — so the algorithm can never trade a broken
    promise for extra speed.

    Uses the prefix-caching optimization above: the unchanged part of
    the route before each candidate swap's start position is never
    re-simulated, only the changed suffix is.
    """
    best_route = route[:]
    best_score = evaluate_route_plain(best_route, travel_time, packages_plain,
                                       route_date, departure_time_str)
    passes_run = 0

    for _ in range(max_passes):
        improved_this_pass = False
        arrival_prefix, violation_prefix, start_time_overall = _compute_prefix(
            best_route, travel_time, packages_plain, route_date, departure_time_str
        )

        for i in range(1, len(best_route) - 1):
            for j in range(i + 1, len(best_route)):
                new_route = best_route[:i] + best_route[i:j+1][::-1] + best_route[j+1:]
                new_score = _evaluate_from_prefix(
                    new_route, i, arrival_prefix, violation_prefix,
                    travel_time, packages_plain, start_time_overall
                )
                if new_score < best_score:
                    best_route = new_route
                    best_score = new_score
                    improved_this_pass = True
                    arrival_prefix, violation_prefix, start_time_overall = _compute_prefix(
                        best_route, travel_time, packages_plain, route_date, departure_time_str
                    )

        passes_run += 1
        if not improved_this_pass:
            break

    return best_route, best_score, passes_run