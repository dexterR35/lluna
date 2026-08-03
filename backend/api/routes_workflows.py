"""Workflow validation and compilation routes."""

from fastapi import APIRouter, Depends

from backend.api.auth import require_token
from backend.graph.compiler import compile_workflow
from backend.graph.schema import WorkflowDocument
from backend.graph.validation import validate_workflow

router = APIRouter(prefix="/api/workflows", dependencies=[Depends(require_token)])


@router.post("/validate")
def validate(workflow: WorkflowDocument) -> dict:
    return validate_workflow(workflow).model_dump(mode="json", by_alias=True)


@router.post("/compile")
def compile(workflow: WorkflowDocument) -> dict:
    return compile_workflow(workflow).model_dump(mode="json", by_alias=True)
