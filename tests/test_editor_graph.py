from __future__ import annotations

import pytest

from backend.editor.graph import OperationGraph, OperationNode


def _source() -> OperationNode:
    return OperationNode(
        id="op_source",
        type="source.image",
        inputs={"asset": "asset_source:image"},
        parameters={"orientation": 1},
    )


def _refine() -> OperationNode:
    return OperationNode(
        id="op_refine",
        type="alpha.refine",
        inputs={"image": "op_source:image", "mask": "mask_subject:mask"},
        parameters={"feather_radius_px": 0.5},
    )


def test_graph_round_trip_and_fingerprint_are_deterministic() -> None:
    graph = OperationGraph((_source(), _refine()), extensions={"future": {"x": 1}})

    restored = OperationGraph.from_dict(graph.to_dict())

    assert restored == graph
    assert restored.fingerprint() == graph.fingerprint()


def test_unknown_node_fields_are_preserved() -> None:
    raw = _refine().to_dict()
    raw["future_provider_hint"] = {"quality": "high"}

    restored = OperationNode.from_dict(raw)

    assert restored.to_dict()["future_provider_hint"] == {"quality": "high"}


def test_graph_rejects_unknown_dependencies_and_cycles() -> None:
    with pytest.raises(ValueError, match="unknown source"):
        OperationGraph(
            (
                OperationNode(
                    id="op_bad",
                    type="alpha.refine",
                    inputs={"image": "missing:image"},
                ),
            )
        )

    first = OperationNode(
        id="op_first",
        type="test.first",
        inputs={"image": "op_second:image"},
    )
    second = OperationNode(
        id="op_second",
        type="test.second",
        inputs={"image": "op_first:image"},
    )
    with pytest.raises(ValueError, match="cycle"):
        OperationGraph((first, second))


def test_referenced_node_cannot_be_removed() -> None:
    graph = OperationGraph((_source(), _refine()))

    with pytest.raises(ValueError, match="used by op_refine"):
        graph.remove("op_source")


def test_graph_operations_return_new_instances() -> None:
    original = OperationGraph((_source(),))
    added = original.add(_refine())
    disabled = added.replace(
        OperationNode(
            id="op_refine",
            type="alpha.refine",
            enabled=False,
            inputs={"image": "op_source:image", "mask": "mask_subject:mask"},
        )
    )

    assert len(original.nodes) == 1
    assert len(added.nodes) == 2
    assert disabled.nodes[1].enabled is False
