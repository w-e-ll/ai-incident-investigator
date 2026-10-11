import json
import logging

from core.logging import Formatter, request_id


def test_safe_traceback_does_not_include_exception_payload():
    try:
        raise RuntimeError("password=private-secret")
    except RuntimeError as exc:
        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1, "operation.failed", (), (type(exc), exc, exc.__traceback__)
        )
    token = request_id.set("test-request")
    try:
        text = Formatter().format(record)
    finally:
        request_id.reset(token)
    payload = json.loads(text)
    assert payload["request_id"] == "test-request"
    assert payload["stack"] and payload["exception_type"] == "RuntimeError"
    assert "private-secret" not in text


def test_module_log_contains_source_and_rotates(tmp_path):
    from core.logging import ModuleFiles

    handler = ModuleFiles(tmp_path, Formatter())
    record = logging.LogRecord("test", logging.INFO, "/core/investigator.py", 42, "model.completed", (), None)
    handler.handle(record)
    handler.close()
    payload = json.loads((tmp_path / "investigator.log").read_text(encoding="utf-8"))
    assert payload["file"] == "investigator.py"
    assert payload["line"] == 42
