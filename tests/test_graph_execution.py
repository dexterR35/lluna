from __future__ import annotations
import time
from PIL import Image
from backend.artifacts.store import ArtifactStore,DesktopGrantStore
from backend.graph.executor import RunManager
from backend.graph.schema import WorkflowDocument,WorkflowEdge,WorkflowNode

def test_fake_worker_vertical_slice_commits_artifact(monkeypatch,tmp_path):
    monkeypatch.setenv("MIDGARD_FAKE_WORKER","1")
    source_path=tmp_path/"input.png";Image.new("RGBA",(4,3),(10,20,30,255)).save(source_path)
    ArtifactStore._instance=ArtifactStore(tmp_path/"artifacts")
    DesktopGrantStore._instance=None;grants=DesktopGrantStore.instance();grant=grants.issue(source_path)
    RunManager._instance=None;manager=RunManager.instance()
    source=WorkflowNode(id="load",schema_id="midgard.input.image",parameters={"pathGrantId":grant.grant_id})
    enhance=WorkflowNode(id="enhance",schema_id="midgard.image.upscale",parameters={"model":"test"})
    preview=WorkflowNode(id="preview",schema_id="midgard.output.preview_image")
    workflow=WorkflowDocument(nodes=[source,enhance,preview],edges=[WorkflowEdge(source_node_id="load",source_port_id="image",target_node_id="enhance",target_port_id="image"),WorkflowEdge(source_node_id="enhance",source_port_id="image",target_node_id="preview",target_port_id="image")])
    run=manager.start(workflow)
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        snapshot=manager.get(run.run_id)
        if snapshot.status in {"COMPLETED","FAILED","CANCELLED"}:break
        time.sleep(.02)
    assert snapshot.status=="COMPLETED",snapshot.error
    assert snapshot.nodes["enhance"].status in {"SUCCEEDED","CACHED"}
    assert snapshot.artifact_ids
    artifact=ArtifactStore.instance().get(snapshot.artifact_ids[-1])
    assert artifact.width==4 and artifact.height==3
