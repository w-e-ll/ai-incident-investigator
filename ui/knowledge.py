"""Knowledge base controls; all data and provider work belong to the API."""

import json
from pathlib import Path

import streamlit as st

from core.schemas import KnowledgeChunkBatch
from scripts.queue_case import build_payload
from ui.client import APIProblem, call


def show_knowledge(tenant_id: str, config: dict) -> None:

    headers = {"X-Tenant-ID": tenant_id}

    st.subheader("Historical incident knowledge base")

    st.caption(
        "Store reviewed resolutions, then retrieve similar symptoms and fixes for the current incident."
    )

    try:
        counts = call("GET", "/api/v1/knowledge/status", headers=headers)["counts"]

        with st.container(horizontal=True):
            for state in ("queued", "embedding", "ready", "failed"):
                st.metric(state.capitalize(), counts[state], border=True)

        uploaded = st.file_uploader("Resolved incident case JSON", type=["json"], key="resolved_case")

        sample = st.checkbox("Use the reviewed synthetic resolved case")

        data = None

        if sample:
            data = json.loads(
                (Path(__file__).resolve().parents[1] / "samples/resolved_incident_case.json").read_text()
            )

        elif uploaded:
            data = json.loads(uploaded.getvalue())

        if data is not None:
            payload = KnowledgeChunkBatch.model_validate(build_payload(data, tenant_id)).model_dump(
                mode="json"
            )

            st.dataframe(payload["chunks"], hide_index=True, alt="Prepared incident sections and metadata")

            if st.button("Save case to indexing queue"):
                result = call("POST", "/api/v1/knowledge/chunks", json=payload, headers=headers)

                st.success(f"Saved {result['count']} new chunks. Identical imports are reused.")

        reviewed = st.checkbox("I reviewed the case data and permit sending redacted chunks for embeddings")

        if st.button("Index queued chunks", disabled=not reviewed or not config["live_configured"]):
            with st.spinner("Generating embeddings"):
                result = call("POST", "/api/v1/knowledge/index", headers=headers)

            st.success(f"Indexing result: {result['status']} · {result['processed']} chunks")

        if counts["embedding"]:
            st.caption(
                "Claims inactive for 15 minutes can be marked failed. Their provider billing is unknown."
            )
            if st.button("Mark stale embedding claims failed"):
                result = call("POST", "/api/v1/knowledge/recover", headers=headers)
                st.info(f"Marked {result['failed']} claims failed. Review provider usage before retrying.")

        if counts["failed"] and st.button("Requeue failed chunks"):
            result = call("POST", "/api/v1/knowledge/retry", headers=headers)

            st.success(f"Requeued {result['requeued']} chunks. Run indexing when ready.")

        with st.form("knowledge_search"):
            query = st.text_input(
                "Similar incident query", placeholder="checkout database connection timeout"
            )

            service = st.text_input("Service filter (optional)")

            environment = st.text_input("Environment filter (optional)")

            submitted = st.form_submit_button("Search historical incidents")

        if submitted and query.strip():
            filters = {k: v for k, v in {"service": service, "environment": environment}.items() if v}

            matches = call(
                "POST",
                "/api/v1/knowledge/search",
                json={"query": query, "metadata": filters, "limit": 10},
                headers=headers,
            )

            if not matches:
                st.info("No indexed cases match the query and filters.")

            for match in matches:
                with st.container(border=True):
                    st.markdown(f"**{match['case_id']} · {match['section']}**")

                    st.write(match["text"])

                    st.caption(f"RRF score: {float(match['rrf_score']):.5f} · metadata: {match['metadata']}")

    except (APIProblem, ValueError, TypeError) as exc:
        st.error(str(exc))
