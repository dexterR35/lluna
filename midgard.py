#!/usr/bin/env python3
"""Midgard Python sidecar entry point."""

import multiprocessing

from backend.api.app import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
