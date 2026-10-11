"""Safe JSON logs to stdout and rotating per-service files."""

import json
import logging
import os
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

request_id: ContextVar[str] = ContextVar("request_id", default="")
run_id: ContextVar[str] = ContextVar("run_id", default="")
ALLOWED = {
    "duration_ms",
    "status",
    "code",
    "mode",
    "events",
    "rejected",
    "call",
    "model",
    "input_tokens",
    "output_tokens",
    "name",
    "matched",
    "incident_id",
    "route",
    "method",
    "tenant_id",
    "attempt",
    "job_id",
    "queue_depth",
    "billing_status",
    "latency_ms",
}


class Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": os.getenv("SERVICE_NAME", "app"),
            "module": record.module,
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
            "event": record.getMessage(),
            "request_id": request_id.get(),
            "run_id": run_id.get(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info and record.exc_info[2]:
            payload["exception_type"] = record.exc_info[0].__name__
            payload["stack"] = [
                {
                    "file": f.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
                    "line": f.lineno,
                    "function": f.name,
                }
                for f in traceback.extract_tb(record.exc_info[2])
            ]
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger("incident_investigator")


class ModuleFiles(logging.Handler):
    """One rotating file per service and Python source module, within one process."""

    def __init__(self, directory: Path, formatter: logging.Formatter):
        super().__init__()
        self.directory = directory
        self.formatter = formatter
        self.files = {}

    def emit(self, record):
        module = Path(record.pathname).stem
        if module not in self.files:
            if len(self.files) >= 32:
                return
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(
                    self.directory / f"{module}.log",
                    maxBytes=5 * 1024 * 1024,
                    backupCount=3,
                    encoding="utf-8",
                )
                handler.setFormatter(self.formatter)
                self.files[module] = handler
            except OSError:
                return
        self.files[module].handle(record)

    def close(self):
        for handler in self.files.values():
            handler.close()
        super().close()


def setup_logging() -> None:
    if logger.handlers:
        return
    formatter = Formatter()
    stdout = logging.StreamHandler()
    stdout.setFormatter(formatter)
    logger.addHandler(stdout)
    log_dir = Path(os.getenv("LOG_DIR", "var/logs"))
    service = os.getenv("SERVICE_NAME", "app")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / f"{service}.log", maxBytes=20 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
    except OSError:
        file_handler = None
    if file_handler is not None:
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(ModuleFiles(log_dir / service, formatter))
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False


def emit(event: str, **fields) -> None:
    from core.telemetry import record_event

    record_event(event, fields)
    logger.info(event, stacklevel=2, extra={"fields": {k: v for k, v in fields.items() if k in ALLOWED}})
