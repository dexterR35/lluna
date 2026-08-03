"""Node catalog routes."""

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import require_token
from backend.graph.registry import NODE_REGISTRY, list_nodes

router = APIRouter(prefix="/api/nodes", dependencies=[Depends(require_token)])


@router.get("")
def nodes() -> list[dict]:
    return [item.model_dump(mode="json", by_alias=True) for item in list_nodes()]


@router.get("/{schema_id}")
def node(schema_id: str) -> dict:
    definition = NODE_REGISTRY.get(schema_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Unknown node schema")
    return definition.model_dump(mode="json", by_alias=True)
