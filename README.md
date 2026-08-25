# Last-Mile Route Optimization: Algorithm vs. Human Drivers

A full-stack data engineering and AI project testing whether an algorithm can sequence delivery stops as well as an experienced human driver — using real Amazon delivery data — while never breaking a delivery-time commitment the human respected. Includes an agentic AI layer that investigates optimization results with a code-enforced safety guardrail, and a live interactive dashboard.

**🔗 Live demo:** _add your Streamlit Community Cloud link here after deployment_

## Problem statement

Delivery companies (Amazon, quick-commerce platforms like Swiggy Instamart/Blinkit, any fleet-based business) must decide, for every route, what order a driver should visit their stops in. Pure distance-minimizing algorithms often lose to experienced human drivers in practice, because drivers factor in real-world knowledge (traffic patterns, access issues) a map doesn't capture. This project quantifies that gap on real data: **can a constraint-aware optimization algorithm match or beat real human driver performance, without breaking any delivery-time promise?**

## Dataset

[Amazon Last Mile Routing Research Challenge](https://registry.opendata.aws/amazon-last-mile-challenges/) — 6,112 real, anonymized delivery routes from 2018, across five US metro areas. Each route includes stop locations, package delivery time windows, real pairwise travel times between stops, and the actual sequence the human driver drove.

Licensed CC BY-NC 4.0. Credit: Amazon.com, Inc. and MIT-CAVE.

## Architecture

A medallion architecture (Bronze → Silver → Gold) built in Databricks:
Bronze → Raw JSON files, landed as-is from the public S3 bucket
Silver → Cleaned, flattened, relational tables (star schema)
Gold → Per-route algorithm-vs-human comparison results


**Silver layer tables:**

| Table | Description | Rows |
|---|---|---|
| `dim_routes` | Route-level metadata (depot, date, capacity, quality score) | 6,112 |
| `fact_stops` | One row per stop (location, type, zone) | 904,527 |
| `dim_packages` | One row per package (time window, dimensions, status) | 1,457,175 |
| `fact_actual_sequences` | Ground truth — real order each driver visited stops in | 904,527 |
| `fact_travel_times` | Drive time between every pair of stops, per route | 139,748,173 |

**Gold layer:** `route_comparison` — one row per route, with nearest-neighbor, constrained-algorithm, and actual-driver results (time, violations) side by side.

## Approach

1. **Baseline algorithm** — nearest-neighbor construction (always visit the closest unvisited stop next).
2. **Improvement pass** — 2-opt local search, with a delta-based optimization that only re-simulates the changed section of a route per candidate swap (instead of recomputing the whole route each time).
3. **Constraint enforcement** — a swap is only accepted if it improves `(violations, time)` as a pair — violations compared first, so the algorithm can never trade a broken delivery promise for extra speed.
4. **Fair evaluation** — every comparison includes travel time *and* package service time, checked against simulated arrival times.
5. **Validation at scale** — run on a random, reproducible sample of 500 routes (seed 42).

## Algorithmic trade-offs and design choices

We chose **2-opt local search** over global solvers (e.g., OR-Tools, LKH, Concorde) for three reasons:

1. **Tractability** — 2-opt runs in ~O(n²) per iteration, which is manageable for real-world routes of 50–150 stops. A global optimum solver would be overkill for a retrospective study and would obscure the comparison to human intuition.
2. **Interpretability** — every swap is a simple "uncrossing" of two path segments. We can trace *why* a swap was accepted or rejected, which is valuable for debugging and for explaining results to a non-technical audience.
3. **Fair baseline** — escalating to a super-human optimizer (e.g., Concorde) would make the comparison to human drivers unfair. We wanted to test whether a *modest, interpretable* heuristic could match human performance — not whether a state-of-the-art solver could obliterate it.

**Where 2-opt falls short:** in routes with highly clustered stops, 2-opt can get trapped in a local minimum that would require a *3-opt* or *Or-opt* move to escape. This perfectly explains the residual violations in 6 out of 500 routes — they're not a systematic failure, but the expected behavior of a local search method without a global optimality guarantee.

## Results

Across 500 real routes:

| Metric | Result |
|---|---|
| Average time saved by algorithm vs. actual driver | **6.7 minutes** |
| Routes where algorithm was faster | **354 / 500 (70.8%)** |
| Routes with zero time-window violations | **494 / 500 (98.8%)** |
| Unconstrained nearest-neighbor: avg. time vs. driver | +4.1 min **slower** |
| Unconstrained nearest-neighbor: total violations | **1,113** |

The 6 routes (1.2%) where a violation remained each had exactly one residual violation, with no correlation to route size — consistent with 2-opt being a local search method without a global optimality guarantee, not a systematic failure pattern.

## Key insight

Human drivers' real advantage isn't raw path-finding — it's *implicit constraint balancing*. A naive algorithm optimizes distance; a human optimizes *trust* (not breaking delivery promises). When we explicitly encode the constraint into the algorithm — violations first, speed second — it matches human-level reliability (98.8% zero violations) while still winning on speed in 7 of 10 routes.

**The practical implication:** the gap between human and machine route planning is not about intelligence — it's about encoding the right objective function. A human driver is not a better shortest-path solver; they are a better *prioritizer* of commitments. Build that priority into the optimizer, and the gap largely disappears.

## Scope and limitations

This project is a **retrospective, data-driven analysis** — it evaluates how the algorithm *would have* performed against historical routes, using historical ground truth. It does not claim production deployment or real-world driver usage.

A genuine rollout would require, at minimum:
- **Live A/B testing** — comparing algorithm-suggested routes against driver judgment in real conditions, not simulated ones
- **Real-time data** — this analysis uses historical average travel times; live traffic conditions change minute to minute
- **Driver adoption considerations** — whether drivers trust and follow an unfamiliar route suggestion is a separate, non-technical problem
- **A feedback loop** — capturing cases where a driver overrides the algorithm, to improve the system over time

This project is best understood as the necessary first step before such a pilot — a data-backed, quantified case for whether further investment is justified.

## Agentic AI layer

An LLM-driven orchestrator (`agent/orchestrator.py`, using Groq's `openai/gpt-oss-120b` with tool-calling) investigates a route's optimization result autonomously. Given a route ID, it decides which of 4 tools to call — fetching the route's summary, validating it against a safety guardrail, comparing it to the real human driver's performance, and searching for similar known failure cases — reasoning through each step and producing a grounded, plain-English explanation.

**Design principle: the safety guardrail is enforced in code, not by the LLM.** After every optimization result, an independent check (`validate_route`) confirms the algorithm's violation count never exceeds the untouched baseline's — this runs regardless of what the LLM concludes, so a confused or incorrect model can never cause an unsafe result to be reported as safe. Reasoning is delegated to the LLM; safety is enforced structurally. This is a genuine (if minimal) **agent harness**: it manages the tool-calling loop, executes tools with real code rather than LLM-simulated results, maintains conversation state across turns, and enforces a hard iteration limit.

Observed example: investigating a route with a residual violation, the agent correctly distinguished "guardrail passed" (algorithm ≤ baseline) from "fully resolved" (zero violations) — flagging the route as safe-but-needing-review rather than falsely claiming full success — and identified similar-sized routes with the same residual-violation pattern without being explicitly told to look for one.

Tested in `tests/test_agent_guardrail.py` — covers the guardrail passing when the algorithm improves or matches the baseline, and failing correctly if violations were ever worse than baseline.

**Honest current limitations of the harness:** no retry/error-handling for failed tool calls or API errors, no timeout enforcement, no persistent logging across sessions, and it's a single agent rather than a multi-agent system.

## Live dashboard

A single-page Streamlit dashboard (`app.py`) presents the full project: KPI summary cards, the three supporting charts (time-saved distribution, algorithm-vs-actual scatter, violation comparison), and an integrated section to run the live agent investigation on any of the 6 known failure-case routes — all in one view, using internally-scrolling panels rather than a long scrolling page.

## Code walkthrough

| Script | What it does |
|---|---|
| `scripts/01_bronze_ingestion.py` | Downloads the 5 raw JSON files from the public S3 bucket into a Databricks Volume, streamed in 8MB chunks (avoids the unreliable multi-threaded `download_file` on network-mounted storage). |
| `scripts/02_silver_transform.py` | Flattens all 5 raw files into the Silver-layer star schema. `travel_times.json` (1.7GB) is streamed route-by-route with `ijson` from a local copy, converted to pandas before Spark, and written in resumable batches of 100 routes — necessary after diagnosing a real 5,000x pandas-overhead bug. |
| `scripts/03_algorithm.py` | `nearest_neighbor_route`, `evaluate_route_plain`, and `two_opt_constrained_fast` — the core routing algorithm, with delta-based prefix caching so each candidate swap only re-simulates the changed section of the route. |
| `scripts/04_batch_evaluation.py` | Runs the full algorithm across a random, seeded 500-route sample, bulk-pulling data in 5 queries (not 2,500), and saving results in resumable batches of 25. |
| `agent/orchestrator.py` | The agentic harness: 4 tools, the tool-calling loop, and the safety guardrail. |
| `app.py` | The Streamlit dashboard. |
| `tests/test_algorithm.py` | 11 unit tests covering the routing algorithm's correctness, including a regression test confirming the delta-based optimization produces identical results to the original evaluator. |
| `tests/test_agent_guardrail.py` | 4 unit tests confirming the agent's safety guardrail logic. |

## Engineering challenges (real, and worth mentioning in interviews)

- **A 5,000x performance bug**: repeated small pandas operations (`.notna()`, comparisons, `.sum()`) on tiny 1-3 row slices had heavy fixed overhead when called millions of times; fixed by converting to plain Python tuples before the hot loop.
- **A silent correctness bug**: an early "faster" algorithm result was actually invalid — it violated delivery-time promises the human driver respected. Caught by building an explicit validation step rather than trusting a favorable-looking number.
- **Platform instability**: Databricks Free Edition serverless compute repeatedly dropped sessions, including a confirmed multi-day platform-wide outage. Solved by designing every long-running step (the 1.7GB file load, the 500-route batch run) to be resumable.
- **An O(n³) algorithmic cost**: the original 2-opt recalculated the entire route from scratch per candidate swap. Fixed with prefix caching, only re-simulating the changed suffix — verified identical to the original via a regression test.

## What's still possible to extend

- Scale beyond the 500-route sample to the full 6,112-route population.
- Parallelize the per-route algorithm loop across Spark (`applyInPandas`) instead of a single-threaded Python loop.
- A learned cost function: train a model on `actual_sequences.json` to predict which stop a driver would choose next, and use it as an additional signal inside 2-opt — this project deliberately used an agentic-AI extension instead, but this remains a natural, unexplored direction.
- Incremental/daily-load handling (e.g., Delta Lake `MERGE` by date) — not built, since there's no real recurring data source in this project to justify it, but the approach is straightforward to describe.

## Tech stack

Databricks (Free Edition, serverless) · PySpark · Delta Lake · `ijson` · pandas · SQL · Python · Groq (LLM tool-calling) · Streamlit · Plotly · pytest

## Acknowledgment

Dataset provided by Amazon.com, Inc. and MIT Center for Transportation & Logistics, released for the Amazon Last Mile Routing Research Challenge (2021).