"""Collision-safe output path generation."""

from __future__ import annotations

from pathlib import Path


def default_output_path(
    input_path: str | Path,
    *,
    suffix: str,
    extension: str | None = None,
    directory: str | Path | None = None,
) -> Path:
    source = Path(input_path).expanduser().resolve()
    ext = extension or source.suffix
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    parent = Path(directory).expanduser().resolve() if directory else source.parent
    candidate = parent / f"{source.stem}{suffix}{ext}"
    if candidate.resolve() == source:
        raise ValueError("output path must not overwrite the input")
    return candidate


def next_available_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.exists():
        return candidate
    for number in range(1, 10_000):
        alternate = candidate.with_name(f"{candidate.stem}-{number}{candidate.suffix}")
        if not alternate.exists():
            return alternate
    raise FileExistsError(f"No available output name near {candidate}")
