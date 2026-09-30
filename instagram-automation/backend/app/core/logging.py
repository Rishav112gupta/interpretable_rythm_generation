"""Logging setup with secret redaction.

Access tokens must never reach log files. The filter below scrubs anything that
looks like a token from every log record, and noisy HTTP client loggers (which
print full request URLs, including `access_token=` query parameters) are
silenced below WARNING.
"""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    re.compile(r"(access_token=)[^&\s\"']+", re.IGNORECASE),
    re.compile(r"(client_secret=)[^&\s\"']+", re.IGNORECASE),
    re.compile(r"(\"?access_token\"?\s*[:=]\s*\"?)[^\"',\s}]+", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]+"),
    re.compile(r"(IG[A-Za-z0-9]{4})[A-Za-z0-9]{20,}"),
    re.compile(r"(EAA[A-Za-z0-9]{2})[A-Za-z0-9]{20,}"),
]


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpx2", "httpcore", "urllib3", "botocore", "google"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
