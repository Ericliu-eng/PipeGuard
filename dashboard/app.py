import json
from typing import Any
import os
import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
)


st.set_page_config(
    page_title="PipeGuard",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ PipeGuard")
st.subheader("Data Pipeline Monitoring Dashboard")


def analyze_run(run_id: int) -> dict[str, Any] | None:
    try:
        response = requests.post(
            f"{API_BASE_URL}/runs/{run_id}/analyze",
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as exc:
        st.error(f"Failed to analyze pipeline run: {exc}")
        return None

def get_runs() -> list[dict[str, Any]]:
    try:
        response = requests.get(
            f"{API_BASE_URL}/runs",
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()

        if isinstance(data, list):
            return data

        st.error("Unexpected response format from GET /runs.")
        return []

    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to the FastAPI backend.")
        return []

    except requests.exceptions.RequestException as exc:
        st.error(f"Failed to load pipeline runs: {exc}")
        return []


def get_run_checks(run_id: int) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            f"{API_BASE_URL}/runs/{run_id}/checks",
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()

        if isinstance(data, list):
            return data

        st.error("Unexpected response format from checks API.")
        return []

    except requests.exceptions.RequestException as exc:
        st.error(f"Failed to load quality checks: {exc}")
        return []

def trigger_demo_run(scenario: str) -> dict[str, Any] | None:
    try:
        params = {
            "simulate_failure": scenario == "pipeline_failure",
            "data_scenario": (
                "quality_failure"
                if scenario == "quality_issue"
                else "normal"
            ),
        }
        response = requests.post(
            f"{API_BASE_URL}/runs/demo",
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as exc:
        st.error(f"Failed to trigger demo pipeline: {exc}")
        return None

st.subheader("Run Demo Pipeline")

scenario = st.selectbox(
    "Select a demo scenario",
    options=["normal", "pipeline_failure", "quality_issue"],
)

if st.button("Run Pipeline"):
    result = trigger_demo_run(scenario)

    if result is not None:
        st.success("Demo pipeline completed.")
        st.rerun()

runs = get_runs()

if not runs:
    st.warning("No pipeline runs found.")
else:
    st.success(f"Loaded {len(runs)} pipeline runs.")

    runs_df = pd.DataFrame(runs)

    total_runs = len(runs_df)
    status_series = runs_df["status"].astype(str).str.upper()

    successful_runs = (status_series == "SUCCESS").sum()
    failed_runs = (status_series == "FAILED").sum()
    success_rate = (
        successful_runs / total_runs * 100
        if total_runs > 0
        else 0
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Runs", total_runs)
    col2.metric("Success Rate", f"{success_rate:.1f}%")
    col3.metric("Successful Runs", successful_runs)
    col4.metric("Failed Runs", failed_runs)

    st.subheader("Recent Pipeline Runs")
    st.dataframe(
        runs_df,
        use_container_width=True,
        hide_index=True,
    )
    st.subheader("Quality Check Details")

    run_ids = runs_df["id"].tolist()

    selected_run_id = st.selectbox(
        "Select a pipeline run",
        options=run_ids,
    )

    checks = get_run_checks(selected_run_id)

    if not checks:
        st.info("No quality checks found for this run.")
    else:
        checks_df = pd.DataFrame(checks)

        check_status_series = checks_df["status"].astype(str).str.upper()

        passed_checks = (check_status_series == "PASS").sum()
        warned_checks = (check_status_series == "WARN").sum()
        failed_checks = (check_status_series == "FAIL").sum()

        check_col1, check_col2, check_col3 = st.columns(3)

        check_col1.metric("Passed Checks", int(passed_checks))
        check_col2.metric("Warning Checks", int(warned_checks))
        check_col3.metric("Failed Checks", int(failed_checks))

        st.dataframe(
            checks_df,
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Incident Analysis")

        if st.button("Analyze Selected Run"):
            analysis = analyze_run(selected_run_id)

            if analysis is not None:
                st.success("Incident analysis completed.")

                st.write("**Severity:**", analysis["severity"])
                st.write("**Summary:**", analysis["summary"])
                likely_causes = json.loads(analysis["likely_causes"])
                recommended_steps = json.loads(analysis["recommended_steps"])

                st.write("**Likely Causes:**")
                for cause in likely_causes:
                    st.write(f"- {cause}")

                st.write("**Recommended Steps:**")
                for step in recommended_steps:
                    st.write(f"- {step}")
                st.write("**Analysis Model:**", analysis["model_name"])


