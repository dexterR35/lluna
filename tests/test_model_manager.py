"""ModelManager/DynamicRuntimeManager: one shared cache and eviction policy
for both builtin and manifest-backed (custom) models.

Before this, a custom model cached in DynamicRuntimeManager was invisible to
the ad hoc release_*() sweep builtin jobs ran between each other - these
tests exercise the generic acquire/evict_except path directly with lightweight
fake adapters, so they don't need real torch/GPU-backed runtimes.
"""

from __future__ import annotations

from backend.models.adapters import DynamicRuntimeManager, RuntimeAdapter
from backend.models.manager import ModelManager


class _FakeAdapter(RuntimeAdapter):
    id = "fake"

    def __init__(self) -> None:
        self.loaded_count = 0
        self.unloaded: list[str] = []

    def load(self, record=None, *, dtype=None):
        self.loaded_count += 1
        return f"payload-{self.loaded_count}"

    def run(self, loaded, inputs, *, progress=None, cancel_event=None):
        return loaded

    def unload(self, loaded) -> None:
        self.unloaded.append(loaded)


def _fresh_manager() -> DynamicRuntimeManager:
    return DynamicRuntimeManager(cache_size=2)


def test_acquire_reuses_a_cached_entry_without_reloading():
    manager = _fresh_manager()
    adapter = _FakeAdapter()

    first = manager.acquire("key-a", adapter, adapter.load)
    second = manager.acquire("key-a", adapter, adapter.load)

    assert first == second == "payload-1"
    assert adapter.loaded_count == 1


def test_evict_except_unloads_everything_but_the_kept_key():
    manager = _fresh_manager()
    builtin = _FakeAdapter()
    custom = _FakeAdapter()

    manager.acquire("builtin:x", builtin, builtin.load)
    manager.acquire("custom-model:auto", custom, custom.load)

    manager.evict_except("builtin:x")

    assert custom.unloaded == ["payload-1"]
    assert builtin.unloaded == []
    assert len(manager._cache) == 1
    assert "builtin:x" in manager._cache


def test_lru_eviction_crosses_builtin_and_custom_pools():
    """The whole point of ModelManager: a resident custom model must not be
    invisible to eviction just because the next job is a builtin one, and
    vice versa - both share the same OrderedDict and cache_size budget."""
    manager = _fresh_manager()  # cache_size=2
    builtin_a = _FakeAdapter()
    custom_b = _FakeAdapter()
    builtin_c = _FakeAdapter()

    manager.acquire("builtin:a", builtin_a, builtin_a.load)
    manager.acquire("custom:b", custom_b, custom_b.load)
    # A third entry over budget must evict the least-recently-used one
    # (builtin:a), regardless of which pool it came from.
    manager.acquire("builtin:c", builtin_c, builtin_c.load)

    assert builtin_a.unloaded == ["payload-1"]
    assert custom_b.unloaded == []
    assert builtin_c.unloaded == []
    assert set(manager._cache) == {"custom:b", "builtin:c"}


def test_model_manager_acquire_model_delegates_to_shared_cache(monkeypatch):
    DynamicRuntimeManager._instance = _fresh_manager()
    from backend.models import builtin_adapters

    fake = _FakeAdapter()
    fake.id = "builtin:fake"
    monkeypatch.setitem(builtin_adapters.BUILTIN_ADAPTERS, "builtin:fake", fake)

    with ModelManager.instance().acquire_model("builtin:fake") as lease:
        assert lease.adapter is fake
        assert lease.loaded == "payload-1"

    ModelManager.instance().evict_except(None)
    assert fake.unloaded == ["payload-1"]


def test_runtime_adapter_default_estimate_and_health_check():
    from types import SimpleNamespace

    record = SimpleNamespace(
        manifest=SimpleNamespace(id="m", hardware=SimpleNamespace(minimum_vram_mb=0.0))
    )

    adapter = RuntimeAdapter()
    budget = adapter.estimate(record)
    assert budget.estimated_mb == 0.0  # no CUDA budget / undeclared minimum -> no-op
    assert adapter.health_check("anything") is True
    assert adapter.health_check(None) is False
