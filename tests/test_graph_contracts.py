from backend.graph.compiler import compile_workflow
from backend.graph.registry import list_nodes
from backend.graph.schema import Position, WorkflowDocument, WorkflowEdge, WorkflowNode
from backend.graph.validation import validate_workflow

def node(schema_id, node_id):
    return WorkflowNode(id=node_id, schema_id=schema_id, position=Position(x=0,y=0))

def test_catalog_contains_all_existing_ai_adapters():
    adapters={item.adapter for item in list_nodes()}
    assert {"generate","subtitle","bg_remove","enhance","low_light","select_subject","lama_retouch"} <= adapters
    assert not {"midgard.utility.metadata","midgard.utility.note"} & {item.schema_id for item in list_nodes()}

def test_processing_nodes_publish_explicit_model_choices_and_defaults():
    catalog={item.schema_id:item for item in list_nodes()}
    expected={
        "midgard.image.remove_background":"birefnet-general",
        "midgard.image.upscale":"RealESRGAN_x2plus",
        "midgard.generate.image":"FLUX.2-klein-base-4B",
    }
    for schema_id,default in expected.items():
        model=next(parameter for parameter in catalog[schema_id].parameters if parameter.id=="model")
        assert model.default==default
        assert {option["value"] for option in model.options}
        assert all(option.get("modelId") for option in model.options)

def test_legacy_bypass_is_discarded_from_nodes():
    parsed=WorkflowNode.model_validate({"schemaId":"midgard.input.prompt","bypass":True})
    assert "bypass" not in parsed.model_dump(mode="json",by_alias=True)

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

def test_orphan_nodes_do_not_block_output_chain():
    source=node("midgard.input.image","source"); enhance=node("midgard.image.upscale","enhance"); preview=node("midgard.output.preview_image","preview")
    orphan_generate=node("midgard.generate.image","orphan-generate"); orphan_retouch=node("midgard.image.lama_retouch","orphan-retouch")
    source.parameters={"pathGrantId":"test-grant"}
    workflow=WorkflowDocument(
        nodes=[source,enhance,preview,orphan_generate,orphan_retouch],
        edges=[
            WorkflowEdge(source_node_id="source",source_port_id="image",target_node_id="enhance",target_port_id="image"),
            WorkflowEdge(source_node_id="enhance",source_port_id="image",target_node_id="preview",target_port_id="image"),
        ],
    )
    result=validate_workflow(workflow)
    assert result.valid
    assert {issue.code for issue in result.issues if issue.severity=="warning"}=={"UNUSED_NODE"}
    assert [step.node_id for step in compile_workflow(workflow).steps]==["source","enhance","preview"]

def test_run_from_here_includes_upstream_then_downstream():
    source=node("midgard.input.image","source"); remove=node("midgard.image.remove_background","remove")
    enhance=node("midgard.image.upscale","enhance"); preview=node("midgard.output.preview_image","preview")
    source.parameters={"pathGrantId":"test-grant"}
    workflow=WorkflowDocument(
        nodes=[source,remove,enhance,preview],
        edges=[
            WorkflowEdge(source_node_id="source",source_port_id="image",target_node_id="remove",target_port_id="image"),
            WorkflowEdge(source_node_id="remove",source_port_id="image",target_node_id="enhance",target_port_id="image"),
            WorkflowEdge(source_node_id="enhance",source_port_id="image",target_node_id="preview",target_port_id="image"),
        ],
    )
    steps=compile_workflow(workflow, mode="from", selected_node_ids=["enhance"]).steps
    assert [step.node_id for step in steps]==["source","remove","enhance","preview"]
    selected_only=compile_workflow(workflow, mode="selected", selected_node_ids=["enhance"]).steps
    assert [step.node_id for step in selected_only]==["source","remove","enhance"]

def test_run_from_here_includes_side_inputs_required_by_downstream_merges():
    source=node("midgard.input.image","source"); source.parameters={"pathGrantId":"image-grant"}
    mask=node("midgard.input.mask","mask"); mask.parameters={"pathGrantId":"mask-grant"}
    enhance=node("midgard.image.upscale","enhance")
    retouch=node("midgard.image.lama_retouch","retouch")
    preview=node("midgard.output.preview_image","preview")
    workflow=WorkflowDocument(
        nodes=[source,mask,enhance,retouch,preview],
        edges=[
            WorkflowEdge(source_node_id="source",source_port_id="image",target_node_id="enhance",target_port_id="image"),
            WorkflowEdge(source_node_id="enhance",source_port_id="image",target_node_id="retouch",target_port_id="image"),
            WorkflowEdge(source_node_id="mask",source_port_id="mask",target_node_id="retouch",target_port_id="mask"),
            WorkflowEdge(source_node_id="retouch",source_port_id="image",target_node_id="preview",target_port_id="image"),
        ],
    )
    ordered=[step.node_id for step in compile_workflow(workflow,mode="from",selected_node_ids=["enhance"]).steps]
    assert set(ordered)=={"source","mask","enhance","retouch","preview"}
    assert ordered.index("mask") < ordered.index("retouch")
