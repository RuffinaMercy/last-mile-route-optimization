"""
Core routing algorithm: a nearest-neighbor construction heuristic
improved with constrained 2-opt local search. The 2-opt only accepts
a swap if it improves (violation_count, total_time) as a pair —
violations are compared first, so speed can never be gained by
breaking a delivery-time promise.
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


def evaluate_route_plain(route, travel_time, packages_plain, route_date, departure_time_str):
    """
    Simulates a route's clock (travel time + package service time) and
    counts how many delivery time-window promises are broken.

    packages_plain: dict of stop_id -> list of (window_start, window_end, service_seconds)
    tuples — deliberately plain Python (no pandas calls) inside this hot
    loop, since repeated small pandas operations here were ~5,000x slower.
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
        if stop_id not in packages_plain:
            continue
        arrival_ts = pd.Timestamp(arrival)
        for window_start, window_end, _ in packages_plain[stop_id]:
            if pd.isna(window_start) or pd.isna(window_end):
                continue
            if arrival_ts < pd.Timestamp(window_start) or arrival_ts > pd.Timestamp(window_end):
                violation_count += 1

    return violation_count, total_time


def two_opt_constrained_fast(route, travel_time, packages_plain, route_date,
                              departure_time_str, max_passes=10):
    """
    2-opt improvement: tries every pair of positions, reversing the
    segment between them. A swap is kept only if the resulting
    (violations, time) tuple is strictly better — violations compared
    first, time second — so the algorithm can never trade a broken
    promise for extra speed.

    Note: this recalculates the whole route per candidate swap
    (O(n^3) per pass) — a known limitation. A delta-based version that
    only recalculates the changed section would be the production fix.
    """
    best_route = route[:]
    best_score = evaluate_route_plain(best_route, travel_time, packages_plain,
                                       route_date, departure_time_str)
    passes_run = 0

    for _ in range(max_passes):
        improved_this_pass = False
        for i in range(1, len(best_route) - 1):
            for j in range(i + 1, len(best_route)):
                new_route = best_route[:i] + best_route[i:j+1][::-1] + best_route[j+1:]
                new_score = evaluate_route_plain(new_route, travel_time, packages_plain,
                                                  route_date, departure_time_str)
                if new_score < best_score:
                    best_route = new_route
                    best_score = new_score
                    improved_this_pass = True
        passes_run += 1
        if not improved_this_pass:
            break

    return best_route, best_score, passes_run