from __future__ import annotations

import json
import zipfile

import pytest

from backend.editor.graph import OperationGraph, OperationNode
from backend.projects import (
    MidgardProject,
    load_project,
    project_asset_from_file,
    save_project,
)


def _graph() -> OperationGraph:
    return OperationGraph(
        (
            OperationNode(
                id="op_source",
                type="source.image",
                inputs={"asset": "asset_source:image"},
            ),
        )
    )


def test_project_round_trip_with_verified_embedded_source(tmp_path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"immutable source bytes")
    asset = project_asset_from_file("asset_source", source, embed=True)
    project = MidgardProject.new(_graph(), assets=(asset,))
    target = tmp_path / "example.midgard"

    save_project(project, target, embedded_sources={asset.id: source})
    restored = load_project(target)

    assert restored.project_id == project.project_id
    assert restored.graph == project.graph
    assert restored.assets == project.assets


def test_save_rejects_changed_source_and_preserves_existing_target(tmp_path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"first")
    asset = project_asset_from_file("asset_source", source, embed=True)
    project = MidgardProject.new(_graph(), assets=(asset,))
    target = tmp_path / "example.midgard"
    target.write_bytes(b"previous project remains")
    source.write_bytes(b"changed after import")

    with pytest.raises(ValueError, match="source changed"):
        save_project(project, target, embedded_sources={asset.id: source})

    assert target.read_bytes() == b"previous project remains"


def test_project_rejects_path_traversal_member(tmp_path) -> None:
    path = tmp_path / "unsafe.midgard"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape", b"no")
        archive.writestr("manifest.json", b"{}")

    with pytest.raises(ValueError, match="unsafe project member"):
        load_project(path)


def test_project_rejects_graph_tampering(tmp_path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    asset = project_asset_from_file("asset_source", source, embed=True)
    project = MidgardProject.new(_graph(), assets=(asset,))
    original = tmp_path / "original.midgard"
    tampered = tmp_path / "tampered.midgard"
    save_project(project, original, embedded_sources={asset.id: source})

    with zipfile.ZipFile(original, "r") as reader, zipfile.ZipFile(tampered, "w") as writer:
        for info in reader.infolist():
            data = reader.read(info)
            if info.filename == "document/graph.json":
                graph = json.loads(data)
                graph["nodes"][0]["enabled"] = False
                data = json.dumps(graph).encode()
            writer.writestr(info.filename, data)

    with pytest.raises(ValueError, match="fingerprint"):
        load_project(tampered)


def test_unknown_manifest_and_asset_fields_round_trip(tmp_path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    asset = project_asset_from_file("asset_source", source, embed=True)
    asset = type(asset)(**{**asset.__dict__, "extensions": {"future_asset": 7}})
    project = MidgardProject.new(_graph(), assets=(asset,))
    project = type(project)(
        **{**project.__dict__, "extensions": {"future_project": {"enabled": True}}}
    )
    target = tmp_path / "future.midgard"

    save_project(project, target, embedded_sources={asset.id: source})
    restored = load_project(target)

    assert restored.extensions["future_project"] == {"enabled": True}
    assert restored.assets[0].extensions["future_asset"] == 7
