"""Atomic `.midgard` ZIP project snapshots with bounded, safe reads."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from backend.editor.graph import OperationGraph


FORMAT_VERSION = 1
MAX_ENTRIES = 10_000
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 64 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


@dataclass(frozen=True)
class ProjectAsset:
    id: str
    sha256: str
    size_bytes: int
    original_name: str
    media_type: str = "application/octet-stream"
    embedded_path: str | None = None
    linked_path: str | None = None
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.startswith("asset_"):
            raise ValueError("project asset IDs must start with 'asset_'")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("project asset SHA-256 is invalid")
        if self.size_bytes < 0:
            raise ValueError("project asset size cannot be negative")
        if Path(self.original_name).name != self.original_name:
            raise ValueError("project asset original name must be a basename")
        if bool(self.embedded_path) == bool(self.linked_path):
            raise ValueError("project asset must be exactly one of embedded or linked")
        if self.embedded_path:
            _validate_member_name(self.embedded_path)
        try:
            encoded_extensions = json.dumps(
                self.extensions,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("project asset extensions must be JSON-compatible") from exc
        object.__setattr__(self, "extensions", json.loads(encoded_extensions))
        reserved = {
            "id",
            "sha256",
            "size_bytes",
            "original_name",
            "media_type",
            "embedded_path",
            "linked_path",
        }
        if reserved.intersection(self.extensions):
            raise ValueError("project asset extensions cannot replace standard fields")

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "original_name": self.original_name,
            "media_type": self.media_type,
            "embedded_path": self.embedded_path,
            "linked_path": self.linked_path,
        }
        data.update(dict(self.extensions))
        return data

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ProjectAsset:
        data = dict(value)
        known = {
            "id",
            "sha256",
            "size_bytes",
            "original_name",
            "media_type",
            "embedded_path",
            "linked_path",
        }
        return cls(
            id=data["id"],
            sha256=data["sha256"],
            size_bytes=data["size_bytes"],
            original_name=data["original_name"],
            media_type=data.get("media_type", "application/octet-stream"),
            embedded_path=data.get("embedded_path"),
            linked_path=data.get("linked_path"),
            extensions={key: data[key] for key in data.keys() - known},
        )


@dataclass(frozen=True)
class MidgardProject:
    project_id: str
    graph: OperationGraph
    assets: tuple[ProjectAsset, ...] = ()
    created_at: str = field(default_factory=_now)
    modified_at: str = field(default_factory=_now)
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_id.startswith("project_"):
            raise ValueError("project ID must start with 'project_'")
        if not isinstance(self.graph, OperationGraph):
            raise TypeError("project graph must be an OperationGraph")
        assets = tuple(self.assets)
        if not all(isinstance(asset, ProjectAsset) for asset in assets):
            raise TypeError("project assets must be ProjectAsset values")
        object.__setattr__(self, "assets", assets)
        asset_ids = {asset.id for asset in assets}
        if len(asset_ids) != len(assets):
            raise ValueError("project asset IDs must be unique")
        try:
            encoded_extensions = json.dumps(
                self.extensions,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("project extensions must be JSON-compatible") from exc
        object.__setattr__(self, "extensions", json.loads(encoded_extensions))
        reserved = {
            "format",
            "format_version",
            "minimum_reader_version",
            "project_id",
            "created_at",
            "modified_at",
            "graph_path",
            "graph_sha256",
            "assets",
        }
        if reserved.intersection(self.extensions):
            raise ValueError("project extensions cannot replace standard fields")

    @classmethod
    def new(
        cls,
        graph: OperationGraph | None = None,
        *,
        assets: tuple[ProjectAsset, ...] = (),
    ) -> MidgardProject:
        return cls(
            project_id=f"project_{uuid.uuid4().hex}",
            graph=graph or OperationGraph(),
            assets=assets,
        )

    def manifest(self) -> dict[str, Any]:
        data = {
            "format": "midgard-project",
            "format_version": FORMAT_VERSION,
            "minimum_reader_version": FORMAT_VERSION,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "graph_path": "document/graph.json",
            "graph_sha256": self.graph.fingerprint(),
            "assets": [asset.to_dict() for asset in self.assets],
        }
        data.update(dict(self.extensions))
        return data


def project_asset_from_file(
    asset_id: str,
    source: str | Path,
    *,
    embed: bool = True,
    media_type: str = "application/octet-stream",
) -> ProjectAsset:
    path = Path(source)
    digest, size = _sha256_file(path)
    suffix = path.suffix.lower()
    embedded_path = f"assets/{digest}{suffix}" if embed else None
    return ProjectAsset(
        id=asset_id,
        sha256=digest,
        size_bytes=size,
        original_name=path.name,
        media_type=media_type,
        embedded_path=embedded_path,
        linked_path=None if embed else str(path),
    )


def _validate_member_name(name: str) -> None:
    pure = PurePosixPath(name)
    if (
        not name
        or name.startswith(("/", "\\"))
        or "\\" in name
        or pure.is_absolute()
        or ".." in pure.parts
        or "." in pure.parts
    ):
        raise ValueError(f"unsafe project member path: {name!r}")


def _validate_archive(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ValueError("project contains too many entries")
    found: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in infos:
        _validate_member_name(info.filename)
        if info.filename in found:
            raise ValueError(f"duplicate project member: {info.filename}")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValueError(f"project member cannot be a symlink: {info.filename}")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError("project uncompressed size exceeds the safety limit")
        if (
            info.file_size > 1024 * 1024
            and info.compress_size > 0
            and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise ValueError(f"project member compression ratio is unsafe: {info.filename}")
        found[info.filename] = info
    return found


def _read_json(
    archive: zipfile.ZipFile,
    members: Mapping[str, zipfile.ZipInfo],
    name: str,
) -> dict[str, Any]:
    info = members.get(name)
    if info is None:
        raise ValueError(f"project is missing {name}")
    if info.file_size > MAX_JSON_BYTES:
        raise ValueError(f"project JSON is too large: {name}")
    raw = archive.read(info)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"project JSON is invalid: {name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"project JSON root must be an object: {name}")
    return value


def save_project(
    project: MidgardProject,
    target: str | Path,
    *,
    embedded_sources: Mapping[str, str | Path] | None = None,
) -> Path:
    """Write, reopen, validate, and atomically replace a project snapshot."""
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sources = dict(embedded_sources or {})
    expected_embedded = {
        asset.id: asset for asset in project.assets if asset.embedded_path is not None
    }
    if set(sources) != set(expected_embedded):
        missing = set(expected_embedded).difference(sources)
        extra = set(sources).difference(expected_embedded)
        details = []
        if missing:
            details.append(f"missing embedded sources: {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unknown embedded sources: {', '.join(sorted(extra))}")
        raise ValueError("; ".join(details))

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        graph_bytes = json.dumps(
            project.graph.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        manifest_bytes = json.dumps(
            project.manifest(),
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            allowZip64=True,
        ) as archive:
            archive.writestr("manifest.json", manifest_bytes)
            archive.writestr("document/graph.json", graph_bytes)
            written_paths: set[str] = set()
            for asset_id, asset in expected_embedded.items():
                source = Path(sources[asset_id])
                digest, size = _sha256_file(source)
                if digest != asset.sha256 or size != asset.size_bytes:
                    raise ValueError(f"embedded source changed: {asset.original_name}")
                if asset.embedded_path in written_paths:
                    continue
                archive.write(source, asset.embedded_path)
                written_paths.add(asset.embedded_path)
        loaded = load_project(temporary, verify_embedded=True)
        if loaded.project_id != project.project_id:
            raise ValueError("project validation returned a different project ID")
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        try:
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
        return destination
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def load_project(
    source: str | Path,
    *,
    verify_embedded: bool = True,
) -> MidgardProject:
    path = Path(source)
    with zipfile.ZipFile(path, "r") as archive:
        members = _validate_archive(archive)
        manifest = _read_json(archive, members, "manifest.json")
        if manifest.get("format") != "midgard-project":
            raise ValueError("file is not a Midgard project")
        version = manifest.get("format_version")
        if version != FORMAT_VERSION:
            raise ValueError(f"unsupported Midgard project version: {version}")
        graph_path = manifest.get("graph_path")
        if graph_path != "document/graph.json":
            raise ValueError("project graph path is unsupported")
        graph = OperationGraph.from_dict(_read_json(archive, members, graph_path))
        if graph.fingerprint() != manifest.get("graph_sha256"):
            raise ValueError("project graph fingerprint does not match the manifest")
        raw_assets = manifest.get("assets", [])
        if not isinstance(raw_assets, list):
            raise ValueError("project assets must be a list")
        assets = tuple(ProjectAsset.from_dict(value) for value in raw_assets)
        if verify_embedded:
            verified_paths: set[str] = set()
            for asset in assets:
                if asset.embedded_path is None or asset.embedded_path in verified_paths:
                    continue
                info = members.get(asset.embedded_path)
                if info is None:
                    raise ValueError(f"project is missing embedded asset {asset.id}")
                digest = hashlib.sha256()
                size = 0
                with archive.open(info) as stream:
                    while chunk := stream.read(1024 * 1024):
                        size += len(chunk)
                        digest.update(chunk)
                if size != asset.size_bytes or digest.hexdigest() != asset.sha256:
                    raise ValueError(f"embedded asset failed verification: {asset.id}")
                verified_paths.add(asset.embedded_path)
        known = {
            "format",
            "format_version",
            "minimum_reader_version",
            "project_id",
            "created_at",
            "modified_at",
            "graph_path",
            "graph_sha256",
            "assets",
        }
        return MidgardProject(
            project_id=manifest["project_id"],
            graph=graph,
            assets=assets,
            created_at=manifest["created_at"],
            modified_at=manifest["modified_at"],
            extensions={key: manifest[key] for key in manifest.keys() - known},
        )
