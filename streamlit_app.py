"""Sunday AI Builds #4: evidence-driven investigation workbench."""

import json
import os
import re
from pathlib import Path
from uuid import uuid4

import streamlit as st

from ui.client import APIProblem, call, investigation_updates
from ui.views import show_activity, show_cost, show_monitoring, show_report, show_timeline

os.environ.setdefault("SERVICE_NAME", "ui")

st.set_page_config(page_title="AI Incident Investigator", page_icon=":material/troubleshoot:", layout="wide")
st.title("AI Incident Investigator")
st.caption("SUNDAY AI BUILDS #4 · Follow the evidence. Keep uncertainty visible.")
st.session_state.setdefault("incident", None)
st.session_state.setdefault("result", None)
st.session_state.setdefault("pending", None)

try:
    config = call("GET", "/api/v1/config")
except APIProblem as exc:
    st.error(str(exc))
    st.code("uv run uvicorn api.main:app --host 127.0.0.1 --port 8000", language="powershell")
    st.stop()

with st.sidebar:
    st.subheader("Investigation desk")
    section = st.radio(
        "Workspace",
        ["Investigate", "History & monitoring", "Knowledge base"],
        key="workspace",
        bind="query-params",
    )
    st.divider()
    st.caption(f"Storage: {config['storage']}")
    st.caption(f"Configured model: {config['model']}")
    tenant_id = st.text_input(
        "Tenant", value="demo-team", max_chars=100, key="tenant_id", bind="query-params"
    )
    try:
        kb = call("GET", "/api/v1/knowledge/status", headers={"X-Tenant-ID": tenant_id})
        counts = kb["counts"]
        st.caption(
            f"Knowledge index · ready {counts['ready']} · queued {counts['queued']} · failed {counts['failed']}"
        )
    except APIProblem:
        st.caption("Knowledge index status unavailable")
    if config["live_configured"]:
        st.badge("API key configured")
        st.caption("Provider access is verified when a model call succeeds.")
    else:
        st.error("AI unavailable — API key is missing in the backend.")
    if st.button("Check dependencies", icon=":material/monitor_heart:"):
        try:
            call("GET", "/health/db")
            st.success("API and database reachable")
        except APIProblem as exc:
            st.error(str(exc))

if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", tenant_id):
    st.error("Tenant must contain letters, numbers, dots, colons, underscores or hyphens.")
    st.stop()
if st.session_state.get("active_tenant", tenant_id) != tenant_id:
    st.session_state.incident = None
    st.session_state.result = None
    st.session_state.pending = None
    for key in ("incident_id", "run_id"):
        st.query_params.pop(key, None)
st.session_state.active_tenant = tenant_id


def remember_selection():
    """Keep only persisted identifiers in the URL, never uploaded contents."""
    incident = st.session_state.incident
    run = st.session_state.result or st.session_state.pending
    for key, value in {
        "incident_id": incident["incident_id"] if incident else None,
        "run_id": run["run_id"] if run else None,
    }.items():
        if value:
            st.query_params[key] = str(value)
        else:
            st.query_params.pop(key, None)


if not st.session_state.get("selection_restored"):
    st.session_state.selection_restored = True
    saved_incident = st.query_params.get("incident_id")
    saved_run = st.query_params.get("run_id")
    try:
        if saved_incident:
            st.session_state.incident = call(
                "GET", f"/api/v1/incidents/{saved_incident}", headers={"X-Tenant-ID": tenant_id}
            )
        if saved_run:
            status = call("GET", f"/api/v1/runs/{saved_run}/status", headers={"X-Tenant-ID": tenant_id})
            if status["status"] == "completed":
                result = call("GET", f"/api/v1/runs/{saved_run}", headers={"X-Tenant-ID": tenant_id})
                st.session_state.incident = call(
                    "GET", f"/api/v1/incidents/{result['incident_id']}", headers={"X-Tenant-ID": tenant_id}
                )
                st.session_state.result = result
            elif status["status"] in {"queued", "started"}:
                st.session_state.pending = {"run_id": saved_run}
            else:
                st.warning("The saved run failed. Review History & monitoring before starting another run.")
    except APIProblem as exc:
        st.warning(f"Could not restore the saved selection: {exc}")


if section == "Knowledge base":
    from ui.knowledge import show_knowledge

    show_knowledge(tenant_id, config)
    st.stop()

