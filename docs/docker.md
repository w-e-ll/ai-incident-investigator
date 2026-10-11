# Docker and PostgreSQL

Prerequisites: Docker Desktop with Linux engine, Compose v2, and accessible image registries. Copy `.env.example` to `.env` only if it does not exist. Set strong separate `POSTGRES_ADMIN_PASSWORD` and `APP_DB_PASSWORD`; use URL-safe app-password characters for the Compose DSN.

The initial DB script creates a non-superuser `investigator` role. Bootstrap runs only on a new named volume. Existing schemas are upgraded with Alembic, not by re-running initialization SQL. `db` healthy → `migrate` completed → `api` healthy → `ui`. DB is not exposed on the host; API and UI ports bind to loopback.

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail 100 api
docker compose --profile tests run --rm tests
docker compose down
```

The `tests` container executes mocked/SQLite tests and a real PostgreSQL test in the separate `incidents_test` database created on first-volume initialization. The PostgreSQL test creates and removes only its own random schema. Run `./scripts/run.ps1 DockerVerify` from a terminal with Docker engine access. An older volume created before test-database provisioning needs a separately created test database; do not reset the volume.

`postgres_data` persists under the PostgreSQL 18 image data root `/var/lib/postgresql`. `down` keeps it. Never remove that volume to fix readiness or password issues. Changing a password in `.env` does not update an existing database role: rotate it explicitly and update connection configuration together.

## Native PostgreSQL

Set `DATABASE_URL=postgresql+psycopg://<app-user>:<url-encoded-password>@127.0.0.1:<port>/<database>` and run `uv run alembic upgrade head` before starting API. Use an app role with schema privileges, not a superuser.

## Backup / restore

For local SQLite, stop API writes before copying `var/incidents.db` to a protected backup destination. For PostgreSQL, use `pg_dump -Fc` with a configured connection and restore into a separate database with `pg_restore`. Verify incident counts, run counts, and sample report retrieval after restore. Do not write backup commands that expose the password on screen or commit dumps containing uploaded data. No backup/restore drill has been executed for this initial build.

## Troubleshooting

`DockerVerify` starts the database/migration and executes tests; it does not start the application UI. Run `./scripts/run.ps1 DockerUp` afterwards. DockerUp builds the explicit `runtime` stage for migrate/API/UI and waits for service health before reporting the URL. The `tests` stage is used only by the tests service. Without an explicit target, Docker builds the final stage, which would make the API execute pytest instead of starting Uvicorn.

If port 8501 refuses connections, run `./scripts/run.ps1 DockerStatus` to display service states and recent migration/API/UI logs. An exited migration container is expected only when its exit code is 0. DockerUp prints the same diagnostic information automatically when startup fails. Existing database volumes are preserved during rebuilds.

If the CLI is absent from PATH on Windows, its installation may be under Docker Desktop resources/bin. A missing `docker_engine` or `dockerDesktopLinuxEngine` pipe means the chosen engine is unavailable: start Docker Desktop and select the appropriate context. Permission denial reading Docker config is separate from engine readiness. Do not change user Docker configuration to work around this silently.

Container builds and live PostgreSQL execution remain unverified when the daemon is unavailable. Local SQLite is an explicit fallback, not proof that the PostgreSQL deployment works.
