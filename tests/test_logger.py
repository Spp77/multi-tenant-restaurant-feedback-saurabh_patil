"""
Unit Tests: Logger utility (tests/test_logger.py)
Covers JsonFormatter output shape and get_logger() behaviour.
"""
import json
import logging
import pytest
from src.utils.logger import get_logger, JsonFormatter


class TestJsonFormatter:
    def _make_record(self, message="test message", level=logging.INFO, name="test.logger"):
        record = logging.LogRecord(
            name=name,
            level=level,
            pathname="test_logger.py",
            lineno=42,
            msg=message,
            args=(),
            exc_info=None,
        )
        return record

    def test_output_is_valid_json(self):
        formatter = JsonFormatter()
        record = self._make_record()
        output = formatter.format(record)
        parsed = json.loads(output)   # raises if invalid JSON
        assert isinstance(parsed, dict)

    def test_output_contains_required_fields(self):
        formatter = JsonFormatter()
        record = self._make_record("hello world")
        parsed = json.loads(formatter.format(record))
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "message" in parsed
        assert "module" in parsed
        assert "function" in parsed
        assert "line" in parsed

    def test_message_is_correct(self):
        formatter = JsonFormatter()
        record = self._make_record("Pizza order received")
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "Pizza order received"

    def test_level_name_is_correct(self):
        formatter = JsonFormatter()
        record = self._make_record(level=logging.WARNING)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "WARNING"

    def test_logger_name_is_correct(self):
        formatter = JsonFormatter()
        record = self._make_record(name="src.api.feedback_handler")
        parsed = json.loads(formatter.format(record))
        assert parsed["logger"] == "src.api.feedback_handler"

    def test_exception_info_is_included_when_present(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("something went wrong")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = self._make_record()
        record.exc_info = exc_info
        parsed = json.loads(formatter.format(record))
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]


class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)

    def test_logger_has_correct_name(self):
        logger = get_logger("src.storage.dynamodb_client")
        assert logger.name == "src.storage.dynamodb_client"

    def test_logger_level_is_info_by_default(self):
        logger = get_logger("test.default.level")
        assert logger.level == logging.INFO

    def test_logger_level_can_be_overridden(self):
        logger = get_logger("test.debug.level", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_logger_does_not_propagate(self):
        logger = get_logger("test.no.propagate")
        assert logger.propagate is False

    def test_logger_has_stream_handler(self):
        logger = get_logger("test.has.handler")
        assert len(logger.handlers) >= 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_same_name_returns_same_logger(self):
        """get_logger is idempotent — same name → same instance."""
        l1 = get_logger("test.singleton")
        l2 = get_logger("test.singleton")
        assert l1 is l2

    def test_handler_uses_json_formatter(self):
        logger = get_logger("test.json.fmt")
        assert isinstance(logger.handlers[0].formatter, JsonFormatter)

    def test_logger_emits_valid_json(self, capsys):
        logger = get_logger("test.emit")
        logger.info("Tenant resolved", extra={"tenant_id": "pizza-palace-123"})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["message"] == "Tenant resolved"
        assert parsed["tenant_id"] == "pizza-palace-123"