if not config["live_configured"]:
    with st.container(border=True):
        st.subheader("Connect the model to enable AI investigation")
        st.write(
            "The backend has no OPENAI_API_KEY. Log parsing works, but rule-based preview makes no AI calls."
        )
        st.write("Add the key to the project .env file, save it, then run this from the project terminal:")
        st.code(".\\scripts\\run.ps1 DockerUp", language="powershell")
        st.caption(
            "DockerUp recreates changed containers. Refresh this page afterwards. Do not paste keys into log uploads."
        )

if section == "History & monitoring":
    try:
        runs = call("GET", "/api/v1/runs", headers={"X-Tenant-ID": tenant_id})
        show_monitoring(runs)
        completed = [r for r in runs if r["status"] == "completed"]
        if completed:
            chosen = st.selectbox("Saved report", [r["run_id"] for r in completed])
            if st.button("Open investigation"):
                result = call("GET", f"/api/v1/runs/{chosen}", headers={"X-Tenant-ID": tenant_id})
                incident = call(
                    "GET", f"/api/v1/incidents/{result['incident_id']}", headers={"X-Tenant-ID": tenant_id}
                )
                st.session_state.incident, st.session_state.result = incident, result
                st.session_state.pending = None
                remember_selection()
            if st.session_state.result:
                show_report(st.session_state.result, st.session_state.incident["parsed"]["events"])
                show_cost(st.session_state.result)
    except APIProblem as exc:
        st.error(str(exc))
    st.stop()

with st.container(border=True):
    st.subheader("1 · Bring a small incident")
    left, right = st.columns(2)
    with left:
        uploaded = st.file_uploader(
            "UTF-8 log, JSONL, or incident.v1 JSON · maximum 2 MiB", type=["json", "jsonl", "log", "txt"]
        )
        if st.button("Load file", disabled=uploaded is None, icon=":material/upload:"):
            try:
                st.session_state.incident = call(
                    "POST",
                    "/api/v1/incidents",
                    headers={"X-Tenant-ID": tenant_id},
                    files={
                        "file": (uploaded.name, uploaded.getvalue(), "application/octet-stream"),
                    },
                )
                st.session_state.result, st.session_state.pending = None, None
            except APIProblem as exc:
                st.error(str(exc))
    with right:
        examples = {
            "Database timeout cascade": "db_timeout.jsonl",
            "Configuration regression": "config_change.jsonl",
            "Two independent failures": "independent_failures.jsonl",
            "Insufficient evidence": "insufficient.jsonl",
            "Text log with stack trace": "sample.log",
            "Structured production incident": "incident_v1.json",
            "Production trace and deployment cascade": "production_trace_incident.json",
        }
        sample = st.selectbox("Or use a synthetic incident", list(examples))
        if st.button("Load sample", icon=":material/science:"):
            try:
                sample_path = Path(__file__).parent / "samples" / examples[sample]
                st.session_state.incident = call(
                    "POST",
                    "/api/v1/incidents",
                    headers={"X-Tenant-ID": tenant_id},
                    files={
                        "file": (sample_path.name, sample_path.read_bytes(), "application/octet-stream"),
                    },
                )
                st.session_state.result, st.session_state.pending = None, None
            except APIProblem as exc:
                st.error(str(exc))
    with st.expander("Supported formats and privacy"):
        st.code(
            '{"timestamp":"2026-10-06T12:00:00Z","level":"ERROR",'
            '"service":"checkout","message":"DB connection timeout","trace_id":"trace-1"}',
            language="json",
        )
        st.code("2026-10-06T12:00:00Z ERROR checkout DB connection timeout", language="text")
        st.write(
            "Indented continuation lines are attached to the preceding text event. "
            "Timezone-less events stay in file order and are excluded from the timeline. "
            "Review sensitive data: redaction covers common patterns and is not comprehensive."
        )

remember_selection()
incident = st.session_state.incident
if not incident:
    st.info("Load a sample or a log file to inspect evidence and start an investigation.")
    st.stop()

parsed = incident["parsed"]
events, groups = parsed["events"], incident["groups"]
with st.container(horizontal=True):
    st.metric("Parsed events", len(events), border=True)
    st.metric("Rejected records", parsed["rejected_records"], border=True)
    st.metric("Error groups", len(groups), border=True)
    st.metric("ERROR / CRITICAL events", sum(g["count"] for g in groups), border=True)
st.caption(f"{incident['name']} · incident {incident['incident_id']}")
with st.expander("Parsing notes", expanded=bool(parsed["rejected_records"])):
    for warning in parsed["warnings"]:
        st.write(warning)
    if parsed["issues"]:
        st.json(parsed["issues"])

