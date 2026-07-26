# -*- coding: utf-8 -*-
"""CLI diagnostic / debug logger for Midgard Studio.

Enable (default when stdout is a TTY):
  MIDGARD_DIAG=1 ./run_gui.sh
  ./run_gui.sh --diag

Disable:
  MIDGARD_DIAG=0 ./run_gui.sh
  ./run_gui.sh --no-diag

Optional noisy UI click log (off by default):
  MIDGARD_DIAG_CLICKS=1 ./run_gui.sh
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from typing import Any, Optional

# Categories mirror the user-facing debug surface
CAT_START = "START"
CAT_NAV = "NAV"
CAT_BUTTON = "BUTTON"
CAT_EVENT = "EVENT"
CAT_WORKER = "WORKER"
CAT_UPLOAD = "UPLOAD"
CAT_SAVE = "SAVE"
CAT_PROGRESS = "PROGRESS"
CAT_PROCESS = "PROCESS"
CAT_RUN = "RUN"
CAT_MODEL = "MODEL"
CAT_INFO = "INFO"
CAT_WARN = "WARN"
CAT_ERROR = "ERROR"

_COLORS = {
    CAT_START: "\033[96m",      # cyan
    CAT_NAV: "\033[94m",        # blue
    CAT_BUTTON: "\033[95m",     # magenta
    CAT_EVENT: "\033[93m",      # yellow
    CAT_WORKER: "\033[92m",     # green
    CAT_UPLOAD: "\033[96m",
    CAT_SAVE: "\033[92m",
    CAT_PROGRESS: "\033[90m",   # gray
    CAT_PROCESS: "\033[92m",
    CAT_RUN: "\033[93m",
    CAT_MODEL: "\033[96m",
    CAT_INFO: "\033[97m",
    CAT_WARN: "\033[33m",
    CAT_ERROR: "\033[91m",
}
_RESET = "\033[0m"
_DIM = "\033[90m"
_BOLD = "\033[1m"

_lock = threading.Lock()
_enabled: Optional[bool] = None
_use_color: Optional[bool] = None
_t0 = time.monotonic()
_last_progress: dict[str, int] = {}
_PROGRESS_STEP = 5  # log at most every N%


def _env_flag(name: str) -> Optional[bool]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() not in ("0", "false", "no", "off")


def is_enabled() -> bool:
    global _enabled
    if _enabled is None:
        env = _env_flag("MIDGARD_DIAG")
        if env is not None:
            _enabled = env
        else:
            _enabled = bool(getattr(sys.stdout, "isatty", lambda: False)())
    return bool(_enabled)


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = bool(on)


def use_color() -> bool:
    global _use_color
    if _use_color is None:
        if os.environ.get("NO_COLOR"):
            _use_color = False
        else:
            _use_color = bool(getattr(sys.stdout, "isatty", lambda: False)())
    return bool(_use_color)


def elapsed_ms() -> int:
    return int((time.monotonic() - _t0) * 1000)


def log(category: str, message: str, *args: Any, **kwargs: Any) -> None:
    """Print a diagnostic line to the CLI."""
    if not is_enabled():
        return
    if args:
        try:
            message = message.format(*args)
        except Exception:
            message = f"{message} {' '.join(str(a) for a in args)}"
    extra = ""
    if kwargs:
        parts = [f"{k}={v!r}" for k, v in kwargs.items()]
        extra = "  " + " ".join(parts)

    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    ms = elapsed_ms()
    cat = (category or CAT_INFO).upper()
    line_body = f"{message}{extra}"

    with _lock:
        if use_color():
            color = _COLORS.get(cat, _COLORS[CAT_INFO])
            out = (
                f"{_DIM}[{ts} +{ms:6d}ms]{_RESET} "
                f"{color}{_BOLD}{cat:<8}{_RESET} {line_body}"
            )
        else:
            out = f"[{ts} +{ms:6d}ms] {cat:<8} {line_body}"
        print(out, flush=True)


def start(message: str, **kwargs: Any) -> None:
    log(CAT_START, message, **kwargs)


def nav(message: str, **kwargs: Any) -> None:
    log(CAT_NAV, message, **kwargs)


def button(message: str, **kwargs: Any) -> None:
    log(CAT_BUTTON, message, **kwargs)


def event(message: str, **kwargs: Any) -> None:
    log(CAT_EVENT, message, **kwargs)


def worker(message: str, **kwargs: Any) -> None:
    log(CAT_WORKER, message, **kwargs)


def upload(message: str, **kwargs: Any) -> None:
    log(CAT_UPLOAD, message, **kwargs)


def save(message: str, **kwargs: Any) -> None:
    log(CAT_SAVE, message, **kwargs)


def process(message: str, **kwargs: Any) -> None:
    log(CAT_PROCESS, message, **kwargs)


def run(message: str, **kwargs: Any) -> None:
    log(CAT_RUN, message, **kwargs)


def model(message: str, **kwargs: Any) -> None:
    log(CAT_MODEL, message, **kwargs)


def warn(message: str, **kwargs: Any) -> None:
    log(CAT_WARN, message, **kwargs)


def error(message: str, **kwargs: Any) -> None:
    log(CAT_ERROR, message, **kwargs)


def progress(key: str, percent: int, message: str = "", *, force: bool = False) -> None:
    """Throttled progress logging (every 5% + 0/100)."""
    if not is_enabled():
        return
    try:
        p = int(percent)
    except Exception:
        p = 0
    p = max(0, min(100, p))
    last = _last_progress.get(key)
    if not force and last is not None:
        if p not in (0, 100) and (p - last) < _PROGRESS_STEP and p > last:
            return
        if p == last:
            return
    _last_progress[key] = p
    msg = message or key
    log(CAT_PROGRESS, f"{msg}  {p}%")


def reset_progress(key: Optional[str] = None) -> None:
    if key is None:
        _last_progress.clear()
    else:
        _last_progress.pop(key, None)


def banner() -> None:
    if not is_enabled():
        return
    line = "─" * 56
    with _lock:
        if use_color():
            print(
                f"\n{_BOLD}{_COLORS[CAT_START]}{line}\n"
                f"  Midgard Studio - diagnostic CLI log ON\n"
                f"  Focus: UPLOAD → MODEL → RUN → WORKER → PROCESS → PROGRESS\n"
                f"  UI clicks are OFF (no ToolButton spam).\n"
                f"  Enable clicks: MIDGARD_DIAG_CLICKS=1\n"
                f"  Disable all:   MIDGARD_DIAG=0  or  --no-diag\n"
                f"{line}{_RESET}\n",
                flush=True,
            )
        else:
            print(
                f"\n{line}\n"
                f"  Midgard Studio - diagnostic CLI log ON\n"
                f"  Focus: UPLOAD → MODEL → RUN → WORKER → PROCESS → PROGRESS\n"
                f"  UI clicks are OFF (no ToolButton spam).\n"
                f"  Enable clicks: MIDGARD_DIAG_CLICKS=1\n"
                f"  Disable all:   MIDGARD_DIAG=0  or  --no-diag\n"
                f"{line}\n",
                flush=True,
            )


def parse_cli_flags(argv: Optional[list[str]] = None) -> list[str]:
    """Consume --diag / --no-diag from argv; return remaining args."""
    args = list(sys.argv[1:] if argv is None else argv)
    keep: list[str] = []
    for a in args:
        if a == "--diag":
            set_enabled(True)
        elif a == "--no-diag":
            set_enabled(False)
        else:
            keep.append(a)
    if argv is None:
        sys.argv = [sys.argv[0], *keep]
    return keep
