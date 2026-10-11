"""Native UI components for traceable reports and sample-scoped operational metrics."""

import altair as alt
import pandas as pd
import streamlit as st


def evidence(ids: list[str], events: list[dict]) -> None:
    by_id = {e["id"]: e for e in events}
    for evidence_id in ids:
        event = by_id.get(evidence_id)
        if event:
            st.caption(
                f"{evidence_id} · lines {event['line_start']}–{event['line_end']} · {event['service']}"
            )
            st.code(event["source"], language="text")


def show_report(result: dict, events: list[dict]) -> None:
    report = result["report"]
    st.subheader("Investigation findings")
    if result["mode"] == "demo":
        st.warning("Rule-based preview — no model was called. These hypotheses come from templates.")
    else:
        st.caption(
            f"AI investigation · {result['metrics']['model']} · {result['metrics']['llm_calls']} model calls"
        )
    st.badge(report["conclusion"].replace("_", " "), icon=":material/search:")
    st.write(report["summary"])
    st.caption("Citation validation checks references and quotes. It does not prove that a claim is true.")
    matches = result["metrics"].get("historical_matches", [])
    if matches:
        with st.expander(f"Historical matches used ({len(matches)})"):
            st.caption("Historical cases are comparative context, not current incident proof.")
            st.dataframe(
                matches, hide_index=True, alt="Historical incident matches used as comparative context"
            )
    checks = result["metrics"].get("evaluation", [])
    if checks:
        with st.expander("Input and report evaluation"):
            st.dataframe(checks, hide_index=True, alt="Executed evaluation checks and limitations")
    facts, hypotheses, missing = st.tabs(["Facts", "Hypotheses", "Missing evidence"])
    with facts:
        for number, fact in enumerate(report["facts"], 1):
            with st.container(border=True):
                st.markdown(f"**{number}. {fact['statement']}**")
                with st.expander("Inspect cited evidence"):
                    evidence([c["event_id"] for c in fact["evidence"]], events)
    with hypotheses:
        if not report["hypotheses"]:
            st.info("No supported hypothesis could be proposed.")
        for hypothesis in report["hypotheses"]:
            with st.container(border=True):
                st.markdown(f"**{hypothesis['id']} · {hypothesis['support']} support**")
                st.write(hypothesis["explanation"])
                st.caption(hypothesis["rationale"])
                st.markdown("**Alternatives**")
                for alternative in hypothesis["alternatives"]:
                    st.write(f"- {alternative}")
                with st.expander("Supporting evidence"):
                    evidence(hypothesis["supporting_evidence_ids"], events)
                if hypothesis["contradicting_evidence_ids"]:
                    with st.expander("Contradicting evidence"):
                        evidence(hypothesis["contradicting_evidence_ids"], events)
    with missing:
        for item in report["missing_evidence"]:
            with st.container(border=True):
                st.markdown(f"**{item['hypothesis_id'] or 'Investigation'} · {item['needed']}**")
                st.write(item["next_check"])
    with st.expander("Limitations and execution steps"):
        for limitation in report["limitations"]:
            st.write(f"- {limitation}")
        st.code(" → ".join(result["metrics"]["steps"]), language="text")
    if result["metrics"].get("execution"):
        with st.expander("Investigation activity — recorded actions and decision summaries"):
            for item in result["metrics"]["execution"]:
                show_activity(item, events)


def show_activity(item: dict, events: list[dict]) -> None:
    st.markdown(f"**{item['sequence']}. {item['title']}** · {item['elapsed_ms'] / 1000:.2f}s")
    st.write(item["detail"])
    if item.get("evidence_ids"):
        with st.expander(f"Inspect {len(item['evidence_ids'])} selected evidence events"):
            evidence(item["evidence_ids"], events)


