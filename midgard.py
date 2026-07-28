#!/usr/bin/env python3
"""Midgard desktop entry point."""

from backend.application.bootstrap import launch_desktop


if __name__ == "__main__":
    raise SystemExit(launch_desktop())
