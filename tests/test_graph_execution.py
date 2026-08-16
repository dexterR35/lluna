from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from PIL import Image

from backend.artifacts.store import ArtifactStore, DesktopGrantStore
from backend.configuration.service import update_settings
from backend.graph.executor import RunManager
from backend.graph.schema import WorkflowDocument, WorkflowEdge, WorkflowNode
from backend.tools.inference.protocol import JobType


def wait_for_run(manager, run_id, timeout=3):
    deadline = time.monotonic() + timeout
    snapshot = manager.get(run_id)
    while time.monotonic() < deadline:
        snapshot = manager.get(run_id)
        if snapshot.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return snapshot
        time.sleep(0.02)
    return snapshot


def test_fake_worker_vertical_slice_commits_artifact(monkeypatch, tmp_path):
    monkeypatch.setenv("LLUNA_FAKE_WORKER", "1")
    source_path = tmp_path / "input.png"
    Image.new("RGBA", (4, 3), (10, 20, 30, 255)).save(source_path)
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    grants = DesktopGrantStore.instance()
    grant = grants.issue(source_path)
    RunManager._instance = None
    manager = RunManager.instance()
    source = WorkflowNode(
        id="load", schema_id="lluna.input.image", parameters={"pathGrantId": grant.grant_id}
    )
    enhance = WorkflowNode(
        id="enhance", schema_id="lluna.image.upscale", parameters={"model": "test"}
    )
    preview = WorkflowNode(id="preview", schema_id="lluna.output.preview_image")
    workflow = WorkflowDocument(
        nodes=[source, enhance, preview],
        edges=[
            WorkflowEdge(
                source_node_id="load",
                source_port_id="image",
                target_node_id="enhance",
                target_port_id="image",
            ),
            WorkflowEdge(
                source_node_id="enhance",
                source_port_id="image",
                target_node_id="preview",
                target_port_id="image",
            ),
        ],
    )
    run = manager.start(workflow)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = manager.get(run.run_id)
        if snapshot.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        time.sleep(0.02)
    assert snapshot.status == "COMPLETED", snapshot.error
    assert snapshot.nodes["enhance"].status in {"SUCCEEDED", "CACHED"}
    assert snapshot.artifact_ids
    artifact = ArtifactStore.instance().get(snapshot.artifact_ids[-1])
    assert artifact.width == 4 and artifact.height == 3
    cached_run = manager.start(workflow)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        cached_snapshot = manager.get(cached_run.run_id)
        if cached_snapshot.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        time.sleep(0.02)
    assert cached_snapshot.status == "COMPLETED", cached_snapshot.error
    assert cached_snapshot.nodes["enhance"].status == "CACHED"
    assert cached_snapshot.nodes["enhance"].artifact_ids


