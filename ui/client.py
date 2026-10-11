"""No automatic POST retries: unknown outcomes keep the same run ID."""

import os

import httpx

from core.schemas import InvestigationUpdate

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


class APIProblem(Exception):
    pass


def call(method: str, path: str, **kwargs):
    import streamlit as st

    selected_tenant = st.session_state.get("tenant_id", "demo-team")
    kwargs.setdefault("headers", {})
    kwargs["headers"].setdefault("X-Tenant-ID", selected_tenant)
    from core.logging import emit, setup_logging

    setup_logging()
    emit("ui.api_request", method=method)
    try:
        response = httpx.request(method, BASE_URL + path, timeout=150, **kwargs)
    except httpx.HTTPError as exc:
        raise APIProblem(
            "API connection failed. Start the backend or check run history before retrying."
        ) from exc
    if not response.is_success:
        try:
            body = response.json()
        except ValueError:
            body = {}
        raise APIProblem(
            f"{body.get('message', 'API request failed')} "
            f"[request: {body.get('request_id', 'unknown')} / {body.get('code', response.status_code)}]"
        )
    return response.json()


def investigation_updates(incident_id: str, body: dict, tenant_id: str | None = None):
    """Consume real backend updates with no POST retries or simulated delays."""
    import streamlit as st

    tenant_id = tenant_id or st.session_state.get("tenant_id", "demo-team")
    terminal = False
    try:
        with httpx.stream(
            "POST",
            BASE_URL + f"/api/v1/incidents/{incident_id}/investigate/stream",
            json=body,
            headers={"X-Tenant-ID": tenant_id},
            timeout=150,
        ) as response:
            if not response.is_success:
                raise APIProblem(
                    f"Investigation request failed (HTTP {response.status_code}). Check run history."
                )
            for line in response.iter_lines():
                if not line.strip():
                    continue
                update = InvestigationUpdate.model_validate_json(line)
                terminal = update.type in {"result", "error"}
                yield update.model_dump(mode="json")
    except httpx.HTTPError as exc:
        raise APIProblem(
            "Investigation connection interrupted. Check the saved run before starting again."
        ) from exc
    except ValueError as exc:
        raise APIProblem(
            "Invalid investigation stream received. Check the saved run before starting again."
        ) from exc
    if not terminal:
        raise APIProblem("Stream ended without a final result. Check the saved run before starting again.")
