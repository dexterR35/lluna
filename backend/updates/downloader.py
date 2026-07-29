"""Download and verify the packaged update matching this installation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from backend.core.build_info import BUILD_INFO
from backend.core.paths import PATHS
from backend.core.release_target import ReleaseTarget, current_release_target
from backend.updates.manifest import (
    ReleaseAsset,
    parse_verified_manifest,
    verify_artifact,
)

ProgressCallback = Callable[[int], None]


@dataclass(frozen=True)
class PreparedUpdate:
    version: str
    target: ReleaseTarget
    asset: ReleaseAsset
    path: Path


def release_download_url(version: str, filename: str) -> str:
    safe_version = version.strip().removeprefix("v")
    if not safe_version or "/" in safe_version or "\\" in safe_version:
        raise ValueError("Invalid update version.")
    if Path(filename).name != filename:
        raise ValueError("Invalid update filename.")
    return (
        f"{BUILD_INFO.project_url}/releases/download/v{safe_version}/{filename}"
    )


def _get_bytes(url: str) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": "Midgard-packaged-updater"},
        timeout=15,
        allow_redirects=True,
    )
    response.raise_for_status()
    return response.content


def _download(
    url: str,
    destination: Path,
    expected_size: int,
    progress: ProgressCallback | None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    received = 0
    with requests.get(
        url,
        headers={"User-Agent": "Midgard-packaged-updater"},
        timeout=(10, 60),
        allow_redirects=True,
        stream=True,
    ) as response:
        response.raise_for_status()
        with destination.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                stream.write(chunk)
                received += len(chunk)
                if progress and expected_size > 0:
                    progress(min(99, int(received * 100 / expected_size)))
            stream.flush()
            os.fsync(stream.fileno())


def prepare_update(
    version: str,
    *,
    target: ReleaseTarget | None = None,
    updates_dir: Path | None = None,
    progress: ProgressCallback | None = None,
    fetch_bytes: Callable[[str], bytes] = _get_bytes,
    download: Callable[[str, Path, int, ProgressCallback | None], None] = _download,
) -> PreparedUpdate:
    normalized = version.strip().removeprefix("v")
    selected_target = target or current_release_target()
    manifest_url = release_download_url(normalized, "midgard-update.json")
    signature_url = release_download_url(normalized, "midgard-update.json.sig")
    manifest = parse_verified_manifest(
        fetch_bytes(manifest_url),
        fetch_bytes(signature_url).strip(),
    )
    if manifest.version != normalized:
        raise RuntimeError(
            f"Release manifest version {manifest.version} does not match {normalized}."
        )
    asset = manifest.select(selected_target)
    if asset.name != selected_target.asset_name(normalized):
        raise RuntimeError("Release asset name does not match its signed target metadata.")
    destination_root = Path(updates_dir or PATHS.updates_dir) / normalized
    destination_root.mkdir(parents=True, exist_ok=True)
    partial = destination_root / f"{asset.name}.part"
    final = destination_root / asset.name
    partial.unlink(missing_ok=True)
    try:
        download(asset.url, partial, asset.size, progress)
        verify_artifact(partial, asset)
        os.replace(partial, final)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    if progress:
        progress(100)
    return PreparedUpdate(normalized, selected_target, asset, final)
