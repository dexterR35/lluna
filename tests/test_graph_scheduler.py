"""Wave ordering and device admission."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from backend.graph.scheduler import (
    HEAVY,
    LIGHT,
    DependencyCycle,
    DeviceScheduler,
    concurrency_enabled,
    dependencies,
    execution_waves,
    node_kind,
    plan_concurrency,
)


def _edge(source: str, target: str) -> SimpleNamespace:
    return SimpleNamespace(source_node_id=source, target_node_id=target)


def test_chain_is_one_node_per_wave():
    waves = execution_waves(["a", "b", "c"], [_edge("a", "b"), _edge("b", "c")])

    assert waves == (("a",), ("b",), ("c",))


def test_independent_branches_share_a_wave():
    """load -> {upscale, caption} is the case worth parallelising."""
    edges = [_edge("load", "upscale"), _edge("load", "caption")]

    waves = execution_waves(["load", "upscale", "caption"], edges)

    assert waves == (("load",), ("upscale", "caption"))


def test_join_waits_for_every_branch():
    edges = [
        _edge("load", "left"),
        _edge("load", "right"),
        _edge("left", "join"),
        _edge("right", "join"),
    ]

    waves = execution_waves(["load", "left", "right", "join"], edges)

    assert waves == (("load",), ("left", "right"), ("join",))


def test_wave_order_follows_the_plan_order():
    """Deterministic runs whether or not concurrency is enabled."""
    waves = execution_waves(["b", "a", "c"], [])

    assert waves == (("b", "a", "c"),)


def test_edges_leaving_the_active_set_impose_no_ordering():
    """Boundary inputs are resolved before execution, so they are not dependencies."""
    waves = execution_waves(["b"], [_edge("outside", "b")])

    assert waves == (("b",),)
    assert dependencies(["b"], [_edge("outside", "b")]) == {"b": frozenset()}


def test_a_cycle_is_reported_rather_than_hanging():
    with pytest.raises(DependencyCycle, match="depend on each other"):
        execution_waves(["a", "b"], [_edge("a", "b"), _edge("b", "a")])


def test_self_edge_is_not_a_dependency_on_itself():
    assert execution_waves(["a"], [_edge("a", "a")]) == (("a",),)


def test_model_backed_nodes_are_heavy():
    assert node_kind(SimpleNamespace(adapter="enhance", required_models=[])) == HEAVY
    assert node_kind(SimpleNamespace(adapter="save", required_models=["flux"])) == HEAVY
    assert node_kind(SimpleNamespace(adapter="save", required_models=[])) == LIGHT
    assert node_kind(SimpleNamespace()) == LIGHT


def test_every_real_node_that_reaches_the_worker_is_classified_heavy():
    """Guards the drift that made two upscales run at once: the heavy marker must
    match the adapters RunManager._run_node actually dispatches as worker jobs."""
    import inspect

    from backend.graph import executor
    from backend.graph.registry import NODE_REGISTRY
    from backend.graph.scheduler import INFERENCE_ADAPTERS

    source = inspect.getsource(executor)
    dispatched = {
        adapter for adapter in INFERENCE_ADAPTERS if f'"{adapter}": JobType.' in source
    }
    assert dispatched == set(INFERENCE_ADAPTERS), (
        "INFERENCE_ADAPTERS disagrees with the job_types map in the executor"
    )

    for definition in NODE_REGISTRY.values():
        if str(getattr(definition, "adapter", "")) in INFERENCE_ADAPTERS:
            assert node_kind(definition) == HEAVY, definition.schema_id


def test_one_heavy_job_per_device():
    scheduler = DeviceScheduler(heavy_devices=("cuda:0",))
    overlapped = threading.Event()
    released = threading.Event()

    def hold():
        with scheduler.slot(HEAVY):
            released.wait(timeout=2)

    holder = threading.Thread(target=hold)
    holder.start()
    time.sleep(0.05)

    def second():
        with scheduler.slot(HEAVY):
            overlapped.set()

    contender = threading.Thread(target=second)
    contender.start()
    assert not overlapped.wait(timeout=0.2), "two heavy jobs shared one device"

    released.set()
    holder.join(timeout=2)
    assert overlapped.wait(timeout=2)
    contender.join(timeout=2)


def test_two_devices_admit_two_heavy_jobs():
    scheduler = DeviceScheduler(heavy_devices=("cuda:0", "cuda:1"))
    both = threading.Barrier(2, timeout=2)
    used: list[str] = []
    lock = threading.Lock()

    def run():
        with scheduler.slot(HEAVY) as device:
            with lock:
                used.append(device)
            both.wait()  # only passes if both hold a slot at once

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert sorted(used) == ["cuda:0", "cuda:1"]


def test_light_jobs_run_together():
    scheduler = DeviceScheduler(heavy_devices=("cuda:0",), light_slots=3)
    together = threading.Barrier(3, timeout=2)

    def run():
        with scheduler.slot(LIGHT):
            together.wait()

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_devices_are_returned_after_use():
    scheduler = DeviceScheduler(heavy_devices=("cuda:0",))
    with scheduler.slot(HEAVY) as device:
        assert device == "cuda:0"
        assert scheduler.heavy_capacity == 0
    assert scheduler.heavy_capacity == 1


def test_device_is_released_even_when_the_node_fails():
    scheduler = DeviceScheduler(heavy_devices=("cuda:0",))
    with pytest.raises(RuntimeError):
        with scheduler.slot(HEAVY):
            raise RuntimeError("node blew up")

    assert scheduler.heavy_capacity == 1


def test_worker_count_never_exceeds_what_can_be_admitted():
    scheduler = DeviceScheduler(heavy_devices=("cuda:0",))
    kinds = {"a": HEAVY, "b": HEAVY, "c": LIGHT}

    # Two heavy nodes but one device: only one heavy plus the light node.
    assert plan_concurrency(("a", "b", "c"), kinds, scheduler) == 2
    assert plan_concurrency(("a", "b"), kinds, scheduler) == 1
    assert plan_concurrency(("c",), kinds, scheduler) == 1


def test_concurrency_kill_switch(monkeypatch):
    monkeypatch.delenv("LLUNA_GRAPH_CONCURRENCY", raising=False)
    assert concurrency_enabled() is True
    monkeypatch.setenv("LLUNA_GRAPH_CONCURRENCY", "0")
    assert concurrency_enabled() is False
