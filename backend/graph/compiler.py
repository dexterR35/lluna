"""Compile validated workflows into deterministic execution plans."""

from __future__ import annotations

from collections import defaultdict

from backend.graph.cache import build_cache_key
from backend.graph.schema import ExecutionPlan, ExecutionStep, WorkflowDocument
from backend.graph.validation import scoped_node_ids, topological_order, validate_workflow


def compile_workflow(
    workflow: WorkflowDocument,
    *,
    mode: str = "all",
    selected_node_ids: list[str] | None = None,
    check_model_availability: bool = False,
) -> ExecutionPlan:
    validation = validate_workflow(
        workflow,
        mode=mode,
        selected_node_ids=selected_node_ids,
        check_model_availability=check_model_availability,
    )
    if not validation.valid:
        return ExecutionPlan(workflow_id=workflow.project_id, steps=[], validation=validation)
    active = scoped_node_ids(workflow, mode=mode, selected_node_ids=selected_node_ids)
    dependencies: dict[str, list[str]] = defaultdict(list)
    for edge in workflow.edges:
        if edge.source_node_id in active and edge.target_node_id in active:
            dependencies[edge.target_node_id].append(edge.source_node_id)
    nodes = {node.id: node for node in workflow.nodes}
    steps = [
        ExecutionStep(
            index=index,
            node_id=node_id,
            schema_id=nodes[node_id].schema_id,
            dependencies=sorted(set(dependencies[node_id])),
            cache_key=build_cache_key(nodes[node_id], []),
        )
        for index, node_id in enumerate(topological_order(workflow, active))
        if not nodes[node_id].disabled
    ]
    return ExecutionPlan(workflow_id=workflow.project_id, steps=steps, validation=validation)
