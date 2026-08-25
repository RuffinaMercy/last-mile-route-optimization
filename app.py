"""
Last-Mile Route Optimization Dashboard

Layout
------
LEFT:
    Performance
    KPIs
    Overall result
    Constraint impact

CENTER:
    Route performance charts

RIGHT:
    AI Investigator
    Route selection
    Investigation evidence
    AI conclusion

UX
--
- Browser/dashboard itself does NOT scroll.
- Each dashboard section has its own internal scroll.
- No unnecessary 500 metric in the header.
- AI Investigator gets the widest panel.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
import json


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Last-Mile Route Optimization",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ============================================================
# DATA
# ============================================================

DATA_DIR = os.path.join(
    os.path.dirname(__file__),
    "data"
)


route_comparison = pd.read_csv(
    os.path.join(
        DATA_DIR,
        "route_comparison.csv"
    )
)


failure_routes = pd.read_csv(
    os.path.join(
        DATA_DIR,
        "failure_routes.csv"
    )
)


# ============================================================
# DATA PREPARATION
# ============================================================

route_comparison["minutes_saved"] = (
    route_comparison["actual_time_seconds"]
    - route_comparison["algo_time_seconds"]
) / 60


# ============================================================
# KPI CALCULATIONS
# ============================================================

total_routes = len(
    route_comparison
)


avg_minutes_saved = (
    route_comparison["minutes_saved"].mean()
)


pct_algo_faster = (
    route_comparison["algo_time_seconds"]
    <
    route_comparison["actual_time_seconds"]
).mean() * 100


pct_zero_violations = (
    route_comparison["algo_violations"] == 0
).mean() * 100


nn_total = int(
    route_comparison[
        "nn_violations"
    ].sum()
)


algo_total = int(
    route_comparison[
        "algo_violations"
    ].sum()
)


# ============================================================
# GLOBAL CSS
#
# The important part:
#
# 1. Hide page-level vertical overflow.
# 2. Give the dashboard a viewport-based height.
# 3. Internal Streamlit containers handle scrolling.
# ============================================================

st.markdown(
    """
    <style>

        /* ====================================================
           LOCK THE MAIN APP
        ==================================================== */

        html,
        body,
        [data-testid="stAppViewContainer"],
        [data-testid="stApp"] {
            overflow: hidden !important;
        }


        /* ====================================================
           REMOVE EXCESSIVE TOP/BOTTOM SPACE
        ==================================================== */

        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0.5rem !important;

            max-width: 1600px !important;
        }


        /* ====================================================
           HEADER
        ==================================================== */

        h1 {
            margin-top: 0 !important;
            margin-bottom: 0.15rem !important;
        }


        /* ====================================================
           COLUMN SPACING
        ==================================================== */

        [data-testid="column"] {
            padding-left: 0.35rem;
            padding-right: 0.35rem;
        }


        /* ====================================================
           METRICS
        ==================================================== */

        div[data-testid="stMetric"] {
            padding-top: 0.2rem;
            padding-bottom: 0.2rem;
        }


        div[data-testid="stMetricLabel"] {
            font-size: 0.75rem;
        }


        div[data-testid="stMetricValue"] {
            font-size: 1.45rem;
        }


        /* ====================================================
           CONTAINER BORDERS
        ==================================================== */

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 10px;
        }


        /* ====================================================
           SCROLLBAR
        ==================================================== */

        ::-webkit-scrollbar {
            width: 7px;
            height: 7px;
        }

        ::-webkit-scrollbar-track {
            background: transparent;
        }

        ::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.18);
            border-radius: 10px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255,255,255,0.28);
        }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# HEADER
# ============================================================

st.title(
    "🚚 Last-Mile Route Optimization"
)


st.caption(
    "Constraint-aware routing benchmarked against real Amazon "
    "delivery drivers across **500 routes**, with AI-powered "
    "failure investigation."
)


# ============================================================
# HEADER DIVIDER
# ============================================================

st.divider()