def show_timeline(events: list[dict], groups: list[dict]) -> None:
    timeline, errors, source = st.tabs(["Timeline", "Error groups", "Evidence explorer"])
    with timeline:
        timed = [e for e in events if e["timestamp"]]
        st.caption(
            "UTC timestamps from uploaded data. Clock skew and collection gaps can change apparent order."
        )
        if timed:
            frame = pd.DataFrame(timed)
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
            chart = (
                alt.Chart(frame)
                .mark_circle(size=90)
                .encode(
                    x=alt.X("timestamp:T", title="Time (UTC)", scale=alt.Scale(type="utc")),
                    y=alt.Y("service:N", title="Service"),
                    color=alt.Color(
                        "level:N",
                        scale=alt.Scale(
                            domain=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN"],
                            range=["#8c96a8", "#38bdf8", "#fbbf24", "#fb7185", "#c084fc", "#94a3b8"],
                        ),
                    ),
                    tooltip=["timestamp:T", "service:N", "level:N", "message:N", "id:N"],
                )
                .interactive()
            )
            st.altair_chart(chart, alt="Incident events over time, grouped by service and severity")
        else:
            st.info("No timezone-aware timestamps. Inspect events in file order below.")
        st.caption(f"{len(events) - len(timed)} events excluded from timeline because time is unknown.")
    with errors:
        if groups:
            st.dataframe(
                pd.DataFrame(groups).drop(columns="evidence_ids"),
                hide_index=True,
                alt="Error groups with counts and first and last timestamps",
            )
            group_id = st.selectbox("Inspect group", [g["id"] for g in groups])
            group = next(g for g in groups if g["id"] == group_id)
            evidence(group["evidence_ids"][:20], events)
            st.caption("Showing at most 20 examples per group.")
        else:
            st.info("No ERROR or CRITICAL events were found.")
    with source:
        services = sorted({e["service"] for e in events})
        selected_services = st.multiselect("Services", services, default=services)
        query = st.text_input("Literal search in messages")
        filtered = [
            e
            for e in events
            if e["service"] in selected_services and query.casefold() in e["message"].casefold()
        ]
        st.caption(f"{len(filtered)} matching events · showing first 300 in file order")
        st.dataframe(pd.DataFrame(filtered[:300]), hide_index=True, alt="Filtered incident evidence")
        options = [e["id"] for e in filtered[:300]]
        if options:
            selected_id = st.selectbox("Open source event", options)
            evidence([selected_id], events)


def show_cost(result: dict) -> None:
    metrics = result["metrics"]
    st.subheader("Cost and optimization")
    with st.container(horizontal=True):
        st.metric("LLM calls", metrics["llm_calls"], border=True)
        st.metric("Tool calls", len(metrics["tool_calls"]), border=True)
        st.metric("Duration", f"{metrics['duration_ms'] / 1000:.2f}s", border=True)
        st.metric(
            "Estimated usage cost",
            f"${metrics['cost_usd']}" if metrics["cost_usd"] is not None else "Unknown",
            border=True,
        )
    raw, pack = metrics["raw_log_tokens_estimate"], metrics["evidence_pack_tokens_estimate"]
    reduction = (1 - pack / raw) * 100 if raw else 0
    st.write(
        f"Full redacted log: **{raw:,}** estimated tokens · initial evidence pack: "
        f"**{pack:,}** · change: **{reduction:+.1f}% reduction**"
    )
    st.caption(
        "Tokenizer estimate for initial input only. Pack overhead can increase size on small files. "
        "This is not measured dollar savings; tool rounds and output add cost."
    )
    st.write(
        f"Investigator saw {metrics['evidence_events']} of {metrics['total_events']} events initially "
        "or through tools. Reduced context may miss evidence."
    )
    if metrics["usage"]:
        st.dataframe(
            pd.DataFrame(metrics["usage"]), hide_index=True, alt="Per-call model token usage and latency"
        )
    if metrics["price_snapshot"]:
        st.json(metrics["price_snapshot"])
    else:
        st.caption(
            "Live cost remains unknown until model-specific input/output prices and date are configured."
        )


def show_monitoring(runs: list[dict]) -> None:
    st.subheader("Application monitoring")
    st.caption(
        "Local run history, latest 100 records. This is not external uptime monitoring or an SLO dashboard."
    )
    if not runs:
        st.info("No investigations yet.")
        return
    failed = sum(r["status"] == "failed" for r in runs)
    started = sum(r["status"] in {"queued", "started"} for r in runs)
    durations = [
        r["duration_ms"] for r in runs if r["status"] == "completed" and r["duration_ms"] is not None
    ]
    frame = pd.DataFrame(runs)
    st.caption(f"Window: {frame['created_at'].min()} → {frame['created_at'].max()}")
    with st.container(horizontal=True):
        st.metric("Recorded runs", len(runs), border=True)
        st.metric("Failed / all runs", f"{failed}/{len(runs)} ({failed / len(runs):.0%})", border=True)
        st.metric("Queued / started", started, border=True)
        st.metric(
            "Completed p95",
            f"{pd.Series(durations).quantile(0.95) / 1000:.2f}s" if durations else "—",
            border=True,
        )
    st.dataframe(frame, hide_index=True, alt="Recent investigations and their statuses")
