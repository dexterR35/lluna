"""Standard logging bootstrap used before the control plane starts."""

from __future__ import annotations

import logging
import os
import sys

from backend.diagnostics.redaction import redact_text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def initialize_logging(*, diagnostic: bool | None = None) -> None:
    root = logging.getLogger()
    if getattr(root, "_midgard_configured", False):
        return
    if diagnostic is None:
        diagnostic = os.environ.get("MIDGARD_DIAG") == "1"
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        RedactingFormatter(
            "%(asctime)s %(levelname)s %(process)d %(threadName)s %(name)s: %(message)s"
        )
    )
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if diagnostic else logging.INFO)
    root.__dict__["_midgard_configured"] = True
