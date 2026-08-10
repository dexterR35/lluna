"""Composing LoRA adapters onto a base pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.models import lora
from backend.models.dynamic_registry import DynamicModelRecord
from backend.models.lora import (
    LoraError,
    LoraSelection,
    applied,
    parse_selections,
    resolve_selections,
    selection_signature,
)
from backend.models.reference.manifest import (
    ModelManifest,
    ModelSource,
    ModelVariant,
    RuntimeRequirement,
)


class _FakePipeline:
    """Records what diffusers would have been asked to do."""

    def __init__(self, *, fail_on_load: bool = False) -> None:
        self.loaded: list[tuple[str, dict]] = []
        self.adapters: tuple[list[str], list[float]] | None = None
        self.unloaded = 0
        self._fail_on_load = fail_on_load

    def load_lora_weights(self, path, **kwargs):
        if self._fail_on_load:
            raise ValueError("not a LoRA checkpoint")
        self.loaded.append((str(path), kwargs))

    def set_adapters(self, names, adapter_weights=None):
        self.adapters = (list(names), list(adapter_weights or []))

    def unload_lora_weights(self):
        self.unloaded += 1


def _record(model_id: str, *, kind: str = "lora", base: str = "flux", **flags):
    manifest = ModelManifest(
        id=model_id,
        name=model_id,
        task="text-to-image",
        adapter="diffusers",
        source=ModelSource(type="local"),
        runtime=RuntimeRequirement(profile="diffusers-torch"),
        variant=ModelVariant(kind=kind, base_model=base),
        expected_files=flags.pop("expected_files", ()),
    )
    return DynamicModelRecord(
        manifest=manifest,
        path=Path(f"/models/{model_id}"),
        installed=flags.pop("installed", True),
        enabled=flags.pop("enabled", True),
    )


@pytest.fixture
def registry(monkeypatch):
    records: dict[str, DynamicModelRecord] = {}

    class _Registry:
        def get(self, model_id, refresh=False):
            if model_id not in records:
                raise KeyError(model_id)
            return records[model_id]

    monkeypatch.setattr(
        "backend.models.dynamic_registry.DynamicModelRegistry.instance", lambda: _Registry()
    )
    return records


# --- parsing -----------------------------------------------------------------


def test_bare_ids_and_objects_both_parse():
    assert parse_selections("style") == (LoraSelection("style", 1.0),)
    assert parse_selections([{"modelId": "style", "weight": 0.6}]) == (
        LoraSelection("style", 0.6),
    )


def test_order_is_preserved():
    parsed = parse_selections([{"modelId": "a"}, {"modelId": "b"}])
    assert [item.model_id for item in parsed] == ["a", "b"]


def test_empty_selection_is_not_an_error():
    assert parse_selections(None) == ()
    assert parse_selections([]) == ()


def test_the_same_lora_cannot_be_selected_twice():
    with pytest.raises(LoraError, match="selected twice"):
        parse_selections([{"modelId": "a"}, {"modelId": "a", "weight": 0.5}])


def test_a_non_numeric_weight_is_refused():
    with pytest.raises(LoraError, match="non-numeric weight"):
        parse_selections([{"modelId": "a", "weight": "strong"}])


def test_too_many_loras_are_refused():
    with pytest.raises(LoraError, match="At most"):
        parse_selections([{"modelId": f"lora-{index}"} for index in range(9)])


# --- resolution --------------------------------------------------------------


def test_resolves_installed_enabled_loras(registry):
    registry["style"] = _record("style")

    resolved = resolve_selections(parse_selections(["style"]), base_model_id="flux")

    assert len(resolved) == 1
    assert resolved[0].adapter_name == "style"


def test_missing_lora_is_reported_by_name(registry):
    with pytest.raises(LoraError, match="not installed"):
        resolve_selections(parse_selections(["ghost"]), base_model_id="flux")


def test_disabled_lora_is_refused(registry):
    registry["style"] = _record("style", enabled=False)

    with pytest.raises(LoraError, match="not enabled"):
        resolve_selections(parse_selections(["style"]), base_model_id="flux")


def test_a_model_that_is_not_a_lora_is_refused(registry):
    registry["sdxl"] = _record("sdxl", kind="base")

    with pytest.raises(LoraError, match="not a LoRA"):
        resolve_selections(parse_selections(["sdxl"]), base_model_id="flux")


def test_lora_for_a_different_base_model_is_refused(registry):
    """The whole failure mode LoRAs have: silently wrong output."""
    registry["sdxl-style"] = _record("sdxl-style", base="stabilityai/sdxl-base")

    with pytest.raises(LoraError, match="was trained for"):
        resolve_selections(parse_selections(["sdxl-style"]), base_model_id="flux")


@pytest.mark.parametrize(
    "declared",
    ["flux", "FLUX", "black-forest-labs/flux", "flux-dev"],
)
def test_base_matching_tolerates_upstream_repo_naming(registry, declared):
    """A LoRA card names the upstream repo; the node names Lluna's model id."""
    registry["style"] = _record("style", base=declared)

    assert resolve_selections(parse_selections(["style"]), base_model_id="custom:flux")


