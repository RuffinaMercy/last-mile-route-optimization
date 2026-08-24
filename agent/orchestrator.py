"""
Agentic orchestrator for the route optimization project.

Given a route_id, the agent decides which tools to call (fetch data,
validate results, compare to the human driver, find similar failure
cases) and reasons about what it finds, in plain language.

Hard guardrail (enforced in code, not just prompted): the agent can
never report a route as successfully optimized if the recorded
algorithm violations exceed the recorded nearest-neighbor (baseline)
violations. This check runs independently of what the LLM says.
"""

import os
import json
import pandas as pd
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
route_comparison = pd.read_csv(os.path.join(DATA_DIR, "route_comparison.csv"))
failure_routes = pd.read_csv(os.path.join(DATA_DIR, "failure_routes.csv"))


# ---------- Tools the agent can call ----------

def fetch_route_summary(route_id: str) -> dict:
    """Returns the full comparison record for one route."""
    row = route_comparison[route_comparison["route_id"] == route_id]
    if row.empty:
        return {"error": f"No route found with id {route_id}"}
    return row.iloc[0].to_dict()


def validate_route(route_id: str) -> dict:
    """
    Checks a route's algorithm result against its own baseline
    (nearest-neighbor) result. This is the guardrail check — it runs
    as plain code, not as an LLM judgment call.
    """
    row = route_comparison[route_comparison["route_id"] == route_id]
    if row.empty:
        return {"error": f"No route found with id {route_id}"}
    r = row.iloc[0]

    guardrail_passed = r["algo_violations"] <= r["nn_violations"]
    return {
        "route_id": route_id,
        "algo_violations": int(r["algo_violations"]),
        "baseline_violations": int(r["nn_violations"]),
        "guardrail_passed": bool(guardrail_passed),
        "status": "SAFE" if r["algo_violations"] == 0 else (
            "GUARDRAIL_OK_BUT_UNRESOLVED" if guardrail_passed else "GUARDRAIL_FAILED"
        )
    }


def compare_to_actual(route_id: str) -> dict:
    """Compares algorithm performance to the real human driver on this route."""
    row = route_comparison[route_comparison["route_id"] == route_id]
    if row.empty:
        return {"error": f"No route found with id {route_id}"}
    r = row.iloc[0]
    diff_minutes = (r["actual_time_seconds"] - r["algo_time_seconds"]) / 60
    return {
        "route_id": route_id,
        "algorithm_minutes": round(r["algo_time_seconds"] / 60, 1),
        "actual_driver_minutes": round(r["actual_time_seconds"] / 60, 1),
        "minutes_saved_by_algorithm": round(diff_minutes, 1),
        "algorithm_was_faster": bool(diff_minutes > 0)
    }


def get_similar_failure_cases(route_id: str) -> dict:
    """
    Finds other routes among the known failure cases with a similar
    number of stops, to help explain whether a given route's issue
    fits a known pattern.
    """
    row = route_comparison[route_comparison["route_id"] == route_id]
    if row.empty:
        return {"error": f"No route found with id {route_id}"}
    num_stops = row.iloc[0]["num_stops"]

    similar = failure_routes[
        (failure_routes["num_stops"] - num_stops).abs() <= 20
    ]
    return {
        "num_similar_cases_found": len(similar),
        "similar_cases": similar.to_dict(orient="records")
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_route_summary",
            "description": "Get the full comparison record for a specific route.",
            "parameters": {
                "type": "object",
                "properties": {"route_id": {"type": "string"}},
                "required": ["route_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_route",
            "description": "Check whether a route's optimization result passes the safety guardrail (never worse than the baseline).",
            "parameters": {
                "type": "object",
                "properties": {"route_id": {"type": "string"}},
                "required": ["route_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_to_actual",
            "description": "Compare the algorithm's performance to the real human driver on a route.",
            "parameters": {
                "type": "object",
                "properties": {"route_id": {"type": "string"}},
                "required": ["route_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_similar_failure_cases",
            "description": "Find other known failure-case routes similar in size to a given route.",
            "parameters": {
                "type": "object",
                "properties": {"route_id": {"type": "string"}},
                "required": ["route_id"]
            }
        }
    }
]

TOOL_FUNCTIONS = {
    "fetch_route_summary": fetch_route_summary,
    "validate_route": validate_route,
    "compare_to_actual": compare_to_actual,
    "get_similar_failure_cases": get_similar_failure_cases,
}

SYSTEM_PROMPT = """You are an orchestration agent for a delivery route optimization system.

Given a route_id, investigate it using the available tools: fetch its
summary, validate it against the safety guardrail, compare it to the
actual human driver's performance, and if it has unresolved violations,
look for similar known failure cases.

IMPORTANT: You must always call validate_route before concluding
anything about whether a route is safe. Never claim a route is safe
without having called validate_route and seeing guardrail_passed: true.

After investigating, give a clear, honest, plain-English summary:
what happened on this route, whether it's safe, how it compares to
the human driver, and if there's an unresolved issue, whether it
matches a known pattern from other failure cases.
"""


def run_agent(route_id: str, model: str = "openai/gpt-oss-120b", max_turns: int = 6):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Investigate route {route_id}."}
    ]

    print(f"\n{'='*60}\nInvestigating route: {route_id}\n{'='*60}")

    for turn in range(max_turns):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )
        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            print(f"\n--- Agent's final answer ---\n{msg.content}")
            return msg.content

        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            print(f"\n[Agent calls tool: {fn_name}({fn_args})]")

            result = TOOL_FUNCTIONS[fn_name](**fn_args)
            print(f"[Tool result: {result}]")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })

    return "Agent did not converge to a final answer within max_turns."


if __name__ == "__main__":
    # Investigate one known failure-case route, and one normal route
    example_failure_route = failure_routes.iloc[0]["route_id"]
    run_agent(example_failure_route)