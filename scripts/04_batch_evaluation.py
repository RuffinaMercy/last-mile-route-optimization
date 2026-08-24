"""
Runs the full algorithm (nearest-neighbor -> constrained 2-opt) across
a random, reproducible sample of 500 routes, comparing each against
the actual human driver's real sequence. Results are written to a
Gold-layer table in resumable batches of 25, so a dropped session
(a real, repeated occurrence on Databricks Free Edition) never loses
progress — each run checks what's already saved and continues from there.
"""

import time
import pandas as pd
from datetime import datetime, timedelta
# from algorithm import nearest_neighbor_route, evaluate_route_plain, two_opt_constrained_fast

# --- Gold table setup (run once) ---
# CREATE SCHEMA IF NOT EXISTS last_mile_routing.gold;
# CREATE TABLE IF NOT EXISTS last_mile_routing.gold.route_comparison (
#     route_id STRING, num_stops INT,
#     nn_time_seconds DOUBLE, nn_violations INT,
#     algo_time_seconds DOUBLE, algo_violations INT,
#     actual_time_seconds DOUBLE, actual_violations INT,
#     algo_passes_run INT
# )

# --- Sample selection (seed 42 = reproducible) ---
sample_routes_df = spark.sql("""
    SELECT DISTINCT route_id FROM last_mile_routing.silver.dim_routes
    ORDER BY RAND(42) LIMIT 500
""").toPandas()
sample_route_ids = sample_routes_df['route_id'].tolist()

# --- Bulk pull all data for the sample (5 queries, not 2,500) ---
route_ids_str = "', '".join(sample_route_ids)
stops_bulk = spark.sql(f"SELECT route_id, stop_id, stop_type FROM last_mile_routing.silver.fact_stops WHERE route_id IN ('{route_ids_str}')").toPandas()
travel_bulk = spark.sql(f"SELECT route_id, from_stop_id, to_stop_id, travel_seconds FROM last_mile_routing.silver.fact_travel_times WHERE route_id IN ('{route_ids_str}')").toPandas()
actual_bulk = spark.sql(f"SELECT route_id, stop_id, actual_sequence_position FROM last_mile_routing.silver.fact_actual_sequences WHERE route_id IN ('{route_ids_str}')").toPandas()
packages_bulk = spark.sql(f"SELECT route_id, stop_id, time_window_start, time_window_end, planned_service_time_seconds FROM last_mile_routing.silver.dim_packages WHERE route_id IN ('{route_ids_str}')").toPandas()
route_info_bulk = spark.sql(f"SELECT route_id, date, departure_time_utc FROM last_mile_routing.silver.dim_routes WHERE route_id IN ('{route_ids_str}')").toPandas()

# --- Build fast, plain-Python lookup structures (pandas overhead avoided) ---
travel_by_route = {}
for rid, group in travel_bulk.groupby('route_id'):
    tt = {}
    for f, t, s in zip(group['from_stop_id'].values, group['to_stop_id'].values, group['travel_seconds'].values):
        tt.setdefault(f, {})[t] = s
    travel_by_route[rid] = tt

stops_by_route = {rid: g for rid, g in stops_bulk.groupby('route_id')}
actual_by_route = {rid: g.sort_values('actual_sequence_position')['stop_id'].tolist() for rid, g in actual_bulk.groupby('route_id')}

packages_bulk['window_start_dt'] = pd.to_datetime(packages_bulk['time_window_start'])
packages_bulk['window_end_dt'] = pd.to_datetime(packages_bulk['time_window_end'])
packages_by_route = {}
for rid, sid, ws, we, svc in zip(packages_bulk['route_id'].values, packages_bulk['stop_id'].values,
                                    packages_bulk['window_start_dt'].values, packages_bulk['window_end_dt'].values,
                                    packages_bulk['planned_service_time_seconds'].values):
    packages_by_route.setdefault(rid, {}).setdefault(sid, []).append((ws, we, svc))

route_info_bulk_indexed = route_info_bulk.set_index('route_id')

# --- Main resumable loop ---
already_done_df = spark.sql("SELECT DISTINCT route_id FROM last_mile_routing.gold.route_comparison").toPandas()
already_done = set(already_done_df['route_id']) if len(already_done_df) else set()

results_batch, flush_every, processed_this_run = [], 25, 0
overall_start = time.time()

for route_id in sample_route_ids:
    if route_id in already_done:
        continue

    tt = travel_by_route[route_id]
    stops = stops_by_route[route_id]
    actual_seq = actual_by_route[route_id]
    pkgs = packages_by_route.get(route_id, {})
    r_info = route_info_bulk_indexed.loc[route_id]
    route_date, departure_time_str = r_info['date'], r_info['departure_time_utc']

    start_stop_rows = stops[stops['stop_type'] == 'Station']
    if len(start_stop_rows) == 0:
        continue
    start_stop = start_stop_rows.iloc[0]['stop_id']
    all_stop_ids = list(stops['stop_id'])

    nn_route = nearest_neighbor_route(start_stop, all_stop_ids, tt)
    nn_violations, nn_time = evaluate_route_plain(nn_route, tt, pkgs, route_date, departure_time_str)

    algo_route, (algo_violations, algo_time), passes_run = two_opt_constrained_fast(
        nn_route, tt, pkgs, route_date, departure_time_str)

    actual_violations, actual_time = evaluate_route_plain(actual_seq, tt, pkgs, route_date, departure_time_str)

    results_batch.append({
        'route_id': route_id, 'num_stops': len(all_stop_ids),
        'nn_time_seconds': nn_time, 'nn_violations': int(nn_violations),
        'algo_time_seconds': algo_time, 'algo_violations': int(algo_violations),
        'actual_time_seconds': actual_time, 'actual_violations': int(actual_violations),
        'algo_passes_run': passes_run
    })
    processed_this_run += 1

    if len(results_batch) >= flush_every:
        pdf = pd.DataFrame(results_batch)
        spark.createDataFrame(pdf).write.format("delta").mode("append") \
            .saveAsTable("last_mile_routing.gold.route_comparison")
        print(f"Flushed {processed_this_run} routes — {time.time()-overall_start:.1f}s elapsed")
        results_batch = []

if results_batch:
    pdf = pd.DataFrame(results_batch)
    spark.createDataFrame(pdf).write.format("delta").mode("append") \
        .saveAsTable("last_mile_routing.gold.route_comparison")

print(f"Done — {processed_this_run} new routes processed.")

# --- Final aggregate findings ---
# SELECT COUNT(*) as total_routes,
#        AVG(algo_time_seconds - actual_time_seconds)/60 as avg_time_diff_minutes,
#        SUM(CASE WHEN algo_time_seconds < actual_time_seconds THEN 1 ELSE 0 END) as routes_algo_faster,
#        SUM(CASE WHEN algo_violations = 0 THEN 1 ELSE 0 END) as routes_zero_violations
# FROM last_mile_routing.gold.route_comparison