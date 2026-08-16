"""Single acquisition/eviction authority for every in-process model.

Before this module, manifest-backed custom models lived in
`DynamicRuntimeManager`'s LRU cache (`backend/models/adapters.py`) while
built-in runtimes (Real-ESRGAN, MIRNet, LaMa, ...) were loaded/released ad hoc
by `backend/tools/inference/worker.py`, invisible to each other's VRAM use. A
custom model cached in `DynamicRuntimeManager` was never evicted when a
built-in job's cleanup swept the process, and vice versa - both pools now
share one `OrderedDict` LRU cache and one eviction policy via
`DynamicRuntimeManager.acquire`/`evict_except`.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from backend.models.adapters import DynamicRuntimeManager, RuntimeAdapter
from backend.models.builtin_adapters import BUILTIN_ADAPTERS


@dataclass(frozen=True)
class ModelLease:
    adapter: RuntimeAdapter
    loaded: Any


class ModelManager:
    """Facade over `DynamicRuntimeManager`'s shared cache for builtin adapters."""

    _instance: "ModelManager | None" = None

    @classmethod
    def instance(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def adapter(self, adapter_id: str) -> RuntimeAdapter:
        try:
            return BUILTIN_ADAPTERS[adapter_id]
        except KeyError as exc:
            raise KeyError(f"No builtin adapter registered for {adapter_id!r}.") from exc

    @contextmanager
    def acquire_model(
        self,
        adapter_id: str,
        *,
        cache_key: str | None = None,
        loader: Callable[[], Any] | None = None,
    ) -> Iterator[ModelLease]:
        """Reuse-or-load the builtin model behind `adapter_id`.

        `cache_key` defaults to `adapter_id` itself - built-in runtimes only
        ever hold one resident configuration at a time (a single global
        singleton per module), unlike manifest models which are keyed by
        `model_id:dtype`.
        """
        adapter = self.adapter(adapter_id)
        key = cache_key or adapter_id
        load = loader or (lambda: adapter.load())
        loaded = DynamicRuntimeManager.instance().acquire(key, adapter, load)
        yield ModelLease(adapter=adapter, loaded=loaded)

    def evict_except(self, keep_adapter_id: str | None, *, keep_cache_key: str | None = None) -> None:
        """Unload every cached model (builtin or custom) except one.

        `keep_adapter_id=None` evicts everything. Otherwise the kept cache key
        defaults to `keep_adapter_id` itself, matching `acquire_model`'s default.
        """
        keep_key = None if keep_adapter_id is None else (keep_cache_key or keep_adapter_id)
        DynamicRuntimeManager.instance().evict_except(keep_key)
