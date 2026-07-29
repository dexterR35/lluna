"""Immutable, serializable operation graph used by project revisions."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any, Mapping


def _json_copy(value: Any, *, label: str) -> Any:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain finite JSON-compatible values") from exc
    return json.loads(encoded)


@dataclass(frozen=True)
class OperationNode:
    id: str
    type: str
    schema_version: int = 1
    enabled: bool = True
    strength: float = 1.0
    inputs: Mapping[str, str] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or ":" in self.id or "/" in self.id:
            raise ValueError("operation ID must be non-empty and cannot contain ':' or '/'")
        if "." not in self.type:
            raise ValueError("operation type must be namespaced")
        if self.schema_version < 1:
            raise ValueError("operation schema version must be positive")
        if not 0.0 <= float(self.strength) <= 1.0:
            raise ValueError("operation strength must be between 0 and 1")
        inputs = _json_copy(dict(self.inputs), label="operation inputs")
        if not all(
            isinstance(name, str) and name and isinstance(reference, str) and reference
            for name, reference in inputs.items()
        ):
            raise ValueError("operation inputs must map non-empty strings to references")
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(
            self,
            "parameters",
            _json_copy(dict(self.parameters), label="operation parameters"),
        )
        object.__setattr__(
            self,
            "extensions",
            _json_copy(dict(self.extensions), label="operation extensions"),
        )
        reserved = {
            "id",
            "type",
            "schema_version",
            "enabled",
            "strength",
            "inputs",
            "parameters",
        }
        if reserved.intersection(self.extensions):
            raise ValueError("operation extensions cannot replace standard fields")

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "type": self.type,
            "schema_version": self.schema_version,
            "enabled": self.enabled,
            "strength": float(self.strength),
            "inputs": deepcopy(dict(self.inputs)),
            "parameters": deepcopy(dict(self.parameters)),
        }
        data.update(deepcopy(dict(self.extensions)))
        return data

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> OperationNode:
        data = dict(value)
        known = {
            "id",
            "type",
            "schema_version",
            "enabled",
            "strength",
            "inputs",
            "parameters",
        }
        missing = {"id", "type"}.difference(data)
        if missing:
            raise ValueError(f"operation node missing: {', '.join(sorted(missing))}")
        return cls(
            id=data["id"],
            type=data["type"],
            schema_version=data.get("schema_version", 1),
            enabled=data.get("enabled", True),
            strength=data.get("strength", 1.0),
            inputs=data.get("inputs", {}),
            parameters=data.get("parameters", {}),
            extensions={key: data[key] for key in data.keys() - known},
        )


@dataclass(frozen=True)
class OperationGraph:
    nodes: tuple[OperationNode, ...] = ()
    schema_version: int = 1
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version < 1:
            raise ValueError("graph schema version must be positive")
        nodes = tuple(self.nodes)
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(
            self,
            "extensions",
            _json_copy(dict(self.extensions), label="graph extensions"),
        )
        if {"schema_version", "nodes"}.intersection(self.extensions):
            raise ValueError("graph extensions cannot replace standard fields")
        self.validate()

    def validate(self) -> None:
        by_id = {node.id: node for node in self.nodes}
        if len(by_id) != len(self.nodes):
            raise ValueError("operation IDs must be unique")
        dependencies: dict[str, set[str]] = {node.id: set() for node in self.nodes}
        for node in self.nodes:
            for reference in node.inputs.values():
                prefix, separator, _port = reference.partition(":")
                if not separator:
                    raise ValueError(
                        f"input reference '{reference}' must contain a source and port"
                    )
                if prefix in by_id:
                    dependencies[node.id].add(prefix)
                elif not prefix.startswith(("asset_", "mask_", "selection_")):
                    raise ValueError(
                        f"operation {node.id} references unknown source {prefix}"
                    )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("operation graph contains a dependency cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in dependencies[node_id]:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node in self.nodes:
            visit(node.id)

    def add(self, node: OperationNode, *, index: int | None = None) -> OperationGraph:
        nodes = list(self.nodes)
        if index is None:
            nodes.append(node)
        else:
            if not 0 <= index <= len(nodes):
                raise IndexError("operation insertion index is out of range")
            nodes.insert(index, node)
        return replace(self, nodes=tuple(nodes))

    def replace(self, node: OperationNode) -> OperationGraph:
        nodes = list(self.nodes)
        for index, existing in enumerate(nodes):
            if existing.id == node.id:
                nodes[index] = node
                return replace(self, nodes=tuple(nodes))
        raise KeyError(f"unknown operation ID: {node.id}")

    def remove(self, node_id: str) -> OperationGraph:
        for node in self.nodes:
            if node.id == node_id:
                continue
            for reference in node.inputs.values():
                if reference.partition(":")[0] == node_id:
                    raise ValueError(f"cannot remove {node_id}; it is used by {node.id}")
        nodes = tuple(node for node in self.nodes if node.id != node_id)
        if len(nodes) == len(self.nodes):
            raise KeyError(f"unknown operation ID: {node_id}")
        return replace(self, nodes=nodes)

    def move(self, node_id: str, index: int) -> OperationGraph:
        if not 0 <= index < len(self.nodes):
            raise IndexError("operation move index is out of range")
        nodes = list(self.nodes)
        current = next((i for i, node in enumerate(nodes) if node.id == node_id), None)
        if current is None:
            raise KeyError(f"unknown operation ID: {node_id}")
        node = nodes.pop(current)
        nodes.insert(index, node)
        return replace(self, nodes=tuple(nodes))

    def to_dict(self) -> dict[str, Any]:
        data = {
            "schema_version": self.schema_version,
            "nodes": [node.to_dict() for node in self.nodes],
        }
        data.update(deepcopy(dict(self.extensions)))
        return data

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> OperationGraph:
        data = dict(value)
        known = {"schema_version", "nodes"}
        raw_nodes = data.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raise ValueError("graph nodes must be a list")
        return cls(
            schema_version=data.get("schema_version", 1),
            nodes=tuple(OperationNode.from_dict(item) for item in raw_nodes),
            extensions={key: data[key] for key in data.keys() - known},
        )

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
