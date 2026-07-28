"""Process-local Paddle runtime policy."""

from __future__ import annotations

import os


def disable_paddle_background_services() -> None:
    """Disable Paddle/BRPC periodic metric dump threads before Paddle loads."""
    # BRPC reads these gflags from the environment while libpaddle is loaded.
    # Its dump interval defaults to one second when enabled.
    os.environ["FLAGS_bvar_dump"] = "false"
    os.environ["FLAGS_mbvar_dump"] = "false"
