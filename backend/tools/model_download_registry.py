"""Track in-flight model installs: cancel → revert partials; reopen → start over."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

from backend.core.atomic import atomic_write_json
from backend.core.paths import AppPaths

# (kind, key) e.g. ("enhance", "x2plus"), ("select_object", "fast")
PendingItem = Tuple[str, str]

KIND_ENHANCE = "enhance"
KIND_LOW_LIGHT = "low_light"
KIND_GENERATE = "generate"
KIND_BG_REMOVE = "bg_remove"
KIND_SELECT_OBJECT = "select_object"
_progress_context = threading.local()


class DownloadCancelled(Exception):
    """Raised when a model download is aborted (app close / CLI / cancel)."""


@dataclass(frozen=True)
class PendingDownload:
    kind: str
    key: str


def _pending_path() -> Path:
    path = AppPaths.resolve().config_dir
    path.mkdir(parents=True, exist_ok=True)
    return path / "pending_model_downloads.json"


def _cancel_flag_path() -> Path:
    path = AppPaths.resolve().config_dir
    path.mkdir(parents=True, exist_ok=True)
    return path / "model_download_cancel.flag"


class ModelDownloadRegistry:
    """Process-wide registry for Settings / ensure_* model downloads."""

    _instance: Optional["ModelDownloadRegistry"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._job_cancel: Optional[threading.Event] = None
        self._active: dict[PendingItem, bool] = {}

    @classmethod
    def instance(cls) -> "ModelDownloadRegistry":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_cancelled(self) -> bool:
        job_cancel = self._job_cancel
        if job_cancel is not None and job_cancel.is_set():
            return True
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

    def schedule(self, kind: str, key: str) -> None:
        """Persist a future download without marking it active (first-run seeding)."""
        item = (kind, str(key))
        with self._lock:
            pending = self._load_pending_unlocked()
            if item not in pending:
                pending.append(item)
                self._save_pending_unlocked(pending)

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
        from backend.tools.model_download_queue import ModelDownloadQueue

        ModelDownloadQueue.instance().report_current_progress(
            100,
            detail="Installed",
        )
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
                pending = self._load_pending_unlocked()
                remaining = [p for p in pending if p != item]
                if remaining != pending:
                    self._save_pending_unlocked(remaining)

    def list_pending(self) -> List[PendingDownload]:
        with self._lock:
            return [PendingDownload(k, v) for k, v in self._load_pending_unlocked()]

    def list_active(self) -> List[PendingDownload]:
        with self._lock:
            return [PendingDownload(k, v) for k, v in self._active.keys()]

    def abort_all_and_revert(self) -> List[PendingDownload]:
        """Cancel in-flight work, delete partial artifacts, keep pending for restart."""
        with self._lock:
            items = list({*self._active.keys(), *self._load_pending_unlocked()})
        if not items:
            # Normal shutdown while idle must not poison a later install click.
            self.clear_cancel()
            return []

        self.request_cancel()
        with self._lock:
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
        except json.JSONDecodeError:
            backup = path.with_name(
                f"{path.name}.corrupt-{int(time.time())}"
            )
            try:
                path.replace(backup)
            except OSError:
                pass
            return []
        except OSError:
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
            atomic_write_json(path, payload)
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
    if total_size > 0:
        downloaded = min(max(0, block_num * block_size), total_size)
        report_install_progress(
            int(downloaded * 100 / total_size),
            f"{downloaded} / {total_size} bytes",
            downloaded_bytes=downloaded,
            total_bytes=total_size,
        )


def report_install_progress(
    percent: int,
    detail: str = "",
    *,
    downloaded_bytes: Optional[int] = None,
    total_bytes: Optional[int] = None,
) -> None:
    """Scale raw download progress into the current model job's range."""
    start, end = getattr(_progress_context, "progress_range", (0, 95))
    raw = max(0, min(100, int(percent)))
    scaled = int(start + ((end - start) * raw / 100))
    from backend.tools.model_download_queue import ModelDownloadQueue

    ModelDownloadQueue.instance().report_current_progress(
        scaled,
        detail=detail,
        downloaded_bytes=downloaded_bytes,
        total_bytes=total_bytes,
    )


@contextmanager
def download_progress_range(start: int, end: int) -> Iterator[None]:
    """Map a nested model/file download into part of the overall job."""
    previous = getattr(_progress_context, "progress_range", None)
    _progress_context.progress_range = (
        max(0, min(100, int(start))),
        max(0, min(100, int(end))),
    )
    try:
        yield
    finally:
        if previous is None:
            try:
                del _progress_context.progress_range
            except AttributeError:
                pass
        else:
            _progress_context.progress_range = previous


