"""Durable Postgres/SQLite investigation worker. Never replay started paid calls."""

import argparse
import signal
from threading import Event
from uuid import UUID

from core.logging import emit, logger, setup_logging
from core.schemas import InvestigationError, RunRequest
from core.service import execute_investigation
from core.settings import Settings
from db.repository import Repository


def process_jobs(repository: Repository, settings: Settings) -> int:
    processed = 0
    for row in repository.queued_runs():
        try:
            execute_investigation(
                settings,
                UUID(row["incident_id"]),
                RunRequest.model_validate(row["config"]),
                repository,
                from_queue=True,
            )
            processed += 1
        except InvestigationError as exc:
            emit("worker.job_failed", code=exc.code, job_id=row["id"])
        except Exception:
            logger.exception("worker.job_failed")
    return processed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    setup_logging()
    from core.telemetry import configure_telemetry

    configure_telemetry()
    settings = Settings()
    repository = Repository(settings.database_url)
    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    try:
        while not stopped.is_set():
            process_jobs(repository, settings)
            if args.once:
                break
            stopped.wait(2)
    finally:
        repository.engine.dispose()


if __name__ == "__main__":
    main()
