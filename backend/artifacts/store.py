"""Atomic artifact store and session-scoped desktop path grants."""

from __future__ import annotations

import json
import mimetypes
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from backend.artifacts.hashing import hash_file
from backend.artifacts.models import ArtifactRecord
from backend.core.atomic import atomic_write_json
from backend.core.paths import PATHS


@dataclass(frozen=True)
class PathGrant:
    grant_id: str
    path: Path
    mode: str
    display_name: str


class DesktopGrantStore:
    _instance: "DesktopGrantStore | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._grants: dict[str, PathGrant] = {}
        self._grants_lock = threading.RLock()

    @classmethod
    def instance(cls) -> "DesktopGrantStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def issue(self, path: str | Path, *, mode: str = "read") -> PathGrant:
        if mode not in {"read", "write", "directory"}:
            raise ValueError("Grant mode must be read, write, or directory")
        resolved = Path(path).expanduser().resolve()
        if mode == "read" and not resolved.is_file():
            raise FileNotFoundError(resolved)
        if mode == "directory" and not resolved.is_dir():
            raise NotADirectoryError(resolved)
        if mode == "write":
            resolved.parent.mkdir(parents=True, exist_ok=True)
        grant = PathGrant(str(uuid4()), resolved, mode, resolved.name)
        with self._grants_lock:
            self._grants[grant.grant_id] = grant
        return grant

    def resolve(self, grant_id: str, *, mode: str | None = None) -> Path:
        with self._grants_lock:
            grant = self._grants.get(grant_id)
        if grant is None:
            raise PermissionError("Unknown or expired path grant")
        if mode is not None and grant.mode != mode:
            raise PermissionError(f"Path grant does not allow {mode} access")
        return grant.path

    def revoke_all(self) -> None:
        with self._grants_lock:
            self._grants.clear()


class ArtifactStore:
    _instance: "ArtifactStore | None" = None
    _instance_lock = threading.Lock()

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or PATHS.data_dir / "artifacts").resolve()
        self.files_dir = self.root / "files"
        self.index_path = self.root / "index.json"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._records: dict[str, ArtifactRecord] = {}
        self._load()

    @classmethod
    def instance(cls) -> "ArtifactStore":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load(self) -> None:
        if not self.index_path.is_file():
            return
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            self._records = {
                key: ArtifactRecord.model_validate(value) for key, value in raw.items()
            }
        except (OSError, ValueError, json.JSONDecodeError):
            self._records = {}

    def _save(self) -> None:
        atomic_write_json(
            self.index_path,
            {key: value.model_dump(mode="json") for key, value in self._records.items()},
        )

    @staticmethod
    def _image_metadata(path: Path) -> tuple[int | None, int | None, bool | None]:
        try:
            from PIL import Image

            with Image.open(path) as image:
                return image.width, image.height, "A" in image.getbands()
        except (ImportError, OSError):
            return None, None, None

    def register_source(self, path: str | Path, *, media_type: str | None = None) -> ArtifactRecord:
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        width, height, alpha = self._image_metadata(source)
        record = ArtifactRecord(
            media_type=media_type
            or mimetypes.guess_type(source.name)[0]
            or "application/octet-stream",
            path=str(source),
            original_source_path=str(source),
            content_hash=hash_file(source),
            byte_size=source.stat().st_size,
            width=width,
            height=height,
            alpha=alpha,
        )
        with self._lock:
            self._records[record.artifact_id] = record
            self._save()
        return record

    def commit(
        self,
        source: str | Path,
        *,
        run_id: str,
        node_id: str,
        inputs: list[ArtifactRecord],
        schema_id: str = "",
        media_type: str | None = None,
        parameters_hash: str = "",
    ) -> ArtifactRecord:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        artifact_id = str(uuid4())
        extension = source_path.suffix.lower() or ".bin"
        destination = self.files_dir / f"{artifact_id}{extension}"
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(source_path, temporary)
        temporary.replace(destination)
        width, height, alpha = self._image_metadata(destination)
        record = ArtifactRecord(
            artifact_id=artifact_id,
            media_type=media_type
            or mimetypes.guess_type(destination.name)[0]
            or "application/octet-stream",
            path=str(destination),
            content_hash=hash_file(destination),
            byte_size=destination.stat().st_size,
            width=width,
            height=height,
            alpha=alpha,
            creating_run_id=run_id,
            creating_node_id=node_id,
            creating_schema_id=schema_id,
            input_artifact_ids=[item.artifact_id for item in inputs],
            parameters_hash=parameters_hash,
        )
        with self._lock:
            self._records[record.artifact_id] = record
            self._save()
        return record

    def get(self, artifact_id: str) -> ArtifactRecord:
        with self._lock:
            record = self._records.get(artifact_id)
        if record is None:
            raise KeyError(artifact_id)
        if not Path(record.path).is_file():
            raise FileNotFoundError(record.path)
        return record

    def thumbnail_path(self, artifact_id: str, *, max_edge: int = 256) -> Path:
        """Return a cached small JPEG for node previews; fall back to source for non-images."""
        record = self.get(artifact_id)
        source = Path(record.path)
        if not (record.media_type or "").startswith("image/"):
            return source
        thumbs_dir = self.root / "thumbs"
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb = thumbs_dir / f"{artifact_id}_{max_edge}.jpg"
        try:
            if thumb.is_file() and thumb.stat().st_mtime >= source.stat().st_mtime:
                return thumb
        except OSError:
            pass
        try:
            from PIL import Image, ImageOps

            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened)
                if image.mode in {"RGBA", "LA"} or (
                    image.mode == "P" and "transparency" in image.info
                ):
                    rgba = image.convert("RGBA")
                    background = Image.new("RGB", rgba.size, (18, 20, 26))
                    background.paste(rgba, mask=rgba.split()[-1])
                    image = background
                else:
                    image = image.convert("RGB")
                image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
                temporary = thumb.with_suffix(".tmp.jpg")
                image.save(temporary, format="JPEG", quality=72, optimize=True)
                temporary.replace(thumb)
            return thumb
        except (ImportError, OSError, ValueError):
            return source

    def list(self) -> list[ArtifactRecord]:
        with self._lock:
            return list(self._records.values())

    def remove(self, artifact_id: str) -> None:
        with self._lock:
            record = self._records.pop(artifact_id, None)
            if record is None:
                return
            path = Path(record.path)
            if self.files_dir in path.parents:
                path.unlink(missing_ok=True)
            for thumb in (self.root / "thumbs").glob(f"{artifact_id}_*.jpg"):
                thumb.unlink(missing_ok=True)
            self._save()
