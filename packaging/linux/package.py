#!/usr/bin/env python3
"""Create a deterministic Linux release archive from the PyInstaller onedir."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--profile", choices=["cpu", "cuda"], required=True)
    parser.add_argument("--architecture", default="x64")
    parser.add_argument("--dist", type=Path, default=Path("dist/Midgard"))
    parser.add_argument("--output-dir", type=Path, default=Path("release"))
    args = parser.parse_args()
    if not (args.dist / "Midgard").is_file():
        raise SystemExit(f"Frozen Midgard executable is missing: {args.dist}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / (
        f"Midgard-{args.version}-linux-{args.architecture}-{args.profile}.tar.gz"
    )
    with tarfile.open(output, "w:gz", compresslevel=9) as archive:
        archive.add(args.dist, arcname="Midgard", recursive=True)
        for source, destination in (
            (
                Path("packaging/linux/install_bundle.sh"),
                "Midgard/install-midgard.sh",
            ),
            (Path("packaging/linux/INSTALL.txt"), "Midgard/INSTALL.txt"),
        ):
            info = archive.gettarinfo(str(source), arcname=destination)
            if source.suffix == ".sh":
                info.mode = 0o755
            with source.open("rb") as stream:
                archive.addfile(info, stream)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
