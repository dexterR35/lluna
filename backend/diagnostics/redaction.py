"""Conservative redaction for shareable diagnostics."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_TOKEN = re.compile(
    r"(?i)\b(hf_[a-z0-9]{8,}|bearer\s+[a-z0-9._~+/=-]{8,}|"
    r"(?:token|password|authorization)\s*[=:]\s*\S+)"
)


def redact_text(value: object) -> str:
    return _TOKEN.sub("[REDACTED]", str(value))


def redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return redact_text(value)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))