def test_select_object_passes_image_and_mask_to_lama_without_preview_node(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("LLUNA_FAKE_WORKER", "1")
    source_path = tmp_path / "subject.png"
    Image.new("RGB", (8, 6), (20, 40, 60)).save(source_path)
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    grant = DesktopGrantStore.instance().issue(source_path)
    RunManager._instance = None
    manager = RunManager.instance()
    source = WorkflowNode(
        id="load",
        schema_id="lluna.input.image",
        parameters={"pathGrantId": grant.grant_id},
    )
    select = WorkflowNode(
        id="select",
        schema_id="lluna.mask.select_object",
        parameters={"text": "person"},
    )
    retouch = WorkflowNode(id="retouch", schema_id="lluna.image.lama_retouch")
    workflow = WorkflowDocument(
        nodes=[source, select, retouch],
        edges=[
            WorkflowEdge(
                source_node_id="load",
                source_port_id="image",
                target_node_id="select",
                target_port_id="image",
            ),
            WorkflowEdge(
                source_node_id="select",
                source_port_id="source_image",
                target_node_id="retouch",
                target_port_id="image",
            ),
            WorkflowEdge(
                source_node_id="select",
                source_port_id="mask",
                target_node_id="retouch",
                target_port_id="mask",
            ),
        ],
    )

    snapshot = wait_for_run(manager, manager.start(workflow).run_id)
    assert snapshot.status == "COMPLETED", snapshot.error
    assert snapshot.nodes["select"].artifact_ids
    assert snapshot.nodes["retouch"].artifact_ids
    mask = ArtifactStore.instance().get(snapshot.nodes["select"].artifact_ids[-1])
    assert mask.creating_schema_id == "lluna.mask.select_object"
    assert mask.input_artifact_ids
    select.result = {
        "status": "SUCCEEDED",
        "artifactIds": snapshot.nodes["select"].artifact_ids,
    }
    boundary = manager._boundary_values(workflow, {"retouch"})
    assert boundary[("select", "mask")].artifact_id == mask.artifact_id
    assert (
        boundary[("select", "source_image")].artifact_id
        == mask.input_artifact_ids[0]
    )


def test_image_effects_commit_the_visible_edit_and_preserve_alpha(tmp_path):
    source_path = tmp_path / "input.png"
    Image.new("RGBA", (2, 1), (100, 60, 20, 123)).save(source_path)
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    grant = DesktopGrantStore.instance().issue(source_path)
    RunManager._instance = None
    manager = RunManager.instance()
    source = WorkflowNode(
        id="load",
        schema_id="lluna.input.image",
        parameters={"pathGrantId": grant.grant_id},
    )
    effects = WorkflowNode(
        id="effects",
        schema_id="lluna.image.effects",
        parameters={"preset": "mono", "brightness": 1.2},
    )
    preview = WorkflowNode(id="preview", schema_id="lluna.output.preview_image")
    workflow = WorkflowDocument(
        nodes=[source, effects, preview],
        edges=[
            WorkflowEdge(
                source_node_id="load",
                source_port_id="image",
                target_node_id="effects",
                target_port_id="image",
            ),
            WorkflowEdge(
                source_node_id="effects",
                source_port_id="image",
                target_node_id="preview",
                target_port_id="image",
            ),
        ],
    )

    snapshot = wait_for_run(manager, manager.start(workflow).run_id)
    assert snapshot.status == "COMPLETED", snapshot.error
    artifact = ArtifactStore.instance().get(snapshot.nodes["effects"].artifact_ids[-1])
    with Image.open(artifact.path) as result:
        red, green, blue, alpha = result.convert("RGBA").getpixel((0, 0))
    assert red == green == blue
    assert alpha == 123
    assert artifact.creating_schema_id == "lluna.image.effects"


def test_image_queue_saves_lineage_names_and_requires_explicit_replace(monkeypatch, tmp_path):
    monkeypatch.setenv("LLUNA_FAKE_WORKER", "1")
    first_path = tmp_path / "portrait.png"
    second_path = tmp_path / "product.jpg"
    Image.new("RGBA", (4, 3), (10, 20, 30, 255)).save(first_path)
    Image.new("RGB", (5, 4), (30, 20, 10)).save(second_path)
    destination = tmp_path / "exports"
    destination.mkdir()

    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    grants = DesktopGrantStore.instance()
    source_grants = [grants.issue(first_path), grants.issue(second_path)]
    destination_grant = grants.issue(destination, mode="directory")
    RunManager._instance = None
    manager = RunManager.instance()

    source = WorkflowNode(
        id="load",
        schema_id="lluna.input.images",
        parameters={"pathGrantIds": [item.grant_id for item in source_grants]},
    )
    low_light = WorkflowNode(
        id="low-light",
        schema_id="lluna.image.low_light",
        parameters={"model": "test"},
    )
    upscale = WorkflowNode(
        id="upscale",
        schema_id="lluna.image.upscale",
        parameters={"model": "test"},
    )
    save = WorkflowNode(
        id="save",
        schema_id="lluna.output.save_image",
        parameters={
            "destinationGrantId": destination_grant.grant_id,
            "conflictPolicy": "ask",
        },
    )
    workflow = WorkflowDocument(
        nodes=[source, low_light, upscale, save],
        edges=[
            WorkflowEdge(
                source_node_id="load",
                source_port_id="images",
                target_node_id="low-light",
                target_port_id="image",
            ),
            WorkflowEdge(
                source_node_id="low-light",
                source_port_id="image",
                target_node_id="upscale",
                target_port_id="image",
            ),
            WorkflowEdge(
                source_node_id="upscale",
                source_port_id="image",
                target_node_id="save",
                target_port_id="image",
            ),
        ],
    )

    first_run = wait_for_run(manager, manager.start(workflow).run_id)
    assert first_run.status == "COMPLETED", first_run.error
    expected = {"portrait_lowlight_upscale.png", "product_lowlight_upscale.png"}
    assert {item.name for item in destination.iterdir()} == expected
    assert len(first_run.nodes["save"].artifact_ids) == 2
    assert [item["status"] for item in first_run.nodes["save"].save_items] == [
        "FINISHED",
        "FINISHED",
    ]
    assert [item["progress"] for item in first_run.nodes["save"].save_items] == [100, 100]
    assert {item["name"] for item in first_run.nodes["save"].save_items} == expected

    conflict_run = wait_for_run(manager, manager.start(workflow).run_id)
    assert conflict_run.status == "FAILED"
    assert conflict_run.error and conflict_run.error["code"] == "OUTPUT_EXISTS"
    assert {item.name for item in destination.iterdir()} == expected

    save.parameters["conflictPolicy"] = "replace"
    replacement_run = wait_for_run(manager, manager.start(workflow, force=True).run_id)
    assert replacement_run.status == "COMPLETED", replacement_run.error
    assert {item.name for item in destination.iterdir()} == expected


def test_multiple_scalar_image_links_share_one_batch_save_input(monkeypatch, tmp_path):
    monkeypatch.setenv("LLUNA_FAKE_WORKER", "1")
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    Image.new("RGB", (3, 3), (10, 20, 30)).save(first_path)
    Image.new("RGB", (3, 3), (30, 20, 10)).save(second_path)
    destination = tmp_path / "joined"
    destination.mkdir()

    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts-multi-link")
    DesktopGrantStore._instance = None
    grants = DesktopGrantStore.instance()
    first_grant = grants.issue(first_path)
    second_grant = grants.issue(second_path)
    destination_grant = grants.issue(destination, mode="directory")
    RunManager._instance = None
    manager = RunManager.instance()

    first = WorkflowNode(
        id="first",
        schema_id="lluna.input.image",
        parameters={"pathGrantId": first_grant.grant_id},
    )
    second = WorkflowNode(
        id="second",
        schema_id="lluna.input.image",
        parameters={"pathGrantId": second_grant.grant_id},
    )
    save = WorkflowNode(
        id="save",
        schema_id="lluna.output.save_image",
        parameters={
            "destinationGrantId": destination_grant.grant_id,
            "conflictPolicy": "replace",
        },
    )
    workflow = WorkflowDocument(
        nodes=[first, second, save],
        edges=[
            WorkflowEdge(
                source_node_id="first",
                source_port_id="image",
                target_node_id="save",
                target_port_id="image",
            ),
            WorkflowEdge(
                source_node_id="second",
                source_port_id="image",
                target_node_id="save",
                target_port_id="image",
            ),
        ],
    )

    snapshot = wait_for_run(manager, manager.start(workflow).run_id)
    assert snapshot.status == "COMPLETED", snapshot.error
    assert {item.name for item in destination.iterdir()} == {"first.png", "second.png"}
    assert len(snapshot.nodes["save"].artifact_ids) == 2


def test_load_image_uses_saved_artifact_when_desktop_grant_has_expired(tmp_path):
    source_path = tmp_path / "persisted.png"
    Image.new("RGB", (5, 4), (10, 20, 30)).save(source_path)
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    artifact = ArtifactStore.instance().register_source(source_path)
    DesktopGrantStore._instance = None
    RunManager._instance = None
    manager = RunManager.instance()
    node = WorkflowNode(
        id="load",
        schema_id="lluna.input.image",
        parameters={"pathGrantId": "expired-grant"},
        result={"status": "READY", "artifactIds": [artifact.artifact_id]},
    )
    loaded = manager._load_granted_media(node)
    assert loaded.artifact_id == artifact.artifact_id


def test_supir_uses_settings_from_connected_llava_node(monkeypatch):
    manager = object.__new__(RunManager)
    captured = {}

    def capture(*args, **_kwargs):
        captured.update(args[3])
        return args[3]

    monkeypatch.setattr(manager, "_invoke_worker", capture)
    node = WorkflowNode(
        id="supir",
        schema_id="lluna.image.upscale",
        parameters={"model": "SUPIR", "useLlava": True},
    )
    llava = {
        "temperature": 0.6,
        "topP": 0.4,
        "question": "Describe materials and lighting.",
        "load8Bit": True,
    }

    manager._run_inference(None, node, {"llava": llava}, [], "cache-key")

    assert captured["use_llava"] is True
    assert captured["llava_temperature"] == 0.6
    assert captured["llava_top_p"] == 0.4
    assert captured["llava_question"] == "Describe materials and lighting."
    assert captured["load_8bit_llava"] is True


def test_subtitle_job_carries_disabled_hardware_acceleration(monkeypatch):
    update_settings({"runtime": {"hardware_acceleration": False}})
    manager = object.__new__(RunManager)
    captured = {}

    def capture(*args, **_kwargs):
        captured["job_type"] = args[2]
        captured["payload"] = args[3]
        return args[3]

    monkeypatch.setattr(manager, "_invoke_worker", capture)
    node = WorkflowNode(
        id="remove-subtitles",
        schema_id="lluna.video.remove_text",
        parameters={"subAreas": [[100, 200, 20, 300]]},
    )

    manager._run_inference(None, node, {}, [], "cache-key")

    assert captured["job_type"] is JobType.SUBTITLE
    assert captured["payload"]["hardware_acceleration"] is False


def test_video_retouch_forces_sttn_auto_regardless_of_subtitle_settings(monkeypatch):
    """Video Retouch must always be content-agnostic region fill, never
    subtitle/text detection - independent of whatever inpaint_mode the user
    has configured for actual subtitle removal (see pipelines/subtitle.py:
    only sttn_auto_mode skips OCR when areas are supplied)."""
    update_settings({"subtitle": {"inpaint_mode": "lama"}})
    manager = object.__new__(RunManager)
    captured = {}

    def capture(*args, **_kwargs):
        captured["job_type"] = args[2]
        captured["payload"] = args[3]
        return args[3]

    monkeypatch.setattr(manager, "_invoke_worker", capture)
    node = WorkflowNode(
        id="retouch",
        schema_id="lluna.video.retouch",
        parameters={"subAreas": [[100, 200, 20, 300]]},
    )

    manager._run_inference(None, node, {}, [], "cache-key")

    assert captured["job_type"] is JobType.SUBTITLE
    assert captured["payload"]["config"]["inpaint_mode"] == "sttn-auto"


def test_remove_text_uses_node_model_parameter(monkeypatch):
    update_settings({"subtitle": {"inpaint_mode": "sttn-auto"}})
    manager = object.__new__(RunManager)
    captured = {}

    def capture(*args, **_kwargs):
        captured["job_type"] = args[2]
        captured["payload"] = args[3]
        return args[3]

    monkeypatch.setattr(manager, "_invoke_worker", capture)
    node = WorkflowNode(
        id="remove-subtitles",
        schema_id="lluna.video.remove_text",
        parameters={"subAreas": [[100, 200, 20, 300]], "model": "propainter"},
    )

    manager._run_inference(None, node, {}, [], "cache-key")

    assert captured["job_type"] is JobType.SUBTITLE
    assert captured["payload"]["config"]["inpaint_mode"] == "propainter"


def test_remove_text_falls_back_to_global_inpaint_mode_when_model_unset(monkeypatch):
    update_settings({"subtitle": {"inpaint_mode": "lama"}})
    manager = object.__new__(RunManager)
    captured = {}

    def capture(*args, **_kwargs):
        captured["job_type"] = args[2]
        captured["payload"] = args[3]
        return args[3]

    monkeypatch.setattr(manager, "_invoke_worker", capture)
    node = WorkflowNode(
        id="remove-subtitles",
        schema_id="lluna.video.remove_text",
        parameters={"subAreas": [[100, 200, 20, 300]]},
    )

    manager._run_inference(None, node, {}, [], "cache-key")

    assert captured["job_type"] is JobType.SUBTITLE
    assert captured["payload"]["config"]["inpaint_mode"] == "lama"


def test_selected_run_reuses_boundary_artifact_without_running_upstream(monkeypatch, tmp_path):
    monkeypatch.setenv("LLUNA_FAKE_WORKER", "1")
    source_path = tmp_path / "boundary.png"
    Image.new("RGB", (6, 5), (30, 40, 50)).save(source_path)
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    artifact = ArtifactStore.instance().register_source(source_path)
    DesktopGrantStore._instance = None
    RunManager._instance = None
    manager = RunManager.instance()
    source = WorkflowNode(
        id="source",
        schema_id="lluna.input.image",
        result={"status": "SUCCEEDED", "artifactIds": [artifact.artifact_id]},
    )
    enhance = WorkflowNode(
        id="enhance", schema_id="lluna.image.upscale", parameters={"model": "test"}
    )
    workflow = WorkflowDocument(
        nodes=[source, enhance],
        edges=[
            WorkflowEdge(
                source_node_id="source",
                source_port_id="image",
                target_node_id="enhance",
                target_port_id="image",
            )
        ],
    )
    run = manager.start(workflow, mode="selected", selected_node_ids=["enhance"])
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = manager.get(run.run_id)
        if snapshot.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        time.sleep(0.02)
    assert snapshot.status == "COMPLETED", snapshot.error
    assert set(snapshot.nodes) == {"enhance"}
    assert snapshot.nodes["enhance"].status in {"SUCCEEDED", "CACHED"}


def test_boundary_output_keeps_single_artifacts_scalar_and_batches_ordered(tmp_path):
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    Image.new("RGB", (2, 2), (10, 20, 30)).save(first_path)
    Image.new("RGB", (3, 2), (30, 20, 10)).save(second_path)
    first = ArtifactStore.instance().register_source(first_path)
    second = ArtifactStore.instance().register_source(second_path)
    DesktopGrantStore._instance = None
    RunManager._instance = None
    manager = RunManager.instance()
    scalar = WorkflowNode(
        id="scalar",
        schema_id="lluna.image.upscale",
        result={"status": "SUCCEEDED", "artifactIds": [first.artifact_id]},
    )
    batch = WorkflowNode(
        id="batch",
        schema_id="lluna.image.upscale",
        result={
            "status": "SUCCEEDED",
            "artifactIds": [first.artifact_id, second.artifact_id],
        },
    )
    scalar_target = WorkflowNode(
        id="scalar-target",
        schema_id="lluna.output.preview_image",
    )
    batch_target = WorkflowNode(
        id="batch-target",
        schema_id="lluna.output.preview_image",
    )
    workflow = WorkflowDocument(
        nodes=[scalar, batch, scalar_target, batch_target],
        edges=[
            WorkflowEdge(
                source_node_id="scalar",
                source_port_id="image",
                target_node_id="scalar-target",
                target_port_id="image",
            ),
            WorkflowEdge(
                source_node_id="batch",
                source_port_id="image",
                target_node_id="batch-target",
                target_port_id="image",
            ),
        ],
    )

    values = manager._boundary_values(
        workflow,
        {"scalar-target", "batch-target"},
    )
    assert values[("scalar", "image")].artifact_id == first.artifact_id
    assert [item.artifact_id for item in values[("batch", "image")]] == [
        first.artifact_id,
        second.artifact_id,
    ]


def _wait_for_run(manager: RunManager, run_id: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = manager.get(run_id)
        if snapshot.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return snapshot
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for graph run")


def test_image_queue_maps_one_processor_over_ordered_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("LLUNA_FAKE_WORKER", "1")
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    grants = DesktopGrantStore.instance()
    grant_ids = []
    for index, width in enumerate((3, 5, 7)):
        source = tmp_path / f"source-{index}.png"
        Image.new("RGBA", (width, 4), (index * 20, 40, 80, 255)).save(source)
        grant_ids.append(grants.issue(source).grant_id)

    RunManager._instance = None
    manager = RunManager.instance()
    source = WorkflowNode(
        id="load-many",
        schema_id="lluna.input.images",
        parameters={"pathGrantIds": grant_ids},
    )
    remove = WorkflowNode(
        id="low-light",
        schema_id="lluna.image.low_light",
        parameters={"model": "test"},
    )
    preview = WorkflowNode(id="preview", schema_id="lluna.output.preview_image")
    workflow = WorkflowDocument(
        nodes=[source, remove, preview],
        edges=[
            WorkflowEdge(
                source_node_id="load-many",
                source_port_id="images",
                target_node_id="low-light",
                target_port_id="image",
            ),
            WorkflowEdge(
                source_node_id="low-light",
                source_port_id="image",
                target_node_id="preview",
                target_port_id="image",
            ),
        ],
    )

    run = _wait_for_run(manager, manager.start(workflow).run_id)
    assert run.status == "COMPLETED", run.error
    assert len(run.nodes["low-light"].artifact_ids) == 3
    outputs = [
        ArtifactStore.instance().get(artifact_id)
        for artifact_id in run.nodes["low-light"].artifact_ids
    ]
    assert [artifact.width for artifact in outputs] == [3, 5, 7]
    assert run.nodes["preview"].artifact_ids == run.nodes["low-light"].artifact_ids


def test_composite_broadcasts_one_background_across_foreground_queue(tmp_path):
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    grants = DesktopGrantStore.instance()
    foreground_ids = []
    for index in range(2):
        source = tmp_path / f"foreground-{index}.png"
        Image.new("RGBA", (4, 4), (255, 0, 0, 128 + index * 64)).save(source)
        foreground_ids.append(grants.issue(source).grant_id)
    background_path = tmp_path / "background.png"
    Image.new("RGB", (8, 4), (0, 0, 255)).save(background_path)
    background_grant = grants.issue(background_path)

    RunManager._instance = None
    manager = RunManager.instance()
    foregrounds = WorkflowNode(
        id="foregrounds",
        schema_id="lluna.input.images",
        parameters={"pathGrantIds": foreground_ids},
    )
    background = WorkflowNode(
        id="background",
        schema_id="lluna.input.image",
        parameters={"pathGrantId": background_grant.grant_id},
    )
    composite = WorkflowNode(
        id="composite",
        schema_id="lluna.image.composite",
        parameters={"fit": "cover"},
    )
    preview = WorkflowNode(id="preview", schema_id="lluna.output.preview_image")
    workflow = WorkflowDocument(
        nodes=[foregrounds, background, composite, preview],
        edges=[
            WorkflowEdge(
                source_node_id="foregrounds",
                source_port_id="images",
                target_node_id="composite",
                target_port_id="foreground",
            ),
            WorkflowEdge(
                source_node_id="background",
                source_port_id="image",
                target_node_id="composite",
                target_port_id="background",
            ),
            WorkflowEdge(
                source_node_id="composite",
                source_port_id="image",
                target_node_id="preview",
                target_port_id="image",
            ),
        ],
    )

    run = _wait_for_run(manager, manager.start(workflow).run_id)
    assert run.status == "COMPLETED", run.error
    assert len(run.nodes["composite"].artifact_ids) == 2
    first = ArtifactStore.instance().get(run.nodes["composite"].artifact_ids[0])
    with Image.open(first.path) as image:
        assert image.size == (4, 4)
        assert image.convert("RGB").getpixel((0, 0)) == (128, 0, 127)


def test_workflow_queue_runs_front_priority_before_fifo_items(monkeypatch, tmp_path):
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    RunManager._instance = None
    manager = RunManager.instance()
    started = threading.Event()
    release = threading.Event()
    order = []

    def execute(control):
        order.append(control.snapshot.run_id)
        control.snapshot.status = "RUNNING"
        if len(order) == 1:
            started.set()
            assert release.wait(timeout=2)
        control.snapshot.status = "COMPLETED"
        control.snapshot.progress = 100
        control.snapshot.completed_at = datetime.now(timezone.utc)

    monkeypatch.setattr(manager, "_execute", execute)
    workflow = WorkflowDocument(
        nodes=[
            WorkflowNode(
                id="prompt",
                schema_id="lluna.input.prompt",
                parameters={"value": "queued"},
            )
        ]
    )

    first = manager.start(workflow)
    assert started.wait(timeout=2)
    second = manager.start(workflow)
    next_run = manager.start(workflow, queue_front=True)

    queued = manager.queue_snapshot()["pending"]
    assert [item.run_id for item in queued] == [next_run.run_id, second.run_id]
    assert [item.queue_position for item in queued] == [1, 2]
    release.set()

    assert _wait_for_run(manager, next_run.run_id).status == "COMPLETED"
    assert _wait_for_run(manager, second.run_id).status == "COMPLETED"
    assert order == [first.run_id, next_run.run_id, second.run_id]
    manager.shutdown()


def test_cancelling_queued_run_does_not_execute_it(monkeypatch, tmp_path):
    ArtifactStore._instance = ArtifactStore(tmp_path / "artifacts")
    DesktopGrantStore._instance = None
    RunManager._instance = None
    manager = RunManager.instance()
    started = threading.Event()
    release = threading.Event()
    order = []

    def execute(control):
        order.append(control.snapshot.run_id)
        control.snapshot.status = "RUNNING"
        started.set()
        if len(order) == 1:
            assert release.wait(timeout=2)
        control.snapshot.status = "COMPLETED"
        control.snapshot.completed_at = datetime.now(timezone.utc)

    monkeypatch.setattr(manager, "_execute", execute)
    workflow = WorkflowDocument(
        nodes=[WorkflowNode(id="value", schema_id="lluna.input.number", parameters={"value": 1})]
    )
    first = manager.start(workflow)
    assert started.wait(timeout=2)
    cancelled = manager.start(workflow)
    snapshot = manager.cancel(cancelled.run_id)
    assert snapshot.status == "CANCELLED"
    assert snapshot.error and snapshot.error["code"] == "CANCELLED"
    release.set()
    assert _wait_for_run(manager, first.run_id).status == "COMPLETED"
    time.sleep(0.05)
    assert order == [first.run_id]
    assert cancelled.run_id in {item.run_id for item in manager.history()}
    manager.shutdown()
