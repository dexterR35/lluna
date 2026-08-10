"""Workflow validation, compilation, template and migration routes."""

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import require_token
from backend.graph.compiler import compile_workflow
from backend.graph.migrations import MigrationError, migrate_workflow, needs_migration
from backend.graph.schema import WorkflowDocument
from backend.graph.templates import all_templates, get_template
from backend.graph.validation import validate_workflow

router = APIRouter(prefix="/api/workflows", dependencies=[Depends(require_token)])


@router.post("/validate")
def validate(workflow: WorkflowDocument) -> dict:
    return validate_workflow(
        workflow, include_unrelated=True, check_model_availability=True
    ).model_dump(mode="json", by_alias=True)


@router.post("/compile")
def compile(workflow: WorkflowDocument) -> dict:
    return compile_workflow(workflow, check_model_availability=True).model_dump(
        mode="json", by_alias=True
    )


@router.get("/templates")
def templates() -> dict:
    """Ready-made workflows to drop on the canvas."""
    return {"templates": [template.to_dict() for template in all_templates()]}


@router.get("/templates/{template_id}")
def template(template_id: str) -> dict:
    try:
        return get_template(template_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown template.") from exc


@router.post("/migrate")
def migrate(workflow: dict) -> dict:
    """Bring a saved workflow forward to the node versions this build expects.

    Takes a raw document rather than a parsed one on purpose: the whole point is
    to handle shapes the current contract would reject.
    """
    try:
        document, applied = migrate_workflow(workflow)
    except MigrationError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "MIGRATION_FAILED", "message": str(exc)}
        ) from exc
    return {
        "workflow": document,
        "migrated": bool(applied),
        "steps": applied,
        "needsMigration": needs_migration(workflow),
    }
