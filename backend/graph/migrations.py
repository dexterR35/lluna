"""Bringing saved workflows forward when a node's contract changes.

`NodeDefinition.schema_version` is bumped whenever a node's parameters or ports
change shape. Validation refuses a workflow whose node is at an older version,
which is correct — running it would silently misinterpret old parameters — but on
its own that turns every saved workflow into a dead file the first time a node
evolves.

A migration closes that gap: a small function per (node, version step) that
rewrites the saved node into the newer shape. They chain, so a node saved at v1
migrates to v3 by running v1→v2 then v2→v3, and a workflow from any past release
opens.

Rules that keep this trustworthy:

* Migrations take and return plain dicts, never model instances. They run *before*
  parsing, which is the only point where old data still exists unaltered.
* They never touch anything but their own node. A migration that reaches across
  the graph cannot be reasoned about or tested in isolation.
* They are pure and total: no I/O, no failure path. An unmigratable node is a
  missing migration, reported as such, not an exception mid-load.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

# (schema_id, from_version) -> function returning the node dict at from_version + 1
NodeMigration = Callable[[dict[str, Any]], dict[str, Any]]
MIGRATIONS: dict[tuple[str, int], NodeMigration] = {}


class MigrationError(RuntimeError):
    """A workflow cannot be brought forward."""


def register(schema_id: str, from_version: int) -> Callable[[NodeMigration], NodeMigration]:
    """Declare how ``schema_id`` moves from ``from_version`` to the next one.

    Example, for the day Generate Image's `steps` parameter is renamed::

        @register("lluna.generate.image", 1)
        def _steps_renamed(node):
            parameters = dict(node.get("parameters") or {})
            if "numSteps" in parameters:
                parameters["steps"] = parameters.pop("numSteps")
            return {**node, "parameters": parameters}

    Nothing is registered today: no shipped node has needed a second version yet.
    The machinery exists so that the first one does not break saved work.
    """

    def decorate(function: NodeMigration) -> NodeMigration:
        key = (schema_id, from_version)
        if key in MIGRATIONS:
            raise ValueError(f"A migration for {schema_id} v{from_version} already exists.")
        MIGRATIONS[key] = function
        return function

    return decorate


def _target_versions() -> dict[str, int]:
    from backend.graph.registry import NODE_REGISTRY

    return {
        schema_id: definition.schema_version
        for schema_id, definition in NODE_REGISTRY.items()
    }


def migrate_node(node: Mapping[str, Any], target: int) -> tuple[dict[str, Any], list[str]]:
    """Step one node up to ``target``, reporting each step applied."""
    current = dict(node)
    schema_id = str(current.get("schemaId") or current.get("schema_id") or "")
    applied: list[str] = []
    version = int(current.get("schemaVersion") or current.get("schema_version") or 1)
    while version < target:
        migration = MIGRATIONS.get((schema_id, version))
        if migration is None:
            raise MigrationError(
                f"{schema_id} was saved at version {version} and this build expects "
                f"{target}, but no migration exists for v{version}."
            )
        current = dict(migration(current))
        version += 1
        current["schemaVersion"] = version
        current.pop("schema_version", None)
        applied.append(f"{schema_id} v{version - 1}->v{version}")
    if version > target:
        raise MigrationError(
            f"{schema_id} was saved at version {version}, which is newer than this "
            f"build supports ({target}). Update Lluna to open this workflow."
        )
    return current, applied


def migrate_workflow(document: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return the workflow at current node versions, plus what was migrated.

    Unknown node types are passed through untouched: validation reports them far
    better than a migration error could, and a workflow may legitimately contain a
    node from a model whose runtime is not installed here.
    """
    targets = _target_versions()
    raw_nodes = document.get("nodes") or []
    if not isinstance(raw_nodes, list):
        raise MigrationError("This workflow's nodes are not a list.")
    migrated: list[dict[str, Any]] = []
    applied: list[str] = []
    for node in raw_nodes:
        if not isinstance(node, Mapping):
            raise MigrationError("This workflow contains a node that is not an object.")
        schema_id = str(node.get("schemaId") or node.get("schema_id") or "")
        target = targets.get(schema_id)
        if target is None:
            migrated.append(dict(node))
            continue
        updated, steps = migrate_node(node, target)
        migrated.append(updated)
        applied.extend(steps)
    return {**dict(document), "nodes": migrated}, applied


def needs_migration(document: Mapping[str, Any]) -> bool:
    targets = _target_versions()
    for node in document.get("nodes") or []:
        if not isinstance(node, Mapping):
            continue
        schema_id = str(node.get("schemaId") or node.get("schema_id") or "")
        target = targets.get(schema_id)
        if target is None:
            continue
        version = int(node.get("schemaVersion") or node.get("schema_version") or 1)
        if version != target:
            return True
    return False
