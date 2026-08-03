from fastapi.testclient import TestClient
from backend.api.app import create_app

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
