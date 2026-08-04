"""Deterministic content-addressed node cache keys."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable

from backend.graph.schema import WorkflowNode


def build_cache_key(
    node: WorkflowNode,
    input_hashes: Iterable[str],
    *,
    model_revision: str = "",
    implementation_revision: str = "1",
) -> str:
    payload = {
        "schemaId": node.schema_id,
        "schemaVersion": node.schema_version,
        "parameters": node.parameters,
        "inputs": sorted(input_hashes),
        "modelRevision": model_revision,
        "implementationRevision": implementation_revision,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
