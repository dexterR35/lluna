#!/usr/bin/env python3
"""Validate and build the portable Midgard desktop bundle."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "midgard.spec"
RELEASE_METADATA = ROOT / "build" / "release-metadata" / "midgard_release.json"
REQUIRED_RESOURCES = (
    ROOT / "midgard.py",
    ROOT / "backend" / "interface" / "en.ini",
    ROOT / "ui" / "icon" / "icon_48.png",
    ROOT / "packaging" / "linux" / "midgard.desktop",
    ROOT / "backend" / "models" / "sttn-auto" / "infer_model.pth",
    ROOT / "backend" / "models" / "sttn-det" / "sttn.pth",
)


def validate_repository(*, strict_python: bool) -> tuple[str, ...]:
    errors: list[str] = []
    if strict_python and sys.version_info[:2] != (3, 12):
        errors.append(
            f"Python 3.12 is required; received "
            f"{sys.version_info.major}.{sys.version_info.minor}."
        )
    for path in REQUIRED_RESOURCES:
        if not path.is_file():
            errors.append(f"Required packaging resource is missing: {path}")
    if not SPEC.is_file():
        errors.append(f"PyInstaller specification is missing: {SPEC}")
    return tuple(errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate repository assets without invoking PyInstaller.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Ask PyInstaller to clear its build cache.",
    )
    parser.add_argument(
        "--profile",
        choices=["cpu", "cuda", "directml", "mps"],
        default=("mps" if sys.platform == "darwin" else "cpu"),
        help="Runtime dependency profile embedded in this release.",
    )
    parser.add_argument(
        "--architecture",
        default=platform.machine(),
        help="Architecture label embedded in this release.",
    )
    args = parser.parse_args(argv)
    errors = validate_repository(strict_python=not args.validate_only)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.validate_only:
        print("Desktop packaging inputs are valid.")
        return 0
    if importlib.util.find_spec("PyInstaller") is None:
        print(
            "ERROR: PyInstaller is missing. Install requirements-packaging.txt.",
            file=sys.stderr,
        )
        return 1
    platform_name = (
        "windows"
        if sys.platform == "win32"
        else "macos"
        if sys.platform == "darwin"
        else "linux"
    )
    RELEASE_METADATA.parent.mkdir(parents=True, exist_ok=True)
    RELEASE_METADATA.write_text(
        json.dumps(
            {
                "platform": platform_name,
                "architecture": args.architecture,
                "profile": args.profile,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        str(SPEC),
    ]
    if args.clean:
        command.insert(4, "--clean")
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
