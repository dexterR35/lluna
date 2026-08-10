"""The ONNX runtime adapter, exercised against a real exported graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.models.adapters import ADAPTERS, AdapterError, OnnxAdapter
from backend.models.dynamic_registry import DynamicModelRecord
from backend.models.reference.manifest import (
    HardwareRequirement,
    ModelManifest,
    ModelSource,
    RuntimeRequirement,
)
from backend.models.reference.runtimes import RUNTIME_PROFILES

onnxruntime = pytest.importorskip("onnxruntime")
torch = pytest.importorskip("torch")
pytest.importorskip("onnx", reason="test-only: needed to export a graph, see requirements-test.txt")


@pytest.fixture(scope="module")
def graph_dir(tmp_path_factory) -> Path:
    """Export a tiny but genuine ONNX graph: y = x @ W + b, then relu."""

    class Tiny(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.linear = torch.nn.Linear(4, 3)

        def forward(self, image):
            return torch.relu(self.linear(image))

    directory = tmp_path_factory.mktemp("onnx-model")
    torch.onnx.export(
        Tiny().eval(),
        (torch.zeros(1, 4),),
        str(directory / "model.onnx"),
        input_names=["image"],
        output_names=["logits"],
        dynamo=False,
    )
    return directory


def _record(path: Path, *, backends=("cpu",), expected_files=()) -> DynamicModelRecord:
    manifest = ModelManifest(
        id="tiny-onnx",
        name="Tiny ONNX",
        task="image-segmentation",
        adapter="onnx",
        source=ModelSource(type="local"),
        runtime=RuntimeRequirement(profile="onnx-runtime"),
        hardware=HardwareRequirement(backends=backends),
        expected_files=expected_files,
    )
    return DynamicModelRecord(manifest=manifest, path=path, installed=True, enabled=True)


def test_onnx_is_a_registered_adapter_and_runtime():
    assert isinstance(ADAPTERS["onnx"], OnnxAdapter)
    profile = RUNTIME_PROFILES["onnx-runtime"]
    assert profile.adapter == "onnx"
    assert "directml" in profile.backends


def test_loads_and_runs_a_real_graph(graph_dir):
    adapter = OnnxAdapter()
    session = adapter.load(_record(graph_dir))

    numpy = pytest.importorskip("numpy")
    outputs = adapter.run(session, {"image": numpy.zeros((1, 4), dtype=numpy.float32)})

    assert set(outputs) == {"logits"}
    assert outputs["logits"].shape == (1, 3)
    assert (outputs["logits"] >= 0).all()  # relu


def test_output_matches_the_torch_model_it_was_exported_from(graph_dir):
    numpy = pytest.importorskip("numpy")
    adapter = OnnxAdapter()
    session = adapter.load(_record(graph_dir))
    sample = numpy.array([[0.5, -1.0, 2.0, 0.25]], dtype=numpy.float32)

    produced = adapter.run(session, {"image": sample})["logits"]

    reference = session.run(None, {"image": sample})[0]
    numpy.testing.assert_allclose(produced, reference, rtol=1e-6)


def test_missing_input_names_the_input_it_wanted(graph_dir):
    adapter = OnnxAdapter()
    session = adapter.load(_record(graph_dir))

    with pytest.raises(AdapterError, match="image"):
        adapter.run(session, {"wrong_name": 1})


def test_folder_without_a_graph_is_rejected(tmp_path):
    with pytest.raises(AdapterError, match="must contain a .onnx graph"):
        OnnxAdapter().load(_record(tmp_path))


def test_ambiguous_folder_asks_for_an_explicit_choice(graph_dir, tmp_path):
    directory = tmp_path / "two-graphs"
    directory.mkdir()
    for name in ("a.onnx", "b.onnx"):
        (directory / name).write_bytes((graph_dir / "model.onnx").read_bytes())

    with pytest.raises(AdapterError, match="several .onnx graphs"):
        OnnxAdapter().load(_record(directory))

    resolved = OnnxAdapter().load(_record(directory, expected_files=("b.onnx",)))
    assert resolved is not None


def test_declared_backends_choose_the_execution_providers(graph_dir, monkeypatch):
    """A cuda-capable manifest asks for the CUDA provider first, CPU as fallback."""
    captured: dict[str, list[str]] = {}

    class FakeSession:
        def __init__(self, path, options, providers):
            captured["providers"] = list(providers)

    monkeypatch.setattr(onnxruntime, "InferenceSession", FakeSession)
    monkeypatch.setattr(
        onnxruntime,
        "get_available_providers",
        lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
    )

    OnnxAdapter().load(_record(graph_dir, backends=("cuda", "cpu")))

    assert captured["providers"][0] == "CUDAExecutionProvider"
    assert captured["providers"][-1] == "CPUExecutionProvider"


def test_cpu_provider_is_always_present_even_if_undeclared(graph_dir, monkeypatch):
    captured: dict[str, list[str]] = {}

    class FakeSession:
        def __init__(self, path, options, providers):
            captured["providers"] = list(providers)

    monkeypatch.setattr(onnxruntime, "InferenceSession", FakeSession)
    monkeypatch.setattr(onnxruntime, "get_available_providers", lambda: ["CPUExecutionProvider"])

    OnnxAdapter().load(_record(graph_dir, backends=("cuda",)))

    assert captured["providers"] == ["CPUExecutionProvider"]


def test_probe_reports_whether_the_runtime_is_importable():
    assert OnnxAdapter().probe() is True


def test_validate_rejects_a_task_the_adapter_does_not_serve(graph_dir, monkeypatch):
    adapter = OnnxAdapter()
    monkeypatch.setattr(adapter, "supported_tasks", ("image-segmentation",))
    record = _record(graph_dir)

    assert adapter.validate(record) == ()

    manifest = ModelManifest(
        id="tiny-onnx",
        name="Tiny ONNX",
        task="text-to-image",
        adapter="onnx",
        source=ModelSource(type="local"),
        runtime=RuntimeRequirement(profile="onnx-runtime"),
    )
    other = DynamicModelRecord(manifest=manifest, path=graph_dir, installed=True, enabled=True)

    assert adapter.validate(other) != ()
