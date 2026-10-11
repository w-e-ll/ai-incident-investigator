FROM python:3.13-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY core core
COPY db db
COPY api api
COPY ui ui
COPY scripts scripts
COPY migrations migrations
COPY samples samples
COPY .streamlit .streamlit
COPY streamlit_app.py worker.py alembic.ini ./
RUN useradd --create-home appuser && mkdir -p var && chown -R appuser:appuser /app
USER appuser
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS tests
USER root
RUN uv sync --frozen
COPY tests tests
RUN chown -R appuser:appuser /app
USER appuser
CMD ["pytest", "-q"]
