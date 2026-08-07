"""Versioned backend-owned graph contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    capability: str = ""
    visible_for_models: list[str] = Field(default_factory=list)


class ParameterCondition(ContractModel):
    """One `node.parameters[parameter_id] == equals` check."""

    parameter_id: str
    equals: Any


class NodeCompanion(ContractModel):
    """Auto-attach/detach a companion node while `when` conditions hold.

    Declarative equivalent of "when this node's parameters look like X,
    make sure a connected companion node of schema Y exists" - e.g. the
    Upscale node's SUPIR model wants a LLaVA Caption node wired into its
    `llava` input whenever `useLlava` is on. Keeping this on the node
    definition (backend-owned, versioned with the rest of the contract)
    means the frontend editor can implement the behavior generically
    instead of special-casing specific schema/model ids.
    """

    schema_id: str
    target_port: str
    source_port: str = "config"
    when: list[ParameterCondition] = Field(default_factory=list)


class NodeDefinition(ContractModel):
    schema_version: int = 1
    schema_id: str
    version: int = 1
    name: str
    category: str
    description: str
    icon: str = "box"
    kind: Literal["input", "processor", "output"] = "processor"
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
    companions: list[NodeCompanion] = Field(default_factory=list)


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
    appearance: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    disabled: bool = False
    collapsed: bool = False

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_bypass(cls, value: Any) -> Any:
        if isinstance(value, dict) and "bypass" in value:
            value = {key: item for key, item in value.items() if key != "bypass"}
        return value


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
    start_node_ids: list[str] = Field(default_factory=list)
    position: Position = Field(default_factory=Position)
    width: float = 360
    height: float = 240
    color: str = "accent"
    kind: str = "flow"
    appearance: dict[str, Any] = Field(default_factory=dict)


class WorkflowDocument(ContractModel):
    format: Literal["lluna-workflow"] = "lluna-workflow"
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
