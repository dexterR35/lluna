#!/usr/bin/env python3
"""Export deterministic API and graph contracts consumed by documentation/tools."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.api.app import create_app
from backend.graph.registry import list_nodes
from backend.graph.schema import WorkflowDocument
target=ROOT/"docs"/"contracts";target.mkdir(parents=True,exist_ok=True)
def write(name,value):(target/name).write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")
write("openapi.json",create_app("contract-export-token-with-at-least-thirty-two-characters").openapi())
write("nodes.json",[item.model_dump(mode="json",by_alias=True) for item in list_nodes()])
write("workflow.schema.json",WorkflowDocument.model_json_schema(by_alias=True))
print(f"Exported contracts to {target}")
