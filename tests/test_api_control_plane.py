from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.api.routes_artifacts import GrantRequest,SaveArtifactRequest,issue_grant,save_artifact
from backend.artifacts.store import ArtifactStore,DesktopGrantStore
from PIL import Image

def test_health_ready_and_authenticated_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("MIDGARD_TESTING","1");monkeypatch.setenv("MIDGARD_DISABLE_MODEL_DOWNLOADS","1")
    token="test-session-token-that-is-at-least-thirty-two-characters"
    with TestClient(create_app(token)) as client:
        assert client.get("/health").json()=={"status":"healthy"}
        assert client.get("/ready").json()=={"ready":True}
        assert client.get("/api/nodes").status_code==401
        response=client.get("/api/nodes",headers={"X-Midgard-Token":token})
        assert response.status_code==200
        assert any(item["schemaId"]=="midgard.generate.image" for item in response.json())

def test_completed_artifact_can_be_saved_through_a_write_grant(tmp_path):
    source=tmp_path/"source.png";source.write_bytes(b"completed-image")
    destination=tmp_path/"saved.png"
    ArtifactStore._instance=ArtifactStore(tmp_path/"artifacts")
    DesktopGrantStore._instance=None
    artifact=ArtifactStore.instance().register_source(source,media_type="image/png")
    grant=DesktopGrantStore.instance().issue(destination,mode="write")
    result=save_artifact(artifact.artifact_id,SaveArtifactRequest(destinationGrantId=grant.grant_id))
    assert result["name"]=="saved.png"
    assert destination.read_bytes()==b"completed-image"

def test_read_grant_registers_an_immediately_previewable_artifact(tmp_path):
    source=tmp_path/"selected.png";Image.new("RGBA",(12,7),(20,40,60,128)).save(source)
    ArtifactStore._instance=ArtifactStore(tmp_path/"artifacts")
    DesktopGrantStore._instance=None
    result=issue_grant(GrantRequest(path=str(source),mode="read"))
    assert result["name"]=="selected.png"
    assert result["mediaType"]=="image/png"
    assert result["width"]==12 and result["height"]==7
    assert result["alpha"] is True
    assert ArtifactStore.instance().get(result["artifactId"]).path==str(source)
