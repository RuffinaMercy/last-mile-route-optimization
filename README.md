# Last-Mile Route Optimization: Algorithm vs. Human Drivers

A data engineering and optimization project that tests whether an algorithm can sequence delivery stops as well as an experienced human driver — using real Amazon delivery data — while still respecting every delivery time-window commitment.

## Problem statement

Delivery companies (Amazon, quick-commerce platforms like Swiggy Instamart/Blinkit, any fleet-based business) must decide, for every route, what order a driver should visit their stops in. Pure distance-minimizing algorithms often lose to experienced human drivers in practice, because drivers factor in real-world knowledge (traffic patterns, access issues) that a map doesn't capture. This project quantifies that gap on real data: **can a constraint-aware optimization algorithm match or beat real human driver performance, without breaking any delivery-time promise?**

## Dataset

[Amazon Last Mile Routing Research Challenge](https://registry.opendata.aws/amazon-last-mile-challenges/) — 6,112 real, anonymized delivery routes from 2018, across five US metro areas. Each route includes:
- Stop locations and zones
- Package details and delivery time windows
- Real pairwise travel times between stops
- The actual sequence the human driver drove

Licensed CC BY-NC 4.0. Credit: Amazon.com, Inc. and MIT-CAVE.

## Architecture

A medallion architecture (Bronze → Silver → Gold) built in Databricks:

```
Bronze  →  Raw JSON files, landed as-is from the public S3 bucket
Silver  →  Cleaned, flattened, relational tables (star schema)
Gold    →  Per-route algorithm-vs-human comparison results, ready for the dashboard
```

**Silver layer tables:**

| Table | Description | Rows |
|---|---|---|
| `dim_routes` | Route-level metadata (depot, date, capacity, quality score) | 6,112 |
| `fact_stops` | One row per stop (location, type, zone) | 904,527 |
| `dim_packages` | One row per package (time window, dimensions, status) | 1,457,175 |
| `fact_actual_sequences` | Ground truth — the real order each driver visited stops in | 904,527 |
| `fact_travel_times` | Drive time between every pair of stops, per route | 139,748,173 |

**Gold layer:** `route_comparison` — one row per route, with nearest-neighbor, constrained-algorithm, and actual-driver results (time, violations) side by side.

## Approach

1. **Baseline algorithm** — nearest-neighbor construction (always visit the closest unvisited stop next).
2. **Improvement pass** — 2-opt local search (detects and removes route "crossings" that waste distance).
3. **Constraint enforcement** — the improvement step only accepts a swap if it reduces time-window violations first, then time second — so the algorithm can never trade a broken delivery promise for extra speed.
4. **Fair evaluation** — every comparison includes both travel time and package service time, and checks every delivery promise against the simulated arrival time.
5. **Validation at scale** — the full pipeline was run on a random, reproducible sample of 500 routes (seed 42), not just a single example.

## Results

Across 500 real routes:

| Metric | Result |
|---|---|
| Average time saved by algorithm vs. actual driver | **6.7 minutes** |
| Routes where algorithm was faster | **354 / 500 (70.8%)** |
| Routes with zero time-window violations | **494 / 500 (98.8%)** |
| Unconstrained nearest-neighbor: avg. time vs. driver | +4.1 min **slower** |
| Unconstrained nearest-neighbor: total violations | **1,113** |

**Key finding:** a naive, unconstrained algorithm is not just less "considerate" than a human driver — it's actually *slower on average* and racks up over a thousand broken delivery promises across the sample. Once the algorithm is made constraint-aware, it matches human-level reliability (98.8% zero-violation rate) while still winning on time in 7 of 10 routes. This suggests human drivers' real advantage isn't raw path-finding — it's implicitly balancing speed against commitments, which a naive optimizer misses entirely.

The 6 routes (1.2%) where the algorithm didn't reach zero violations each had exactly one residual violation, with no correlation to route size — consistent with 2-opt being a local search method without a global optimality guarantee, not a systematic failure pattern.

## Code walkthrough

| Script / notebook cell | What it does |
|---|---|
| **S3 exploration** (`boto3` + `list_objects_v2`) | Confirms the real bucket/folder structure before downloading anything blindly. |
| **Bronze ingestion** (`boto3.get_object` streamed in 8MB chunks) | Downloads the 5 raw JSON files into a Databricks Volume. Uses a manual streaming read/write instead of `download_file`, since network-mounted storage doesn't handle multi-threaded downloads reliably. |
| **`route_data.json` flattening** | Loads the full file (75MB, safe to load whole), splits the nested `route → stops` dict into two flat lists (`dim_routes`, `fact_stops`), saves as Delta tables. |
| **`package_data.json` flattening** | Same pattern, one level deeper (`route → stop → package`), producing `dim_packages`. |
| **`actual_sequences.json` flattening** | Produces `fact_actual_sequences`, the ground-truth benchmark. Row count cross-checked against `fact_stops` for a data-quality guarantee. |
| **`travel_times.json` streaming** (`ijson.kvitems`) | The 1.7GB file is too large/nested to load with `json.load()`. Streamed route-by-route using `ijson`'s C backend, read from a local copy (not the network Volume — network reads were the real bottleneck, not `ijson` itself), converted to pandas before Spark (row-by-row dict→Spark conversion was ~5,000x slower than pandas-first), and written in resumable batches of 100 routes. |
| **`nearest_neighbor_route()`** | Greedy construction heuristic: always moves to the closest unvisited stop. |
| **`evaluate_route_plain()`** | Simulates a route's clock (travel + package service time) and counts time-window violations. Rewritten to avoid pandas method calls inside the loop — the original pandas-based version cost ~2.5 seconds per call; the plain-Python-tuple version costs ~0.5 milliseconds. |
| **`two_opt_constrained_fast()`** | 2-opt improvement loop. Accepts a swap only if `(violations, time)` improves as a pair — violations are compared first, so the algorithm can never sacrifice a delivery promise for speed. |
| **Bulk sample pipeline (500 routes)** | Pulls all data for a random, seeded sample in bulk (5 queries total, not 2,500), builds fast in-memory lookups, runs the full algorithm per route, and saves results in resumable batches of 25 to `gold.route_comparison`. |
| **Aggregate analysis query** | Computes the final headline metrics (average time saved, win rate, violation rate) across all 500 routes. |

## Engineering challenges (real, and worth mentioning in interviews)

- **Nested JSON at scale**: the raw dataset's folder structure and file nesting didn't match documentation exactly — confirmed the real structure via direct S3 listing before writing any pipeline code.
- **A 5,000x performance bug**: repeated small pandas operations (`.notna()`, comparisons, `.sum()`) on tiny 1-3 row slices had heavy fixed overhead when called millions of times; fixed by converting to plain Python tuples before the hot loop.
- **A silent correctness bug**: an early "faster" algorithm result was actually invalid — it violated delivery-time promises the human driver respected. Caught by building an explicit validation step rather than trusting a favorable-looking number.
- **Platform instability**: Databricks Free Edition serverless compute repeatedly dropped sessions, including a confirmed multi-day platform-wide outage. Solved by designing every long-running step (the 1.7GB file load, the 500-route batch run) to be resumable — checking what's already saved before continuing, so no progress was ever lost to a dropped session.

## What's still needed before calling this complete

Being honest about the gaps:

1. **README images/dashboard export** — embed actual screenshots of the Databricks dashboard (or the static matplotlib chart) directly in this README, not just described in text.
2. **Scale beyond the 500-route sample** — the full 6,112-route population hasn't been run end-to-end; the sample is statistically reasonable but a full run (or a larger sample) would strengthen the claim.
3. **Failure case write-up** — a short, specific look at 1-2 of the 6 imperfect routes (what did the human do differently there?) would turn "we found 6 edge cases" into a real, demonstrable insight.
4. **Code cleanup and consolidation** — the working code currently lives across many notebook cells built iteratively; before publishing, consolidate into clean, documented `.py` scripts or a single organized notebook.
5. **Push to GitHub** — with this README, the code, and a `requirements.txt` / environment note (Databricks Free Edition, PySpark, `ijson`, pandas).
6. **A short demo or GIF of the dashboard** for the LinkedIn post itself.
7. **(Optional, stronger differentiator)** — the previously discussed supervised-learning extension: train a model on real driver sequences to learn an implicit "human-like" cost function, and see if it closes the gap further on the routes where 2-opt still trails the driver.

## Tech stack

Databricks (Free Edition, serverless) · PySpark · Delta Lake · `ijson` · pandas · SQL · Python (nearest-neighbor + constrained 2-opt) · Databricks Dashboards

## Acknowledgment

Dataset provided by Amazon.com, Inc. and MIT Center for Transportation & Logistics, released for the Amazon Last Mile Routing Research Challenge (2021).

## Scope and limitations

This project is a **retrospective, data-driven analysis** — it evaluates how the algorithm *would have* performed against historical routes, using historical ground truth. It does not claim production deployment or real-world driver usage.

A genuine rollout would require, at minimum:
- **Live A/B testing** — comparing algorithm-suggested routes against driver judgment in real conditions, not simulated ones
- **Real-time data** — this analysis uses historical average travel times; live traffic conditions change minute to minute
- **Driver adoption considerations** — whether drivers trust and follow an unfamiliar route suggestion is a separate, non-technical problem
- **A feedback loop** — capturing cases where a driver overrides the algorithm, to improve it over time (see the supervised-learning extension idea below)

This project is best understood as the necessary first step before such a pilot — a way to build a data-backed, quantified case for whether further investment in this direction is justified.

## Agentic AI layer

An LLM-driven orchestrator (`agent/orchestrator.py`, using Groq's `openai/gpt-oss-120b` with tool-calling) investigates a route's optimization result autonomously. Given a route ID, it decides which of 4 tools to call — fetching the route's summary, validating it against a safety guardrail, comparing it to the real human driver's performance, and (if issues remain) searching for similar known failure cases — reasoning through each step and producing a grounded, plain-English explanation.

**Design principle: the safety guardrail is enforced in code, not by the LLM.** After every optimization result, an independent check (`validate_route`) confirms that the algorithm's violation count never exceeds the untouched baseline's — this check runs regardless of what the LLM concludes, so a confused or manipulated model can never cause an unsafe result to be reported as safe. This distinction — reasoning delegated to the LLM, safety enforced structurally — is deliberate, and directly informed by [AI safety/security coursework and interest].

Example trace (investigating a route with a residual violation):
- Correctly distinguished "guardrail passed" (algorithm ≤ baseline) from "fully resolved" (zero violations) — flagging the route as safe-but-needing-review rather than falsely claiming full success
- Identified 3 similar-sized routes with the same residual-violation pattern, without being explicitly told to look for a pattern

Tested in `tests/test_agent_guardrail.py`, covering: guardrail passes when the algorithm improves or matches the baseline, and guardrail correctly fails if violations were ever worse than baseline (a case that should never occur given the algorithm's own internal guarantee, but is checked independently regardless).