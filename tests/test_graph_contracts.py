from backend.graph.compiler import compile_workflow
from backend.graph.registry import list_nodes
from backend.graph.schema import Position, WorkflowDocument, WorkflowEdge, WorkflowNode
from backend.graph.validation import validate_workflow
from backend.models.service import known_model_ids

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

def test_image_queue_and_composite_nodes_publish_batch_contracts():
    catalog={item.schema_id:item for item in list_nodes()}
    source=catalog["midgard.input.images"]
    remove=catalog["midgard.image.remove_background"]
    composite=catalog["midgard.image.composite"]
    assert source.outputs[0].multiple
    assert next(port for port in remove.inputs if port.id=="image").multiple
    assert all(port.multiple for port in composite.inputs)
    assert composite.adapter=="composite"

def test_every_node_model_option_has_a_lifecycle_inventory_entry():
    lifecycle_ids=known_model_ids()
    option_ids={
        option["modelId"]
        for definition in list_nodes()
        for parameter in definition.parameters
        if parameter.type=="model"
        for option in parameter.options
    }
    assert option_ids <= lifecycle_ids

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

def test_known_batch_cannot_flow_into_a_scalar_only_output():
    source=node("midgard.input.images","source")
    source.parameters={"pathGrantIds":["one","two"]}
    enhance=node("midgard.image.upscale","enhance")
    save=node("midgard.output.save_image","save")
    workflow=WorkflowDocument(
        nodes=[source,enhance,save],
        edges=[
            WorkflowEdge(source_node_id="source",source_port_id="images",target_node_id="enhance",target_port_id="image"),
            WorkflowEdge(source_node_id="enhance",source_port_id="image",target_node_id="save",target_port_id="image"),
        ],
    )
    result=validate_workflow(workflow)
    assert not result.valid
    assert any(issue.code=="BATCH_TO_SCALAR" for issue in result.issues)

def test_repeated_processor_is_rejected_only_inside_the_planned_path():
    source=node("midgard.input.image","source"); source.parameters={"pathGrantId":"grant"}
    first_remove=node("midgard.image.remove_background","first-remove")
    enhance=node("midgard.image.upscale","enhance")
    second_remove=node("midgard.image.remove_background","second-remove")
    preview=node("midgard.output.preview_image","preview")
    workflow=WorkflowDocument(
        nodes=[source,first_remove,enhance,second_remove,preview],
        edges=[
            WorkflowEdge(source_node_id="source",source_port_id="image",target_node_id="first-remove",target_port_id="image"),
            WorkflowEdge(source_node_id="first-remove",source_port_id="image",target_node_id="enhance",target_port_id="image"),
            WorkflowEdge(source_node_id="enhance",source_port_id="image",target_node_id="second-remove",target_port_id="image"),
            WorkflowEdge(source_node_id="second-remove",source_port_id="image",target_node_id="preview",target_port_id="image"),
        ],
    )
    full=validate_workflow(workflow)
    assert not full.valid
    assert any(issue.code=="REPEATED_OPERATION" and issue.node_id=="second-remove" for issue in full.issues)
    enhance.result={"status":"SUCCEEDED","artifactIds":["enhanced-image"]}
    selected=validate_workflow(workflow,mode="selected",selected_node_ids=["second-remove"])
    assert not any(issue.code=="REPEATED_OPERATION" for issue in selected.issues)

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

def test_run_modes_reuse_upstream_outputs_without_scheduling_upstream_nodes():
    source=node("midgard.input.image","source"); remove=node("midgard.image.remove_background","remove")
    enhance=node("midgard.image.upscale","enhance"); preview=node("midgard.output.preview_image","preview")
    source.parameters={"pathGrantId":"test-grant"}
    remove.result={"status":"SUCCEEDED","artifactIds":["remove-artifact"]}
    workflow=WorkflowDocument(
        nodes=[source,remove,enhance,preview],
        edges=[
            WorkflowEdge(source_node_id="source",source_port_id="image",target_node_id="remove",target_port_id="image"),
            WorkflowEdge(source_node_id="remove",source_port_id="image",target_node_id="enhance",target_port_id="image"),
            WorkflowEdge(source_node_id="enhance",source_port_id="image",target_node_id="preview",target_port_id="image"),
        ],
    )
    steps=compile_workflow(workflow, mode="from", selected_node_ids=["enhance"]).steps
    assert [step.node_id for step in steps]==["enhance","preview"]
    selected_only=compile_workflow(workflow, mode="selected", selected_node_ids=["enhance"]).steps
    assert [step.node_id for step in selected_only]==["enhance"]

def test_run_from_here_requires_stored_side_inputs_without_scheduling_them():
    source=node("midgard.input.image","source"); source.parameters={"pathGrantId":"image-grant"}
    mask=node("midgard.input.mask","mask"); mask.parameters={"pathGrantId":"mask-grant"}
    source.result={"status":"SUCCEEDED","artifactIds":["source-artifact"]}
    mask.result={"status":"SUCCEEDED","artifactIds":["mask-artifact"]}
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
    assert ordered==["enhance","retouch","preview"]

def test_scoped_validation_ignores_unrelated_invalid_nodes_and_edges():
    selected=node("midgard.input.prompt","selected"); selected.parameters={"value":"A castle"}
    unrelated=node("unknown.node.type","unrelated")
    workflow=WorkflowDocument(
        nodes=[selected,unrelated],
        edges=[WorkflowEdge(source_node_id="unrelated",source_port_id="missing",target_node_id="missing-node",target_port_id="missing")],
    )
    full=validate_workflow(workflow)
    scoped=validate_workflow(workflow,mode="selected",selected_node_ids=["selected"])
    assert not full.valid
    assert scoped.valid
    assert compile_workflow(workflow,mode="selected",selected_node_ids=["selected"]).steps[0].node_id=="selected"

def test_document_validation_keeps_unrelated_errors_for_the_problems_panel():
    source=node("midgard.input.image","source"); source.parameters={"pathGrantId":"grant"}
    preview=node("midgard.output.preview_image","preview")
    unrelated=node("unknown.node.type","unrelated")
    workflow=WorkflowDocument(
        nodes=[source,preview,unrelated],
        edges=[WorkflowEdge(source_node_id="source",source_port_id="image",target_node_id="preview",target_port_id="image")],
    )
    run_validation=validate_workflow(workflow)
    document_validation=validate_workflow(workflow,include_unrelated=True)
    assert run_validation.valid
    assert not document_validation.valid
    assert any(issue.node_id=="unrelated" and issue.code=="UNKNOWN_NODE" for issue in document_validation.issues)

def test_scoped_run_requires_a_real_selection():
    prompt=node("midgard.input.prompt","prompt")
    workflow=WorkflowDocument(nodes=[prompt])
    result=validate_workflow(workflow,mode="selected",selected_node_ids=[])
    assert not result.valid
    assert any(issue.code=="NO_SELECTION" for issue in result.issues)

def test_scoped_validation_reports_missing_required_boundary_output():
    source=node("midgard.input.image","source")
    enhance=node("midgard.image.upscale","enhance")
    workflow=WorkflowDocument(
        nodes=[source,enhance],
        edges=[WorkflowEdge(source_node_id="source",source_port_id="image",target_node_id="enhance",target_port_id="image")],
    )
    result=validate_workflow(workflow,mode="selected",selected_node_ids=["enhance"])
    assert not result.valid
    assert any(issue.code=="BOUNDARY_INPUT_UNAVAILABLE" for issue in result.issues)
    assert any(issue.message=="Required input has no completed output." for issue in result.issues)
