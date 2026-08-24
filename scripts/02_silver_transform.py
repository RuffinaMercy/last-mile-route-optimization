"""
Silver layer: flattens the raw nested JSON files into clean,
relational Delta tables (a star schema).
"""

import json
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import ijson
import pandas as pd
import time

volume_path = '/Volumes/last_mile_routing/bronze/raw_files/'

# --- route_data.json -> dim_routes, fact_stops ---
with open(volume_path + 'route_data.json', 'r') as f:
    data = json.load(f)

routes_rows, stops_rows = [], []
for route_id, route_info in data.items():
    routes_rows.append({
        'route_id': route_id,
        'station_code': route_info['station_code'],
        'date': route_info['date_YYYY_MM_DD'],
        'departure_time_utc': route_info['departure_time_utc'],
        'executor_capacity_cm3': route_info['executor_capacity_cm3'],
        'route_score': route_info['route_score']
    })
    for stop_id, stop_info in route_info['stops'].items():
        stops_rows.append({
            'route_id': route_id, 'stop_id': stop_id,
            'lat': stop_info['lat'], 'lng': stop_info['lng'],
            'stop_type': stop_info['type'], 'zone_id': stop_info['zone_id']
        })

spark.createDataFrame(routes_rows).write.format("delta").mode("overwrite") \
    .saveAsTable("last_mile_routing.silver.dim_routes")
spark.createDataFrame(stops_rows).write.format("delta").mode("overwrite") \
    .saveAsTable("last_mile_routing.silver.fact_stops")

# --- package_data.json -> dim_packages ---
with open(volume_path + 'package_data.json', 'r') as f:
    package_data = json.load(f)

packages_rows = []
for route_id, route_packages in package_data.items():
    for stop_id, stop_packages in route_packages.items():
        for package_id, package_info in stop_packages.items():
            packages_rows.append({
                'route_id': route_id, 'stop_id': stop_id, 'package_id': package_id,
                'scan_status': package_info['scan_status'],
                'time_window_start': package_info['time_window']['start_time_utc'],
                'time_window_end': package_info['time_window']['end_time_utc'],
                'planned_service_time_seconds': package_info['planned_service_time_seconds'],
                'depth_cm': package_info['dimensions']['depth_cm'],
                'height_cm': package_info['dimensions']['height_cm'],
                'width_cm': package_info['dimensions']['width_cm']
            })

spark.createDataFrame(packages_rows).write.format("delta").mode("overwrite") \
    .saveAsTable("last_mile_routing.silver.dim_packages")

# --- actual_sequences.json -> fact_actual_sequences (ground truth) ---
with open(volume_path + 'actual_sequences.json', 'r') as f:
    actual_seq_data = json.load(f)

sequences_rows = []
for route_id, seq_info in actual_seq_data.items():
    for stop_id, position in seq_info['actual'].items():
        sequences_rows.append({
            'route_id': route_id, 'stop_id': stop_id,
            'actual_sequence_position': position
        })

spark.createDataFrame(sequences_rows).write.format("delta").mode("overwrite") \
    .saveAsTable("last_mile_routing.silver.fact_actual_sequences")

# --- travel_times.json -> fact_travel_times ---
# 1.7GB, deeply nested (route -> stop -> stop -> seconds), ~140M rows once
# flattened. Too large to json.load() into memory. Streamed with ijson
# (C backend) from a LOCAL copy of the file (reading directly from the
# network-mounted Volume was the real bottleneck, not ijson itself).
# Written in resumable batches: checks the table for already-saved
# routes on every run, so it survives session drops mid-load.

import shutil
shutil.copy(volume_path + 'travel_times.json', '/tmp/travel_times.json')
local_path = '/tmp/travel_times.json'

already_done_df = spark.sql(
    "SELECT DISTINCT route_id FROM last_mile_routing.silver.fact_travel_times"
).toPandas()
already_done = set(already_done_df['route_id']) if len(already_done_df) else set()

batch, routes_processed, routes_skipped = [], 0, 0
flush_every_n_routes = 100
overall_start = time.time()

with open(local_path, 'rb') as f:
    for route_id, matrix in ijson.kvitems(f, ''):
        if route_id in already_done:
            continue

        from_stops, to_stops, seconds = [], [], []
        for from_stop, targets in matrix.items():
            for to_stop, sec in targets.items():
                from_stops.append(from_stop)
                to_stops.append(to_stop)
                seconds.append(sec)

        for f_s, t_s, s in zip(from_stops, to_stops, seconds):
            batch.append({'route_id': route_id, 'from_stop_id': f_s,
                           'to_stop_id': t_s, 'travel_seconds': s})

        routes_processed += 1
        if routes_processed % flush_every_n_routes == 0:
            pdf = pd.DataFrame(batch)
            spark.createDataFrame(pdf).write.format("delta").mode("append") \
                .saveAsTable("last_mile_routing.silver.fact_travel_times")
            print(f"Flushed {routes_processed} routes — {time.time()-overall_start:.1f}s")
            batch = []

if batch:
    pdf = pd.DataFrame(batch)
    spark.createDataFrame(pdf).write.format("delta").mode("append") \
        .saveAsTable("last_mile_routing.silver.fact_travel_times")

print("Silver transform complete.")