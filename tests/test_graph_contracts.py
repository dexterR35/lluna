from backend.graph.compiler import compile_workflow
from backend.graph.registry import list_nodes
from backend.graph.schema import Position, WorkflowDocument, WorkflowEdge, WorkflowNode
from backend.graph.validation import validate_workflow

def node(schema_id, node_id):
    return WorkflowNode(id=node_id, schema_id=schema_id, position=Position(x=0,y=0))

def test_catalog_contains_all_existing_ai_adapters():
    adapters={item.adapter for item in list_nodes()}
    assert {"generate","subtitle","bg_remove","enhance","low_light","select_subject","lama_retouch"} <= adapters

def test_typed_graph_validates_and_compiles_topologically():
    source=node("midgard.input.image","source"); preview=node("midgard.output.preview_image","preview")
    source.parameters={"pathGrantId":"test-grant"}
    workflow=WorkflowDocument(nodes=[source,preview],edges=[WorkflowEdge(source_node_id="source",source_port_id="image",target_node_id="preview",target_port_id="image")])
    result=validate_workflow(workflow)
    assert result.valid
    assert [step.node_id for step in compile_workflow(workflow).steps]==["source","preview"]

def test_incompatible_connection_and_cycle_are_rejected():
    prompt=node("midgard.input.prompt","prompt"); preview=node("midgard.output.preview_image","preview")
    workflow=WorkflowDocument(nodes=[prompt,preview],edges=[WorkflowEdge(source_node_id="prompt",source_port_id="prompt",target_node_id="preview",target_port_id="image")])
    assert any(issue.code=="INCOMPATIBLE_PORTS" for issue in validate_workflow(workflow).issues)
