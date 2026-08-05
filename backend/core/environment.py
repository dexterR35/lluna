"""Explicit process-environment initialization."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentChange:
    name: str
    previous: str | None
    value: str


def initialize_process_environment(
    environ: MutableMapping[str, str] | None = None,
) -> tuple[EnvironmentChange, ...]:
    """Apply Lluna's required runtime variables once and report mutations."""
    target = os.environ if environ is None else environ
    changes: list[EnvironmentChange] = []
    required = {
        "KMP_DUPLICATE_LIB_OK": "True",
        # Paddle bundles BRPC.  Keep its one-second bvar/mbvar dump threads off
        # in the desktop process and every spawned inference worker.
        "FLAGS_bvar_dump": "false",
        "FLAGS_mbvar_dump": "false",
    }
    for name, value in required.items():
        previous = target.get(name)
        if previous == value:
            continue
        target[name] = value
        changes.append(EnvironmentChange(name, previous, value))
    return tuple(changes)
