"""Process-local Paddle runtime policy."""

from __future__ import annotations

import os


def disable_paddle_background_services() -> None:
    """Disable Paddle/BRPC periodic metric dump threads before Paddle loads."""
    # BRPC reads these gflags from the environment while libpaddle is loaded.
    # Its dump interval defaults to one second when enabled.
    os.environ["FLAGS_bvar_dump"] = "false"
    os.environ["FLAGS_mbvar_dump"] = "false"


def preferred_paddle_device(paddle, *, acceleration_enabled: bool) -> str:
    """Return GPU 0 when Paddle CUDA is usable, otherwise CPU.

    Paddle does not support Lluna's DirectML or MPS profiles. The caller
    still retries model construction on CPU because a compiled CUDA wheel can
    be present while its native runtime or driver is unavailable.
    """
    if not acceleration_enabled:
        return "cpu"
    try:
        if not bool(paddle.is_compiled_with_cuda()):
            return "cpu"
        if int(paddle.device.cuda.device_count()) < 1:
            return "cpu"
    except (AttributeError, OSError, RuntimeError, ValueError):
        return "cpu"
    return "gpu:0"
