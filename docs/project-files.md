# File map

| File | Purpose | Maintenance |
|---|---|---|
| `core/schemas.py` | Strict domain/API contracts and report invariants | Update with API and stored snapshot changes |
| `core/parser.py` | Bounded parsing and best-effort redaction | Add formats only with provenance/privacy cases |
| `core/evidence.py` | Fingerprints, evidence selection, tokenizer estimate, citation checks | Evaluate relevance when tuning selection |
| `core/investigator.py` | Demo baseline and bounded LangGraph tool loop | Update budget, prompt and tool tests together |
| `core/settings.py` | Backend configuration | Keep secrets out of defaults/docs |
| `core/logging.py` | Safe structured event formatter and context | Test absence of sensitive exception details |
| `api/main.py` | Routes, startup, reservation/action/finalization, safe errors | Keep response models and Swagger aligned |
| `db/schema.py` | SQLAlchemy tables | Add a new migration for every durable schema change |
| `db/repository.py` | Atomic incident writes and run lifecycle | Preserve claim-before-call and immutable completion |
| `streamlit_app.py` | Upload, execution, history, export | Keep UI on HTTP boundary |
| `ui/client.py` | Safe HTTP client without POST retries | Preserve unknown-outcome run IDs |
| `ui/views.py` | Facts, hypotheses, evidence, timeline, operational/cost views | Keep metric denominators and limitations visible |
| `.streamlit/config.toml` | Native Streamlit theme/config | Avoid fragile DOM styling |
| `samples/` | Synthetic fixture files and qualitative rubric | Keep generator and expected mechanisms consistent |
| `tests/` | Domain/API/UI/privacy/persistence verification | Use isolated DB and mocked model by default |
| `migrations/` / `alembic.ini` | Versioned PostgreSQL schema | Do not rewrite an already-applied revision |
| `pyproject.toml` / `uv.lock` | Dependency/config source and resolved versions | Update together through uv |
| `.env.example` | Safe configuration sample | No real keys/passwords |
| `Dockerfile` / `compose.yaml` | Non-root app image and service readiness | Verify against a running Linux daemon |
| `docker/init-db.sh` | First-volume app-role initialization | Alembic handles existing schemas |
| `scripts/run.ps1` | Windows setup/run/test/Compose commands | Preserve existing secrets and volumes |
| `scripts/create_samples.py` | Reproducible synthetic dataset generation | Never generate real customer data |
| `README.md` / `docs/` | Launch and engineering documentation | Reflect verified behavior and known limitations |
| `VERSION.txt` / `CHANGELOG.md` | Release identity and changes | Align with project/API version |
