"""Track in-flight model installs: cancel → revert partials; reopen → start over."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# (kind, key) e.g. ("enhance", "x2plus"), ("select_object", "fast")
PendingItem = Tuple[str, str]

KIND_ENHANCE = "enhance"
KIND_LOW_LIGHT = "low_light"
KIND_GENERATE = "generate"
KIND_BG_REMOVE = "bg_remove"
KIND_SELECT_OBJECT = "select_object"


class DownloadCancelled(Exception):
    """Raised when a model download is aborted (app close / CLI / cancel)."""


@dataclass(frozen=True)
class PendingDownload:
    kind: str
    key: str


def _pending_path() -> Path:
    # Project root config/ (same tree as config/config.json)
    root = Path(__file__).resolve().parents[2]
    path = root / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path / "pending_model_downloads.json"


def _cancel_flag_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    path = root / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path / "model_download_cancel.flag"


class ModelDownloadRegistry:
    """Process-wide registry for Settings / ensure_* model downloads."""

    _instance: Optional["ModelDownloadRegistry"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._active: dict[PendingItem, bool] = {}

    @classmethod
    def instance(cls) -> "ModelDownloadRegistry":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_cancelled(self) -> bool:
        if self._cancel.is_set():
            return True
        try:
            return _cancel_flag_path().is_file()
        except OSError:
            return False

    def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise DownloadCancelled("Model download cancelled")

    def request_cancel(self) -> None:
        """Signal all in-flight downloads to stop (app close / CLI)."""
        self._cancel.set()
        try:
            _cancel_flag_path().write_text("1", encoding="utf-8")
        except OSError:
            pass

    def clear_cancel(self) -> None:
        self._cancel.clear()
        try:
            flag = _cancel_flag_path()
            if flag.is_file():
                flag.unlink()
        except OSError:
            pass

    def begin(self, kind: str, key: str) -> None:
        """Mark download started; persist so reopen can start over after abort."""
        item = (kind, str(key))
        with self._lock:
            self._active[item] = True
            pending = self._load_pending_unlocked()
            if item not in pending:
                pending.append(item)
                self._save_pending_unlocked(pending)

    def complete(self, kind: str, key: str) -> None:
        item = (kind, str(key))
        with self._lock:
            self._active.pop(item, None)
            pending = [p for p in self._load_pending_unlocked() if p != item]
            self._save_pending_unlocked(pending)

    def fail(self, kind: str, key: str, *, keep_pending: bool = False) -> None:
        """Clear active; drop pending unless keep_pending (abort → restart later)."""
        item = (kind, str(key))
        with self._lock:
            self._active.pop(item, None)
            if keep_pending:
                pending = self._load_pending_unlocked()
                if item not in pending:
                    pending.append(item)
                    self._save_pending_unlocked(pending)
            else:
                pending = [p for p in self._load_pending_unlocked() if p != item]
                self._save_pending_unlocked(pending)

    def list_pending(self) -> List[PendingDownload]:
        with self._lock:
            return [PendingDownload(k, v) for k, v in self._load_pending_unlocked()]

    def list_active(self) -> List[PendingDownload]:
        with self._lock:
            return [PendingDownload(k, v) for k, v in self._active.keys()]

    def abort_all_and_revert(self) -> List[PendingDownload]:
        """Cancel in-flight work, delete partial artifacts, keep pending for restart."""
        self.request_cancel()
        with self._lock:
            items = list({*self._active.keys(), *self._load_pending_unlocked()})
            # Ensure every active is in pending for next open
            pending = self._load_pending_unlocked()
            for item in items:
                if item not in pending:
                    pending.append(item)
            self._save_pending_unlocked(pending)
            self._active.clear()

        for kind, key in items:
            try:
                discard_partial(kind, key)
            except Exception:
                pass
        return [PendingDownload(k, v) for k, v in items]

    def revert_pending_on_disk(self) -> List[PendingDownload]:
        """Delete partials for every pending entry (start-over prep). Keeps pending list."""
        with self._lock:
            items = list(self._load_pending_unlocked())
        for kind, key in items:
            try:
                discard_partial(kind, key)
            except Exception:
                pass
        return [PendingDownload(k, v) for k, v in items]

    def _load_pending_unlocked(self) -> List[PendingItem]:
        path = _pending_path()
        if not path.is_file():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        out: List[PendingItem] = []
        if not isinstance(raw, list):
            return out
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            kind = entry.get("kind")
            key = entry.get("key")
            if isinstance(kind, str) and isinstance(key, str) and kind and key:
                item = (kind, key)
                if item not in out:
                    out.append(item)
        return out

    def _save_pending_unlocked(self, items: Iterable[PendingItem]) -> None:
        path = _pending_path()
        payload = [{"kind": k, "key": v} for k, v in items]
        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass


def discard_partial(kind: str, key: str) -> None:
    """Remove incomplete download artifacts so the next install starts clean."""
    if kind == KIND_ENHANCE:
        from backend.tools.constant import EnhanceMode
        from backend.tools import enhance_models as m

        m.discard_partial(EnhanceMode(key))
    elif kind == KIND_LOW_LIGHT:
        from backend.tools.constant import LowLightMode
        from backend.tools import low_light_models as m

        m.discard_partial(LowLightMode(key))
    elif kind == KIND_GENERATE:
        from backend.tools.constant import GenerateMode
        from backend.tools import generate_models as m

        m.discard_partial(GenerateMode(key))
    elif kind == KIND_BG_REMOVE:
        from backend.tools.constant import BgRemoveMode
        from backend.tools import bg_remove_models as m

        m.discard_partial(BgRemoveMode(key))
    elif kind == KIND_SELECT_OBJECT:
        from backend.tools.select_object_models import SelectObjectPairId
        from backend.tools import select_object_models as m

        m.discard_pair_partial(SelectObjectPairId(key))
    else:
        raise ValueError(f"Unknown download kind: {kind}")


def urllib_cancel_reporthook(block_num: int, block_size: int, total_size: int) -> None:
    """Pass to urlretrieve(..., reporthook=...) so close/CLI can abort."""
    ModelDownloadRegistry.instance().check_cancelled()
