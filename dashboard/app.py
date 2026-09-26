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

# Streamlit reruns this whole script on every interaction, so the read endpoints are
# cached briefly to avoid refetching unchanged history. Triggering a run clears the
# cache, so the TTL only bounds how long a run started elsewhere stays invisible.
# Only successful calls are cached: an exception propagates and is rendered by the
# caller, so a transient API outage is retried on the next rerun instead of being
# cached as an empty result.
CACHE_TTL_SECONDS = 30


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_runs() -> list[dict[str, Any]]:
    response = requests.get(
        f"{API_BASE_URL}/runs",
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError("Unexpected response format from GET /runs.")

    return data


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_run_analysis(run_id: int) -> dict[str, Any] | None:
    response = requests.get(
        f"{API_BASE_URL}/runs/{run_id}/analysis",
        timeout=10,
    )

    if response.status_code == 404:
        return None

    response.raise_for_status()

    return response.json()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_run_checks(run_id: int) -> list[dict[str, Any]]:
    response = requests.get(
        f"{API_BASE_URL}/runs/{run_id}/checks",
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError("Unexpected response format from checks API.")

    return data


def clear_run_caches() -> None:
    fetch_runs.clear()
    fetch_run_checks.clear()
    fetch_run_analysis.clear()


def get_stored_analysis(run_id: int) -> dict[str, Any] | None:
    try:
        return fetch_run_analysis(run_id)

    except requests.exceptions.RequestException as exc:
        st.error(f"Failed to load incident analysis: {exc}")
        return None


def get_runs() -> list[dict[str, Any]]:
    try:
        return fetch_runs()

    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to the FastAPI backend.")
        return []

    except (requests.exceptions.RequestException, ValueError) as exc:
        st.error(f"Failed to load pipeline runs: {exc}")
        return []


def get_run_checks(run_id: int) -> list[dict[str, Any]]:
    try:
        return fetch_run_checks(run_id)

    except (requests.exceptions.RequestException, ValueError) as exc:
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
        clear_run_caches()
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

        # Read the stored analysis on every rerun so it stays visible after the
        # script reruns, rather than only right after the button is clicked.
        analysis = get_stored_analysis(selected_run_id)

        if st.button("Analyze Selected Run"):
            created = analyze_run(selected_run_id)

            if created is not None:
                analysis = created
                fetch_run_analysis.clear()
                st.success("Incident analysis completed.")

        if analysis is None:
            st.info("This run has not been analyzed yet.")
        else:
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