@contextmanager
def download_cancellation_scope(cancel_event: threading.Event) -> Iterator[None]:
    """Make one queue job's stop event visible to download helper threads."""
    registry = ModelDownloadRegistry.instance()
    with registry._lock:
        previous = registry._job_cancel
        registry._job_cancel = cancel_event
    try:
        yield
    finally:
        with registry._lock:
            if registry._job_cancel is cancel_event:
                registry._job_cancel = previous


@contextmanager
def huggingface_download_total(total_bytes: int) -> Iterator[None]:
    """Provide the known snapshot total to Hugging Face progress bars."""
    previous = getattr(_progress_context, "hf_total_bytes", None)
    _progress_context.hf_total_bytes = max(0, int(total_bytes))
    try:
        yield
    finally:
        if previous is None:
            try:
                del _progress_context.hf_total_bytes
            except AttributeError:
                pass
        else:
            _progress_context.hf_total_bytes = previous


def huggingface_progress_tqdm():
    """Return a quiet tqdm class that forwards aggregate snapshot bytes."""
    from tqdm.auto import tqdm

    class _ModelDownloadTqdm(tqdm):
        def __init__(self, *args, **kwargs):
            self._midgard_track_bytes = False
            progress_name = str(kwargs.pop("name", ""))
            description = str(kwargs.get("desc", ""))
            unit = kwargs.get("unit")
            # tqdm short-circuits its byte counter when disabled. Keep counting
            # active, but suppress terminal rendering through display()/clear().
            kwargs["disable"] = False
            super().__init__(*args, **kwargs)
            self._midgard_track_bytes = (
                unit == "B"
                and (
                    progress_name == "huggingface_hub.snapshot_download"
                    or description.startswith("Downloading (incomplete total")
                    or description.startswith("Reconstructing")
                )
            )
            self._report_midgard_progress()

        def update(self, n=1):
            result = super().update(n)
            self._report_midgard_progress()
            return result

        def refresh(self, *args, **kwargs):
            result = super().refresh(*args, **kwargs)
            self._report_midgard_progress()
            return result

        def display(self, *args, **kwargs) -> None:
            return None

        def clear(self, *args, **kwargs) -> None:
            return None

        def _report_midgard_progress(self) -> None:
            ModelDownloadRegistry.instance().check_cancelled()
            if not getattr(self, "_midgard_track_bytes", False):
                return
            total = getattr(_progress_context, "hf_total_bytes", 0)
            if total <= 0:
                total = int(self.total or 0)
            if total <= 0:
                return
            current = max(0, min(int(self.n or 0), total))
            report_install_progress(
                int(current * 100 / total),
                f"{current} / {total} bytes",
                downloaded_bytes=current,
                total_bytes=total,
            )

    return _ModelDownloadTqdm


def pooch_progress_tqdm():
    """Return a quiet tqdm class for rembg/pooch byte progress."""
    from tqdm.auto import tqdm

    class _PoochDownloadTqdm(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = False
            super().__init__(*args, **kwargs)
            self._report_midgard_progress()

        def update(self, n=1):
            result = super().update(n)
            self._report_midgard_progress()
            return result

        def refresh(self, *args, **kwargs):
            result = super().refresh(*args, **kwargs)
            self._report_midgard_progress()
            return result

        def display(self, *args, **kwargs) -> None:
            return None

        def clear(self, *args, **kwargs) -> None:
            return None

        def _report_midgard_progress(self) -> None:
            ModelDownloadRegistry.instance().check_cancelled()
            total = int(getattr(self, "total", 0) or 0)
            if total <= 0:
                return
            current = max(
                0,
                min(int(getattr(self, "n", 0) or 0), total),
            )
            report_install_progress(
                int(current * 100 / total),
                f"{current} / {total} bytes",
                downloaded_bytes=current,
                total_bytes=total,
            )

    return _PoochDownloadTqdm


@contextmanager
def pooch_download_progress() -> Iterator[None]:
    """Forward pooch's built-in progressbar to the active model queue."""
    import pooch.downloaders

    progress_class = pooch_progress_tqdm()
    previous = pooch.downloaders.tqdm
    pooch.downloaders.tqdm = progress_class
    try:
        yield
    finally:
        if pooch.downloaders.tqdm is progress_class:
            pooch.downloaders.tqdm = previous