def test_custom_prefix_is_stripped_on_both_sides(registry):
    registry["style"] = _record("style")

    assert resolve_selections(parse_selections(["custom:style"]), base_model_id="flux")


# --- application -------------------------------------------------------------


def test_weights_are_passed_through_to_set_adapters(registry):
    registry["a"] = _record("a")
    registry["b"] = _record("b")
    resolved = resolve_selections(
        parse_selections([{"modelId": "a", "weight": 0.8}, {"modelId": "b", "weight": 0.35}]),
        base_model_id="flux",
    )
    pipeline = _FakePipeline()

    with applied(pipeline, resolved):
        pass

    assert pipeline.adapters == (["a", "b"], [0.8, 0.35])


def test_adapters_are_removed_after_the_block(registry):
    """Pipelines are cached between runs; a leaked adapter poisons the next run."""
    registry["a"] = _record("a")
    resolved = resolve_selections(parse_selections(["a"]), base_model_id="flux")
    pipeline = _FakePipeline()

    with applied(pipeline, resolved):
        assert pipeline.unloaded == 0

    assert pipeline.unloaded == 1


def test_adapters_are_removed_even_when_generation_fails(registry):
    registry["a"] = _record("a")
    resolved = resolve_selections(parse_selections(["a"]), base_model_id="flux")
    pipeline = _FakePipeline()

    with pytest.raises(RuntimeError):
        with applied(pipeline, resolved):
            raise RuntimeError("generation blew up")

    assert pipeline.unloaded == 1


def test_no_selection_touches_the_pipeline_at_all():
    pipeline = _FakePipeline()

    with applied(pipeline, ()) as returned:
        assert returned is pipeline

    assert pipeline.loaded == [] and pipeline.unloaded == 0


def test_a_pipeline_without_lora_support_says_so():
    with pytest.raises(LoraError, match="does not support LoRA"):
        with applied(object(), (lora.ResolvedLora(LoraSelection("a"), Path("/x"), "a"),)):
            pass


def test_a_bad_lora_file_names_the_lora(registry):
    registry["a"] = _record("a")
    resolved = resolve_selections(parse_selections(["a"]), base_model_id="flux")
    pipeline = _FakePipeline(fail_on_load=True)

    with pytest.raises(LoraError, match="'a' could not be loaded"):
        with applied(pipeline, resolved):
            pass


def test_declared_weight_file_is_passed_when_present(registry):
    registry["a"] = _record("a", expected_files=("pytorch_lora_weights.safetensors",))
    resolved = resolve_selections(parse_selections(["a"]), base_model_id="flux")
    pipeline = _FakePipeline()

    with applied(pipeline, resolved):
        pass

    assert pipeline.loaded[0][1]["weight_name"] == "pytorch_lora_weights.safetensors"


# --- cache correctness -------------------------------------------------------


def test_signature_distinguishes_weights():
    assert selection_signature(parse_selections([{"modelId": "a", "weight": 0.5}])) != (
        selection_signature(parse_selections([{"modelId": "a", "weight": 0.9}]))
    )


def test_cache_key_changes_with_the_lora_selection():
    """Two runs differing only by LoRA must not share a cached artifact."""
    from backend.graph.cache import build_cache_key
    from backend.graph.schema import WorkflowNode

    def key(loras):
        node = WorkflowNode(
            id="gen",
            schema_id="lluna.generate.image",
            parameters={"model": "flux", "prompt": "a cat", "loras": loras},
        )
        return build_cache_key(node, ["input"])

    assert key([]) != key([{"modelId": "a", "weight": 1.0}])
    assert key([{"modelId": "a", "weight": 1.0}]) != key([{"modelId": "a", "weight": 0.4}])
    assert key([{"modelId": "a"}]) == key([{"modelId": "a"}])


def test_lora_revision_is_part_of_the_model_fingerprint(monkeypatch):
    """Replacing a LoRA's weights in place must invalidate cached outputs."""
    from backend.graph.executor import _model_revision_for_node
    from backend.graph.schema import WorkflowNode

    stamps = {"style": "111"}

    class _Registry:
        def revision_stamp(self, model_id, refresh=False):
            return stamps.get(model_id, "")

    monkeypatch.setattr(
        "backend.models.dynamic_registry.DynamicModelRegistry.instance", lambda: _Registry()
    )
    node = WorkflowNode(
        id="gen",
        schema_id="lluna.generate.image",
        parameters={"model": "flux", "loras": [{"modelId": "style"}]},
    )

    before = _model_revision_for_node(node)
    stamps["style"] = "222"
    after = _model_revision_for_node(node)

    assert before != after
    assert "style" in before


def test_a_lora_is_installable_rather_than_incompatible():
    """It cannot run alone, but it must still be installable and enableable."""
    from backend.models.reference.runtimes import compatible_backend

    manifest = ModelManifest(
        id="style",
        name="Style",
        task="text-to-image",
        adapter="diffusers",
        source=ModelSource(type="huggingface", repo="owner/style"),
        runtime=RuntimeRequirement(profile="diffusers-torch"),
        variant=ModelVariant(kind="lora", base_model="flux"),
    )

    _backend, reasons, warnings = compatible_backend(manifest)

    assert reasons == ()
    assert any("does not run on its own" in warning for warning in warnings)
