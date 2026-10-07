"""JSON structured logging with recursive masking of sensitive fields.

Every tool-invocation log line carries at least::

    timestamp, tool_name, params, status, duration_ms

Personal data fields — ``ownerPhone``, ``ownerAddr``, ``chipNo`` and their
snake_case spellings (``owner_phone``, ``owner_addr``, ``chip_no``) — are
recursively masked in ``params`` so the full values never reach the log.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

SENSITIVE_FIELD_NAMES = frozenset(
    {
        # camelCase (Go API wire names)
        "ownerphone",
        "owneraddr",
        "chipno",
        # snake_case
        "owner_phone",
        "owner_addr",
        "chip_no",
    }
)

_MASK = "***"


def mask_recursive(obj: Any, *, _depth: int = 0) -> Any:
    """Return a deep copy of ``obj`` with sensitive values replaced by ``***``.

    Guards against pathological depth / self-references so logging can never
    hang or crash the tool call.
    """
    if _depth > 64:
        return "<max-depth>"
    if isinstance(obj, dict):
        return {
            key: (mask_recursive(_mask_key_value(key, value), _depth=_depth + 1))
            for key, value in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [mask_recursive(item, _depth=_depth + 1) for item in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return "<unserializable>"


def _mask_key_value(key: Any, value: Any) -> Any:
    if isinstance(key, str) and key.lower() in SENSITIVE_FIELD_NAMES:
        return _MASK
    return value


class JsonFormatter(logging.Formatter):
    """Logs records as single-line JSON documents."""

    _EXTRA_FIELDS = ("tool_name", "status", "duration_ms", "params")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                if field == "params":
                    value = mask_recursive(value)
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure the package logger to emit JSON to stderr."""
    logger = logging.getLogger("pet_hospital_mcp")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:
        logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def get_logger(name: str = "pet_hospital_mcp") -> logging.Logger:
    """Return a child logger of the package logger (JSON configured)."""
    return logging.getLogger(name)