# ============================================================
# MAIN THREE-COLUMN LAYOUT
#
# LEFT   = PERFORMANCE
# CENTER = ROUTE PERFORMANCE
# RIGHT  = AI INVESTIGATOR
# ============================================================

performance_col, route_col, agent_col = st.columns(
    [0.82, 1.45, 1.10],
    gap="medium"
)


# ################################################################
# ################################################################
#
# LEFT PANEL
# PERFORMANCE
#
# ################################################################
# ################################################################

with performance_col:

    # ------------------------------------------------------------
    # FIXED INTERNAL PANEL
    #
    # This container scrolls internally.
    # The browser does NOT scroll.
    # ------------------------------------------------------------

    with st.container(
        height=690,
        border=False
    ):

        st.subheader(
            "📊 Performance"
        )


        st.caption(
            "Overall algorithm performance across the benchmark."
        )


        # ========================================================
        # KPI 1
        # ========================================================

        with st.container(
            border=True
        ):

            st.metric(
                label="🗺️ Routes Analyzed",
                value=f"{total_routes}"
            )

            st.caption(
                "Routes included in benchmark"
            )


        # ========================================================
        # KPI 2
        # ========================================================

        with st.container(
            border=True
        ):

            st.metric(
                label="⏱️ Average Time Saved",
                value=f"{avg_minutes_saved:.1f} min"
            )

            st.caption(
                "Average improvement over actual driver"
            )


        # ========================================================
        # KPI 3
        # ========================================================

        with st.container(
            border=True
        ):

            st.metric(
                label="🏆 Algorithm Won",
                value=f"{pct_algo_faster:.1f}%"
            )

            st.caption(
                "Routes where algorithm was faster"
            )


        # ========================================================
        # KPI 4
        # ========================================================

        with st.container(
            border=True
        ):

            st.metric(
                label="✅ Zero Violations",
                value=f"{pct_zero_violations:.1f}%"
            )

            st.caption(
                "Routes with no algorithm violations"
            )


        # ========================================================
        # OVERALL RESULT
        # ========================================================

        st.markdown(
            "### Overall Result"
        )


        with st.container(
            border=True
        ):

            if pct_zero_violations >= 95:

                st.success(
                    f"{pct_zero_violations:.1f}% of routes "
                    "finished with zero violations."
                )

            else:

                st.warning(
                    f"{pct_zero_violations:.1f}% of routes "
                    "finished with zero violations."
                )


            st.write(
                f"The algorithm was faster than the human "
                f"driver on **{pct_algo_faster:.1f}%** of routes, "
                f"with an average saving of "
                f"**{avg_minutes_saved:.1f} minutes**."
            )


        # ========================================================
        # CONSTRAINT IMPACT
        # ========================================================

        st.markdown(
            "### Constraint Impact"
        )


        with st.container(
            border=True
        ):

            st.metric(
                "Unconstrained Violations",
                f"{nn_total}"
            )


            st.metric(
                "Constrained Violations",
                f"{algo_total}"
            )


            if algo_total < nn_total:

                reduction = (
                    (nn_total - algo_total)
                    / nn_total
                    * 100
                )

                st.success(
                    f"{reduction:.1f}% reduction in violations."
                )


# ################################################################
# ################################################################
#
# CENTER PANEL
# ROUTE PERFORMANCE
#
# ################################################################
# ################################################################

