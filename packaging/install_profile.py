#!/usr/bin/env python3
"""Install the exact dependency family used for a frozen release build."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.check_call([sys.executable, "-m", "pip", *args], cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        required=True,
        choices=["cpu", "cuda", "directml", "mps"],
    )
    args = parser.parse_args()
    run("install", "--upgrade", "pip", "setuptools", "wheel")
    if args.profile == "cuda":
        run(
            "install",
            "torch==2.7.0",
            "torchvision==0.22.0",
            "--index-url",
            "https://download.pytorch.org/whl/cu128",
        )
        requirements = "requirements-cuda.txt"
    else:
        requirements = {
            "cpu": "requirements-cpu.txt",
            "directml": "requirements-directml.txt",
            "mps": "requirements-macos.txt",
        }[args.profile]
    run(
        "install",
        "-r",
        requirements,
        "-r",
        "requirements-packaging.txt",
        "-r",
        "requirements-test.txt",
        "-c",
        "constraints.txt",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
