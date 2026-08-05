import asyncio
import time

import httpx
from PIL import Image

from backend.api.app import create_app
from backend.api.routes_artifacts import (
    GrantRequest,
    SaveArtifactRequest,
    issue_grant,
    save_artifact,
)
from backend.artifacts.store import ArtifactStore, DesktopGrantStore
from backend.graph.executor import RunManager
from backend.graph.schema import WorkflowDocument, WorkflowNode


def test_health_ready_and_authenticated_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("LLUNA_TESTING", "1")
    monkeypatch.setenv("LLUNA_DISABLE_MODEL_DOWNLOADS", "1")
    token = "test-session-token-that-is-at-least-thirty-two-characters"  # noqa: S105
    app = create_app(token)

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                assert (await client.get("/health")).json() == {"status": "healthy"}
                assert (await client.get("/ready")).json() == {"ready": True}
                assert (await client.get("/api/nodes")).status_code == 401
                response = await client.get("/api/nodes", headers={"X-Lluna-Token": token})
                assert response.status_code == 200
                assert any(item["schemaId"] == "lluna.generate.image" for item in response.json())

    asyncio.run(scenario())


def test_completed_artifact_can_be_saved_through_a_write_grant(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(b"completed-image")
    destination = tmp_path / "saved.png"
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    artifact = ArtifactStore.instance().register_source(source, media_type="image/png")
    grant = DesktopGrantStore.instance().issue(destination, mode="write")
    result = save_artifact(
        artifact.artifact_id, SaveArtifactRequest(destinationGrantId=grant.grant_id)
    )
    assert result["name"] == "saved.png"
    assert destination.read_bytes() == b"completed-image"


def test_read_grant_registers_an_immediately_previewable_artifact(tmp_path):
    source = tmp_path / "selected.png"
    Image.new("RGBA", (12, 7), (20, 40, 60, 128)).save(source)
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    result = issue_grant(GrantRequest(path=str(source), mode="read"))
    assert result["name"] == "selected.png"
    assert result["mediaType"] == "image/png"
    assert result["width"] == 12 and result["height"] == 7
    assert result["alpha"] is True
    assert ArtifactStore.instance().get(result["artifactId"]).path == str(source)


def test_queue_and_history_api_expose_frozen_workflow_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("LLUNA_TESTING", "1")
    monkeypatch.setenv("LLUNA_DISABLE_MODEL_DOWNLOADS", "1")
    token = "queue-session-token-that-is-at-least-thirty-two-characters"  # noqa: S105
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    RunManager._instance = None
    workflow = WorkflowDocument(
        project_id="queue-api",
        nodes=[
            WorkflowNode(
                id="prompt",
                schema_id="lluna.input.prompt",
                parameters={"value": "hello"},
            )
        ],
    )
    headers = {"X-Lluna-Token": token}

    app = create_app(token)

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/runs",
                    headers=headers,
                    json={"workflow": workflow.model_dump(mode="json", by_alias=True)},
                )
                assert response.status_code == 200, response.text
                started = response.json()
                assert len(started["workflowHash"]) == 64

                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    current = (await client.get(f"/api/runs/{started['runId']}", headers=headers)).json()
                    if current["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                        break
                    await asyncio.sleep(0.02)
                assert current["status"] == "COMPLETED"

                queue = await client.get("/api/queue", headers=headers)
                assert queue.status_code == 200
                assert queue.json()["pending"] == []
                history = await client.get("/api/history?limit=10", headers=headers)
                assert history.status_code == 200
                assert history.json()["runs"][0]["workflowHash"] == started["workflowHash"]

    asyncio.run(scenario())
