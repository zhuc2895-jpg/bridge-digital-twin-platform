"""Request context, log redaction, and stable error responses."""

from __future__ import annotations

import logging
import re
import uuid

REQUEST_ID_HEADER = "X-Request-ID"
MAX_LOG_MESSAGE_CHARS = 2_000
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SENSITIVE_PAIR_PATTERN = re.compile(
    r"(?i)([\"']?(?:password|passwd|token|secret|api[_-]?key|authorization|cookie)"
    r"[\"']?\s*[:=]\s*)([\"']?)([^\"'\s,;}]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-=]+")


def normalize_request_id(value: str | None) -> str:
    """Accept only bounded, log-safe caller request identifiers."""
    if value is not None and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return uuid.uuid4().hex


def redact_text(value: str) -> str:
    """Redact common credentials and truncate oversized log messages."""
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", str(value))
    redacted = _SENSITIVE_PAIR_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        redacted,
    )
    if len(redacted) > MAX_LOG_MESSAGE_CHARS:
        redacted = redacted[:MAX_LOG_MESSAGE_CHARS] + "...[truncated]"
    return redacted


class SensitiveDataFilter(logging.Filter):
    """Remove credentials and cap message size before any handler renders it."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = ()
        return True


def configure_logging(level: str) -> None:
    """Apply application log level and sensitive-data filtering once."""
    app_logger = logging.getLogger("app")
    app_logger.setLevel(getattr(logging, level, logging.INFO))
    handlers = [*app_logger.handlers, *logging.getLogger().handlers]
    for handler in handlers:
        if not any(isinstance(item, SensitiveDataFilter) for item in handler.filters):
            handler.addFilter(SensitiveDataFilter())
    if not handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        handler.addFilter(SensitiveDataFilter())
        app_logger.addHandler(handler)


def stable_error_payload(request_id: str) -> dict[str, dict[str, str]]:
    """Return the public internal-error body without implementation details."""
    return {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Internal server error",
            "request_id": request_id,
        }
    }
