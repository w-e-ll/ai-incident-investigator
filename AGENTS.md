# AI Incident Investigator engineering rules

- UI → HTTP API → core/repository. Provider credentials and DB access stay in backend.
- Preserve facts / hypotheses / missing evidence and strict Pydantic contracts.
- No automatic live provider calls in tests, retries after ambiguous outcomes, or secret logging.
- Reserve a run before billable work, commit outside external calls, finalize only started runs.
- Tests use isolated databases. Never drop/reset the application DB or Docker volume.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`.
- Keep README/docs/DECISIONS aligned with behavior. Distinguish mock tests, estimates and live measurements.
- PostgreSQL schema changes require a new Alembic revision after initial migration is applied.

## Project writing

For messaging, presentation text, demo narration, documentation, and meeting minutes, read `.agents/skills/plain-project-writing/SKILL.md` and its full checklist. Audit prose before delivery. Distinguish implemented, verified, estimated, and pending behavior. Preserve the engineering rules above.
