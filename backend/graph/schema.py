"""Versioned backend-owned graph contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.graph.types import PortType


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel, populate_by_name=True, extra="allow", use_enum_values=True
    )


class PortDefinition(ContractModel):
    id: str
    label: str
    type: PortType
    required: bool = False
    multiple: bool = False
    description: str = ""


class ParameterDefinition(ContractModel):
    id: str
    label: str
    type: str
    default: Any = None
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: list[dict[str, Any]] = Field(default_factory=list)
    description: str = ""


class NodeDefinition(ContractModel):
    schema_version: int = 1
    schema_id: str
    version: int = 1
    name: str
    category: str
    description: str
    icon: str = "box"
    kind: Literal["input", "processor", "output", "utility"] = "processor"
    inputs: list[PortDefinition] = Field(default_factory=list)
    outputs: list[PortDefinition] = Field(default_factory=list)
    parameters: list[ParameterDefinition] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    cache_policy: Literal["none", "content-addressed"] = "content-addressed"
    side_effects: bool = False
    supports_preview: bool = False
    supports_cancel: bool = True
    supports_pause: bool = False
    available: bool = True
    unavailable_reason: str = ""
    adapter: str | None = None


class Position(ContractModel):
    x: float = 0
    y: float = 0


class WorkflowNode(ContractModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    schema_id: str
    schema_version: int = 1
    label: str = ""
    position: Position = Field(default_factory=Position)
    parameters: dict[str, Any] = Field(default_factory=dict)
    disabled: bool = False
    bypass: bool = False
    collapsed: bool = False


class WorkflowEdge(ContractModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_node_id: str
    source_port_id: str
    target_node_id: str
    target_port_id: str


class WorkflowGroup(ContractModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    label: str = "Group"
    node_ids: list[str] = Field(default_factory=list)
    position: Position = Field(default_factory=Position)
    width: float = 360
    height: float = 240
    color: str = "accent"


class WorkflowDocument(ContractModel):
    format: Literal["midgard-workflow"] = "midgard-workflow"
    version: int = 1
    project_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = "Untitled workflow"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    groups: list[WorkflowGroup] = Field(default_factory=list)
    project_settings: dict[str, Any] = Field(default_factory=dict)
    viewport: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(ContractModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None
    action: str | None = None


class ValidationResult(ContractModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class ExecutionStep(ContractModel):
    index: int
    node_id: str
    schema_id: str
    dependencies: list[str] = Field(default_factory=list)
    cache_key: str | None = None


class ExecutionPlan(ContractModel):
    workflow_id: str
    steps: list[ExecutionStep]
    validation: ValidationResult
