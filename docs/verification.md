# Verification

## Publication verification

Prepared on 2026-10-11. Earlier dated entries below preserve the build history. Their pending states are superseded by the observations here.

The user completed real investigations with gpt-4.1-mini and exported saved reports. One saved example recorded 2,928 input tokens, 944 output tokens, one model call, and 8.73 seconds of run duration. Its configured-rate generation estimate was $0.00268160. This is one synthetic incident, not a benchmark or an invoice total.

User-provided screenshots confirm historical sections from a reviewed synthetic checkout case, completed background runs, restoration of incident and findings after browser refresh, Prometheus model and token counters, Grafana activity, and API traces returned in Tempo. The monitoring screenshots are from later runs and should not be attributed to the saved example's usage. User-run Docker verification previously reported 60 passing tests. No new Docker verification was executed during publication preparation.

Citation integrity remains separate from semantic correctness. No broad live accuracy evaluation, production load test, or authentication deployment has been completed.

## Activity-stream update — 2026-10-07

34 tests passed; the PostgreSQL integration test remained skipped in this environment. New checks cover explicit stream failures, saved/streamed contract parity, replay without repeated execution, model/tool activity callbacks, safe authentication errors, and disabled AI submission without a key. A real loopback HTTP test blocks a fake model until the client receives the model-start event, proving that progress is delivered before inference completes. Automated tests make no external provider calls.

A separate explicitly initiated live smoke run used the synthetic configuration-change sample and the project .env key. Provider requests returned authentication failure (HTTP 401); no generated live report was obtained. The effective key matched the project file and had no surrounding whitespace. Keys and provider error bodies were not printed. This establishes a provider authentication blocker, not live model quality. Replace or correct the key and recreate the API container before a new live verification.

Run default checks with no provider key and no application-database deletion:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

The tests cover bounded parsing, timezone ambiguity, multiline provenance, secret patterns, exact quotes, unseen references, report invariants, demo abstention, fake-model tool loops, call budgets, unknown usage, cost arithmetic, safe exception traces, API lifecycle/replay/errors, concurrent claims, isolated Alembic migration and Streamlit sample → report → history.

SQLite files are created in pytest temporary directories. Provider calls use a fake model, except adapter construction which needs no network. Streamlit AppTest uses an in-process API adapter and does not start a UI server. It verifies rendering and interaction logic; it is not a screenshot/layout audit.

## Optional PostgreSQL integration

Create a dedicated test database whose name ends in `_test` and a role permitted to create schemas inside it. Set `TEST_DATABASE_URL` in the test shell, not the application configuration. Then:

```powershell
uv run pytest -q -m postgres
```

The test creates a randomly named schema, runs the Alembic migration within it, exercises repository behavior, and removes only that schema. Without the variable it explicitly skips. Never point this setting at the application database. No default test uses `DATABASE_URL` for teardown.

## Initial build results

The verification environment was Windows, Python 3.13, locked dependencies in `.venv-build`, mocked model calls, and isolated local SQLite. Final results: **30 passed, 1 skipped**, Ruff check and format check pass. Compose configuration validation and offline PostgreSQL migration SQL generation pass.

Docker CLI was found outside PATH. Initially its engine pipes were unavailable; after Docker Desktop was started, the sandbox denied access to its named pipe. The permission tool could not represent that named-pipe path. Therefore Docker image execution and live PostgreSQL integration remain unverified from this chat. `scripts/run.ps1 DockerVerify` provides the concrete build/test command for the user's terminal with normal Docker access. No live provider request or measured live-model benchmark was executed. Quality rubric and input-size estimates are not evidence of production accuracy or savings.
