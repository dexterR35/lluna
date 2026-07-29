#!/usr/bin/env python3
"""Fail a release when tag and declared application versions disagree."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.core.build_info import BUILD_INFO


def verify(tag: str) -> tuple[str, ...]:
    expected = tag.strip().removeprefix("v")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = str(pyproject["project"]["version"])
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"version-(\d+\.\d+\.\d+)-", readme)
    versions = {
        "tag": expected,
        "backend/core/build_info.py": BUILD_INFO.version,
        "pyproject.toml": project_version,
        "README badge": badge.group(1) if badge else "",
    }
    return tuple(
        f"{name} declares {version!r}; expected {expected!r}"
        for name, version in versions.items()
        if version != expected
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    errors = verify(args.tag)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Release version {args.tag} is consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
