"""Dependency-aware scheduling and device admission for graph execution.

Two separate jobs live here:

* **Ordering** - `execution_waves` groups a plan's nodes into dependency levels, so
  branches that do not feed each other can run at the same time instead of being
  walked in whatever order the plan happened to list them.
* **Admission** - `DeviceScheduler` decides how many of those may actually run at
  once. Independence is not permission: two model nodes that both want the GPU
  must still take turns, or they race for the same VRAM and one loses.

Keeping the two apart is deliberate. Ordering is a property of the workflow and is
fully testable; admission is a property of the machine.
"""

from __future__ import annotations

import os
import threading
from collections import deque
from contextlib import contextmanager
from typing import Iterable, Iterator, Mapping, Sequence

HEAVY = "heavy"
LIGHT = "light"

# Light nodes are file and pixel work (load, save, composite, literals). More than
# a handful of threads stops helping, because they contend on disk and the GIL.
_DEFAULT_LIGHT_SLOTS = 4


class DependencyCycle(RuntimeError):
    """The active subgraph contains a cycle and cannot be ordered."""


# Adapters that dispatch a job to the shared inference worker, and therefore hold
# model weights on a device. Kept in step with the job_types map in
# RunManager._run_node - a node is heavy exactly when that map has an entry for it.
# `required_models` looks like the natural signal but is not: nodes such as
# lluna.image.upscale pick their model from a parameter and declare nothing, so
# trusting it would let two model jobs run at once.
INFERENCE_ADAPTERS = frozenset(
    {
        "enhance",
        "low_light",
        "generate",
        "lama_retouch",
        "select_subject",
        "subtitle",
        "birefnet",
        "describe_image",
    }
)


def node_kind(definition) -> str:
    """Whether a node occupies an inference device or merely the CPU.

    Everything outside `INFERENCE_ADAPTERS` - loaders, savers, literals,
    compositing, effects - is CPU work that may overlap freely.
    """
    if str(getattr(definition, "adapter", "")) in INFERENCE_ADAPTERS:
        return HEAVY
    return HEAVY if getattr(definition, "required_models", None) else LIGHT


def dependencies(
    node_ids: Sequence[str], edges: Iterable
) -> dict[str, frozenset[str]]:
    """Map each node to the active nodes it consumes output from.

    Edges reaching outside the active set are ignored: those values are resolved
    up front as boundary inputs and impose no ordering.
    """
    active = set(node_ids)
    found: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in edges:
        target = edge.target_node_id
        source = edge.source_node_id
        if target in active and source in active and source != target:
            found[target].add(source)
    return {node_id: frozenset(sources) for node_id, sources in found.items()}


def execution_waves(
    node_ids: Sequence[str], edges: Iterable
) -> tuple[tuple[str, ...], ...]:
    """Group nodes into levels; every node in a level depends only on earlier ones.

    Order within a level follows ``node_ids``, so a plan executes deterministically
    whether or not concurrency is switched on.
    """
    required = dependencies(node_ids, edges)
    remaining = {node_id: set(sources) for node_id, sources in required.items()}
    waves: list[tuple[str, ...]] = []
    settled: set[str] = set()
    queue = deque(node_ids)
    while queue:
        wave = tuple(
            node_id for node_id in queue if not (remaining[node_id] - settled)
        )
        if not wave:
            raise DependencyCycle(
                "These nodes depend on each other: " + ", ".join(sorted(queue))
            )
        waves.append(wave)
        settled.update(wave)
        queue = deque(node_id for node_id in queue if node_id not in settled)
    return tuple(waves)


def concurrency_enabled() -> bool:
    """Kill switch: ``LLUNA_GRAPH_CONCURRENCY=0`` restores strictly serial runs."""
    return os.environ.get("LLUNA_GRAPH_CONCURRENCY", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def inference_devices() -> tuple[str, ...]:
    """Devices that can host a heavy job, best first.

    Today this is the set of usable accelerators, but the number of *heavy slots*
    is capped by how many inference workers exist, not by how many GPUs are
    plugged in - see ``DeviceScheduler``.
    """
    try:
        from backend.hardware.detector import get_hardware_profile

        profile = get_hardware_profile()
    except (ImportError, OSError, RuntimeError):
        return ("cpu",)
    devices = [
        device["id"]
        for device in profile.devices()
        if device["backend"] in {"cuda", "directml", "mps"}
    ]
    return tuple(devices) or ("cpu",)


class DeviceScheduler:
    """Hands out execution slots: one heavy job per device, many light jobs.

    ``heavy_devices`` is the list of devices a heavy job may be placed on. It is
    deliberately supplied by the caller rather than read from the hardware here,
    because the real constraint is the number of inference *workers* available -
    a second GPU only becomes a second heavy slot once a worker is pinned to it.
    """

    def __init__(
        self,
        heavy_devices: Sequence[str] = ("cuda:0",),
        light_slots: int = _DEFAULT_LIGHT_SLOTS,
    ) -> None:
        if not heavy_devices:
            raise ValueError("At least one device is required for heavy jobs.")
        self._free_devices = deque(heavy_devices)
        self._devices_lock = threading.Lock()
        self._heavy = threading.Semaphore(len(heavy_devices))
        self._light = threading.Semaphore(max(1, light_slots))

    @property
    def heavy_capacity(self) -> int:
        with self._devices_lock:
            return len(self._free_devices)

    @contextmanager
    def slot(self, kind: str) -> Iterator[str]:
        """Occupy a slot for ``kind``, blocking until one frees up."""
        if kind == HEAVY:
            self._heavy.acquire()
            with self._devices_lock:
                device = self._free_devices.popleft()
            try:
                yield device
            finally:
                with self._devices_lock:
                    self._free_devices.append(device)
                self._heavy.release()
        else:
            self._light.acquire()
            try:
                yield "cpu"
            finally:
                self._light.release()


def plan_concurrency(
    wave: Sequence[str], kinds: Mapping[str, str], scheduler: DeviceScheduler
) -> int:
    """How many workers are worth starting for one wave.

    Never more than the wave itself, and never more than the slots that could
    actually be occupied: spinning up threads that will immediately block on the
    heavy semaphore only makes the run harder to follow in the logs.
    """
    heavy = sum(1 for node_id in wave if kinds.get(node_id) == HEAVY)
    light = len(wave) - heavy
    return max(1, min(len(wave), min(heavy, scheduler.heavy_capacity) + light))
