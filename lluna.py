#!/usr/bin/env python3
"""Lluna entry point: desktop sidecar, headless API, or one-shot workflow run.

Called with no subcommand this still starts the API exactly as before, so the
desktop app and the packaging scripts are unaffected.
"""

import multiprocessing

from backend.cli import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