with route_col:

    # ------------------------------------------------------------
    # INTERNAL SCROLLING PANEL
    # ------------------------------------------------------------

    with st.container(
        height=690,
        border=False
    ):

        st.subheader(
            "📈 Route Performance"
        )


        st.caption(
            "Algorithm vs. human performance and constraint behavior."
        )


        # ========================================================
        # PRIMARY CHART
        # ========================================================

        with st.container(
            border=True
        ):

            st.markdown(
                "**Algorithm vs. Actual Driver**"
            )


            st.caption(
                "Points below the diagonal represent routes "
                "where the algorithm was faster."
            )


            fig_scatter = px.scatter(

                route_comparison,

                x=(
                    route_comparison[
                        "algo_time_seconds"
                    ] / 60
                ),

                y=(
                    route_comparison[
                        "actual_time_seconds"
                    ] / 60
                ),

                color="num_stops",

                color_continuous_scale="Blues",

                labels={
                    "x": "Algorithm (minutes)",
                    "y": "Actual Driver (minutes)",
                    "num_stops": "Stops"
                },

                hover_data=[
                    "route_id",
                    "num_stops",
                    "minutes_saved",
                    "algo_violations"
                ]

            )


            max_val = max(

                (
                    route_comparison[
                        "algo_time_seconds"
                    ] / 60
                ).max(),

                (
                    route_comparison[
                        "actual_time_seconds"
                    ] / 60
                ).max()

            )


            fig_scatter.add_shape(

                type="line",

                x0=0,
                y0=0,

                x1=max_val,
                y1=max_val,

                line=dict(
                    color="red",
                    dash="dash"
                )

            )


            fig_scatter.update_layout(

                height=350,

                margin=dict(
                    t=10,
                    b=10,
                    l=10,
                    r=10
                ),

                paper_bgcolor="rgba(0,0,0,0)",

                plot_bgcolor="rgba(0,0,0,0)"

            )


            st.plotly_chart(

                fig_scatter,

                use_container_width=True,

                config={
                    "displayModeBar": False
                }

            )


        # ========================================================
        # MINUTES SAVED
        # ========================================================

        with st.container(
            border=True
        ):

            st.markdown(
                "**Distribution of Minutes Saved**"
            )


            fig_hist = px.histogram(

                route_comparison,

                x="minutes_saved",

                nbins=25,

                labels={
                    "minutes_saved": "Minutes Saved"
                }

            )


            fig_hist.add_vline(

                x=0,

                line_dash="dash",

                line_color="red"

            )


            fig_hist.update_yaxes(
                rangemode="tozero"
            )


            fig_hist.update_layout(

                height=270,

                margin=dict(
                    t=10,
                    b=10,
                    l=10,
                    r=10
                ),

                xaxis_title="Minutes Saved",

                yaxis_title="Routes",

                paper_bgcolor="rgba(0,0,0,0)",

                plot_bgcolor="rgba(0,0,0,0)"

            )


            st.plotly_chart(

                fig_hist,

                use_container_width=True,

                config={
                    "displayModeBar": False
                }

            )


        # ========================================================
        # CONSTRAINT VIOLATIONS
        # ========================================================

        with st.container(
            border=True
        ):

            st.markdown(
                "**Constraint Violations**"
            )


            st.caption(
                "Lower is better."
            )


            fig_bar = go.Figure(

                data=[

                    go.Bar(

                        x=[
                            "Unconstrained",
                            "Constrained"
                        ],

                        y=[
                            nn_total,
                            algo_total
                        ],

                        marker_color=[
                            "#e34948",
                            "#1baf7a"
                        ],

                        text=[
                            str(nn_total),
                            str(algo_total)
                        ],

                        textposition="outside"

                    )

                ]

            )


            fig_bar.update_layout(

                height=270,

                margin=dict(
                    t=20,
                    b=10,
                    l=10,
                    r=10
                ),

                yaxis_title="Total Violations",

                paper_bgcolor="rgba(0,0,0,0)",

                plot_bgcolor="rgba(0,0,0,0)"

            )


            st.plotly_chart(

                fig_bar,

                use_container_width=True,

                config={
                    "displayModeBar": False
                }

            )


# ################################################################
# ################################################################
#
# RIGHT PANEL
# AI INVESTIGATOR
#
# ################################################################
# ################################################################