st.subheader("2 · Investigate")
mode = st.selectbox(
    "Mode",
    ["live", "demo"],
    key="investigation_mode",
    format_func=lambda value: (
        "AI investigation — model and evidence tools"
        if value == "live"
        else "Rule-based preview — no model calls"
    ),
)
if mode == "demo":
    st.info(
        "Preview uses fixed rules. Choose AI investigation for model-generated hypotheses and evidence checks."
    )
else:
    st.caption("Watch actual model requests, evidence checks and short decision summaries as they complete.")
with st.form("investigation", border=True):
    symptom = st.text_input(
        "Observed symptom (optional)",
        max_chars=1000,
        placeholder="Checkout requests started returning 502 after a deployment",
    )
    history_service = st.text_input("Historical service filter (optional)")
    history_environment = st.text_input("Historical environment filter (optional)")
    calls = st.slider("Maximum model calls", 1, 4, 3) if mode == "live" else 1
    reviewed = (
        st.checkbox("I reviewed the upload and permit sending redacted evidence to the model", value=False)
        if mode == "live"
        else False
    )
    background = st.checkbox("Run as a durable background job", value=False)
    submitted = st.form_submit_button(
        "Investigate",
        icon=":material/troubleshoot:",
        type="primary",
        disabled=mode == "live" and not config["live_configured"],
    )
if st.session_state.pending and st.button("Check pending job or interrupted run"):
    pending_id = st.session_state.pending["run_id"]
    try:
        status = call("GET", f"/api/v1/runs/{pending_id}/status")
        st.info(f"Run status: {status['status']}")
        if status["status"] == "completed":
            st.session_state.result = call("GET", f"/api/v1/runs/{pending_id}")
            st.session_state.pending = None
        elif status["status"] == "failed":
            st.error(f"Run failed: {status['error_code']}. Review history before starting a new run.")
            st.session_state.pending = None
        elif status["execution"]:
            st.dataframe(status["execution"], hide_index=True, alt="Saved background investigation activity")
    except APIProblem as exc:
        st.error(str(exc))

if submitted:
    if mode == "live" and not reviewed:
        st.error("Review the upload and enable consent before live investigation.")
    else:
        body = {
            "run_id": str(uuid4()),
            "mode": mode,
            "symptom": symptom,
            "max_calls": calls,
            "tenant_id": tenant_id,
            "metadata": {
                k: v for k, v in {"service": history_service, "environment": history_environment}.items() if v
            },
        }
        st.session_state.pending = body
        st.session_state.result = None
        if background:
            queued = call("POST", f"/api/v1/incidents/{incident['incident_id']}/enqueue", json=body)
            st.success(f"Job {queued['run_id']} queued. The worker will save the result.")
            remember_selection()
            st.rerun()
        activity = st.status("Starting investigation", expanded=True)
        try:
            for update in investigation_updates(incident["incident_id"], body):
                if update["type"] == "progress":
                    item = update["event"]
                    activity.update(label=item["title"])
                    with activity:
                        show_activity(item, events)
                elif update["type"] == "result":
                    st.session_state.result = update["result"]
                    st.session_state.pending = None
                    activity.update(label="Investigation saved", state="complete", expanded=False)
                else:
                    error = update["error"]
                    st.session_state.pending = None
                    raise APIProblem(f"{error['message']} [{error['code']}; request {error['request_id']}]")
        except APIProblem as exc:
            activity.update(label="Investigation interrupted", state="error", expanded=True)
            st.error(str(exc))

if st.session_state.pending:
    pending_id = st.session_state.pending["run_id"]
    st.info(f"Awaiting the saved result. Run ID: {pending_id}. Checking status does not start a new run.")
    if st.button("Check saved result before a new run"):
        try:
            status = call("GET", f"/api/v1/runs/{pending_id}/status")
            if status["status"] == "completed":
                st.session_state.result = call("GET", f"/api/v1/runs/{pending_id}")
                st.session_state.pending = None
                remember_selection()
                st.rerun()
            elif status["status"] in {"queued", "started"}:
                st.info(f"Run status: {status['status']}. The worker has not finished. Check again shortly.")
            else:
                st.error(f"Run failed: {status['error_code']}. Review history before starting another run.")
        except APIProblem as exc:
            st.error(str(exc))

remember_selection()
if st.session_state.result:
    result = st.session_state.result
    show_report(result, events)
    show_cost(result)
    st.download_button(
        "Export investigation JSON",
        json.dumps(result, ensure_ascii=False, indent=2),
        file_name=f"investigation-{result['run_id']}.json",
        mime="application/json",
    )

st.subheader("3 · Inspect the underlying evidence")
show_timeline(events, groups)
