"""
Bronze layer: downloads the 5 raw JSON files from Amazon's public
Last Mile Routing Research Challenge S3 bucket into a Databricks Volume,
completely untouched/raw. Uses a manual chunked streaming read/write
(not boto3's default download_file) because network-mounted Volume
storage does not reliably handle multi-threaded downloads.
"""

import boto3
from botocore import UNSIGNED
from botocore.config import Config

s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
bucket = 'amazon-last-mile-challenges'
prefix = 'almrrc2021/almrrc2021-data-training/model_build_inputs/'
volume_path = '/Volumes/last_mile_routing/bronze/raw_files/'

files = [
    'route_data.json',
    'package_data.json',
    'travel_times.json',
    'actual_sequences.json',
    'invalid_sequence_scores.json'
]

for f in files:
    print(f"Downloading {f}...")
    response = s3.get_object(Bucket=bucket, Key=prefix + f)
    body = response['Body']

    with open(volume_path + f, 'wb') as out_file:
        while True:
            chunk = body.read(8 * 1024 * 1024)  # 8MB at a time
            if not chunk:
                break
            out_file.write(chunk)

    print(f"Done: {f}")

print("Bronze ingestion complete.")