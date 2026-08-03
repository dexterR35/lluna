"""Semantic workflow validation and cycle detection."""

from __future__ import annotations

from collections import defaultdict, deque

from backend.graph.registry import NODE_REGISTRY
from backend.graph.schema import ValidationIssue, ValidationResult, WorkflowDocument
from backend.graph.types import PortType, ports_compatible


def _port(definition, port_id: str, *, output: bool):
    ports = definition.outputs if output else definition.inputs
    return next((item for item in ports if item.id == port_id), None)


def topological_order(workflow: WorkflowDocument) -> list[str]:
    node_ids = {node.id for node in workflow.nodes}
    incoming = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in workflow.edges:
        if edge.source_node_id in node_ids and edge.target_node_id in node_ids:
            outgoing[edge.source_node_id].append(edge.target_node_id)
            incoming[edge.target_node_id] += 1
    queue = deque(sorted(node_id for node_id, count in incoming.items() if count == 0))
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for target in outgoing[current]:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    return ordered


def validate_workflow(workflow: WorkflowDocument) -> ValidationResult:
    issues: list[ValidationIssue] = []
    nodes = {node.id: node for node in workflow.nodes}
    if len(nodes) != len(workflow.nodes):
        issues.append(ValidationIssue(severity="error", code="DUPLICATE_NODE_ID", message="Node IDs must be unique."))
    seen_edges: set[str] = set()
    connected_inputs: dict[tuple[str, str], int] = defaultdict(int)
    for node in workflow.nodes:
        definition = NODE_REGISTRY.get(node.schema_id)
        if definition is None:
            issues.append(ValidationIssue(severity="error", code="UNKNOWN_NODE", message=f"Unknown node type: {node.schema_id}", node_id=node.id, action="Remove or migrate this node."))
            continue
        if node.schema_version != definition.schema_version:
            issues.append(ValidationIssue(severity="error", code="NODE_VERSION", message=f"Unsupported schema version for {definition.name}.", node_id=node.id, action="Migrate this workflow."))
        if not definition.available:
            issues.append(ValidationIssue(severity="error", code="NODE_UNAVAILABLE", message=definition.unavailable_reason or f"{definition.name} is unavailable.", node_id=node.id))
        for parameter in definition.parameters:
            if parameter.required and not node.parameters.get(parameter.id):
                issues.append(ValidationIssue(severity="error", code="REQUIRED_PARAMETER", message=f"{parameter.label} is required.", node_id=node.id))
            value = node.parameters.get(parameter.id)
            if value is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
                if parameter.minimum is not None and value < parameter.minimum:
                    issues.append(ValidationIssue(severity="error", code="PARAMETER_RANGE", message=f"{parameter.label} is below {parameter.minimum}.", node_id=node.id))
                if parameter.maximum is not None and value > parameter.maximum:
                    issues.append(ValidationIssue(severity="error", code="PARAMETER_RANGE", message=f"{parameter.label} is above {parameter.maximum}.", node_id=node.id))
    for edge in workflow.edges:
        if edge.id in seen_edges:
            issues.append(ValidationIssue(severity="error", code="DUPLICATE_EDGE_ID", message="Edge IDs must be unique.", edge_id=edge.id))
        seen_edges.add(edge.id)
        source = nodes.get(edge.source_node_id)
        target = nodes.get(edge.target_node_id)
        if source is None or target is None:
            issues.append(ValidationIssue(severity="error", code="DANGLING_EDGE", message="Connection references a missing node.", edge_id=edge.id))
            continue
        source_definition = NODE_REGISTRY.get(source.schema_id)
        target_definition = NODE_REGISTRY.get(target.schema_id)
        if source_definition is None or target_definition is None:
            continue
        source_port = _port(source_definition, edge.source_port_id, output=True)
        target_port = _port(target_definition, edge.target_port_id, output=False)
        if source_port is None or target_port is None:
            issues.append(ValidationIssue(severity="error", code="UNKNOWN_PORT", message="Connection references an unknown port.", edge_id=edge.id))
            continue
        if not ports_compatible(PortType(source_port.type), PortType(target_port.type)):
            issues.append(ValidationIssue(severity="error", code="INCOMPATIBLE_PORTS", message=f"{source_port.label} ({source_port.type}) cannot connect to {target_port.label} ({target_port.type}).", edge_id=edge.id))
        key = (target.id, target_port.id)
        connected_inputs[key] += 1
        if connected_inputs[key] > 1 and not target_port.multiple:
            issues.append(ValidationIssue(severity="error", code="DUPLICATE_INPUT", message=f"{target_port.label} accepts only one connection.", node_id=target.id, edge_id=edge.id))
    for node in workflow.nodes:
        definition = NODE_REGISTRY.get(node.schema_id)
        if definition is None or node.disabled:
            continue
        for input_port in definition.inputs:
            if input_port.required and not connected_inputs[(node.id, input_port.id)]:
                issues.append(ValidationIssue(severity="error", code="MISSING_INPUT", message=f"{input_port.label} is required.", node_id=node.id, action="Connect a compatible output."))
    if len(topological_order(workflow)) != len(nodes):
        issues.append(ValidationIssue(severity="error", code="CYCLE", message="Workflow cycles are not supported.", action="Remove the feedback connection."))
    if workflow.nodes and not any(NODE_REGISTRY.get(node.schema_id) and NODE_REGISTRY[node.schema_id].kind == "output" for node in workflow.nodes):
        issues.append(ValidationIssue(severity="warning", code="NO_OUTPUT", message="Workflow has no preview or save output."))
    return ValidationResult(valid=not any(issue.severity == "error" for issue in issues), issues=issues)