with agent_col:

    # ------------------------------------------------------------
    # INTERNAL SCROLLING PANEL
    # ------------------------------------------------------------

    with st.container(
        height=690,
        border=False
    ):

        st.subheader(
            "🤖 AI Investigator"
        )


        st.caption(
            "Investigate individual routes and understand "
            "why an optimization result occurred."
        )


        # ========================================================
        # ROUTE SELECTOR
        # ========================================================

        selected_route = st.selectbox(

            "Route",

            failure_routes[
                "route_id"
            ].tolist()

        )


        # ========================================================
        # INVESTIGATE BUTTON
        # ========================================================

        run_clicked = st.button(

            "🔍 Investigate Route",

            type="primary",

            use_container_width=True

        )


        # ========================================================
        # TOOL DEFINITIONS
        # ========================================================

        TOOL_ICONS = {

            "fetch_route_summary":
                "📥",

            "validate_route":
                "🛡️",

            "compare_to_actual":
                "⚖️",

            "get_similar_failure_cases":
                "🔎"

        }


        TOOL_LABELS = {

            "fetch_route_summary":
                "Route Data",

            "validate_route":
                "Safety Check",

            "compare_to_actual":
                "Human Comparison",

            "get_similar_failure_cases":
                "Similar Cases"

        }


        # ========================================================
        # AGENT EXECUTION
        # ========================================================

        if run_clicked:

            # ----------------------------------------------------
            # AGENT DIRECTORY
            # ----------------------------------------------------

            agent_directory = os.path.join(

                os.path.dirname(__file__),

                "agent"

            )


            if agent_directory not in sys.path:

                sys.path.insert(

                    0,

                    agent_directory

                )


            # ----------------------------------------------------
            # IMPORT AGENT
            # ----------------------------------------------------

            from orchestrator import (

                TOOLS,

                TOOL_FUNCTIONS,

                SYSTEM_PROMPT,

                client

            )


            # ----------------------------------------------------
            # INITIAL MESSAGES
            # ----------------------------------------------------

            messages = [

                {
                    "role": "system",

                    "content":
                        SYSTEM_PROMPT

                },

                {
                    "role": "user",

                    "content":
                        f"Investigate route {selected_route}."

                }

            ]


            final_answer = None

            tool_results = []


            # ----------------------------------------------------
            # RUN AGENT
            # ----------------------------------------------------

            with st.spinner(
                "🤖 Investigating..."
            ):

                for _ in range(6):

                    response = client.chat.completions.create(

                        model="openai/gpt-oss-120b",

                        messages=messages,

                        tools=TOOLS,

                        tool_choice="auto"

                    )


                    msg = response.choices[0].message


                    messages.append(
                        msg
                    )


                    # --------------------------------------------
                    # FINAL ANSWER
                    # --------------------------------------------

                    if not msg.tool_calls:

                        final_answer = msg.content

                        break


                    # --------------------------------------------
                    # TOOL CALLS
                    # --------------------------------------------

                    for tool_call in msg.tool_calls:

                        fn_name = (
                            tool_call.function.name
                        )


                        fn_args = json.loads(

                            tool_call.function.arguments

                        )


                        result = TOOL_FUNCTIONS[fn_name](

                            **fn_args

                        )


                        tool_results.append(

                            (
                                fn_name,
                                result
                            )

                        )


                        messages.append(

                            {

                                "role": "tool",

                                "tool_call_id":
                                    tool_call.id,

                                "content":
                                    json.dumps(result)

                            }

                        )


        # ========================================================
        # INVESTIGATION RESULTS
        # ========================================================

        if run_clicked:

            st.markdown(
                "#### Investigation Evidence"
            )


            if tool_results:

                for fn_name, result in tool_results:

                    icon = TOOL_ICONS.get(
                        fn_name,
                        "🔧"
                    )


                    label = TOOL_LABELS.get(
                        fn_name,
                        fn_name
                    )


                    # ==========================================
                    # ERROR
                    # ==========================================

                    if "error" in result:

                        st.error(

                            f"{icon} {label}\n\n"
                            f"{result['error']}"

                        )


                    # ==========================================
                    # ROUTE DATA
                    # ==========================================

                    elif fn_name == (
                        "fetch_route_summary"
                    ):

                        with st.container(
                            border=True
                        ):

                            st.markdown(
                                f"**{icon} {label}**"
                            )


                            c1, c2, c3 = st.columns(3)


                            with c1:

                                st.metric(
                                    "Stops",
                                    result[
                                        "num_stops"
                                    ]
                                )


                            with c2:

                                st.metric(
                                    "Baseline",
                                    result[
                                        "nn_violations"
                                    ]
                                )


                            with c3:

                                st.metric(
                                    "Algorithm",
                                    result[
                                        "algo_violations"
                                    ]
                                )


                    # ==========================================
                    # SAFETY CHECK
                    # ==========================================

                    elif fn_name == (
                        "validate_route"
                    ):

                        with st.container(
                            border=True
                        ):

                            st.markdown(
                                f"**{icon} {label}**"
                            )


                            status = result[
                                "status"
                            ]


                            if status == "SAFE":

                                st.success(
                                    "🟢 SAFE"
                                )


                            elif status == (
                                "GUARDRAIL_OK_BUT_UNRESOLVED"
                            ):

                                st.warning(
                                    "🟡 NEEDS REVIEW"
                                )


                            elif status == (
                                "GUARDRAIL_FAILED"
                            ):

                                st.error(
                                    "🔴 GUARDRAIL FAILED"
                                )


                            else:

                                st.info(
                                    status
                                )


                            c1, c2 = st.columns(2)


                            with c1:

                                st.metric(
                                    "Algorithm Violations",
                                    result[
                                        "algo_violations"
                                    ]
                                )


                            with c2:

                                st.metric(
                                    "Baseline Violations",
                                    result[
                                        "baseline_violations"
                                    ]
                                )


                    # ==========================================
                    # HUMAN COMPARISON
                    # ==========================================

                    elif fn_name == (
                        "compare_to_actual"
                    ):

                        with st.container(
                            border=True
                        ):

                            st.markdown(
                                f"**{icon} {label}**"
                            )


                            c1, c2, c3 = st.columns(3)


                            with c1:

                                st.metric(

                                    "Algorithm",

                                    (
                                        f'{result["algorithm_minutes"]}'
                                        ' min'
                                    )

                                )


                            with c2:

                                st.metric(

                                    "Human",

                                    (
                                        f'{result["actual_driver_minutes"]}'
                                        ' min'
                                    )

                                )


                            with c3:

                                st.metric(

                                    "Saved",

                                    (
                                        f'{result["minutes_saved_by_algorithm"]}'
                                        ' min'
                                    )

                                )


                    # ==========================================
                    # SIMILAR CASES
                    # ==========================================

                    elif fn_name == (
                        "get_similar_failure_cases"
                    ):

                        with st.container(
                            border=True
                        ):

                            st.markdown(
                                f"**{icon} {label}**"
                            )


                            st.write(

                                "Found "
                                f'**{result["num_similar_cases_found"]}** '
                                "similar failure case(s)."

                            )


            else:

                st.info(
                    "No investigation evidence returned."
                )


            # ====================================================
            # AI CONCLUSION
            # ====================================================

            if final_answer:

                st.divider()


                st.markdown(
                    "#### 🧠 AI Conclusion"
                )


                st.write(
                    final_answer
                )


        # ========================================================
        # INITIAL AGENT STATE
        # ========================================================

        else:

            with st.container(
                border=True
            ):

                st.markdown(
                    "### 🟢 Agent Ready"
                )


                st.write(
                    "Choose a route and start an investigation."
                )


                st.divider()


                st.markdown(
                    "#### What the agent checks"
                )


                st.write(
                    "📥 **Route Data**"
                )

                st.caption(
                    "Stops, baseline violations and algorithm violations."
                )


                st.write(
                    "🛡️ **Safety Check**"
                )

                st.caption(
                    "Whether the optimized route satisfies the guardrail."
                )


                st.write(
                    "⚖️ **Human Comparison**"
                )

                st.caption(
                    "Algorithm time versus actual driver time."
                )


                st.write(
                    "🔎 **Similar Cases**"
                )

                st.caption(
                    "Routes with similar failure patterns."
                )


                st.write(
                    "🧠 **AI Conclusion**"
                )

                st.caption(
                    "An explanation combining all available evidence."
                )