"""Control maps and ControlNet composition."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from backend.ai import preprocessors
from backend.ai.preprocessors import PreprocessorError
from backend.graph.registry import NODE_REGISTRY
from backend.models.conditioning import base_matches
from backend.models.controlnet import (
    ControlNetError,
    ControlSelection,
    call_kwargs,
    composed,
    parse_selections,
    resolve_selections,
)
from backend.models.dynamic_registry import DynamicModelRecord
from backend.models.reference.manifest import (
    ModelManifest,
    ModelSource,
    ModelVariant,
    RuntimeRequirement,
)


def _photo(size=(64, 48)) -> Image.Image:
    """An image with a hard edge, so edge detection has something to find."""
    image = Image.new("RGB", size, (12, 12, 12))
    for x in range(size[0] // 2, size[0]):
        for y in range(size[1]):
            image.putpixel((x, y), (240, 240, 240))
    return image


# --- preprocessors -----------------------------------------------------------


def test_canny_needs_no_model_and_finds_the_edge():
    result = preprocessors.run("canny", _photo())

    assert result.size == (64, 48)
    assert result.mode == "RGB"
    # White edge pixels on black: the vertical boundary must show up.
    assert max(result.convert("L").tobytes()) > 200


def test_canny_is_reported_as_built_in():
    entries = {item["id"]: item for item in preprocessors.available()}

    assert entries["canny"]["builtIn"] is True
    assert entries["canny"]["ready"] is True
    assert entries["depth"]["builtIn"] is False
    assert entries["depth"]["requiredModel"]


def test_thresholds_change_the_result():
    """A gradient has weak edges everywhere, so the thresholds decide what survives."""
    gradient = Image.new("RGB", (64, 48))
    for x in range(64):
        for y in range(48):
            gradient.putpixel((x, y), (x * 4 % 256,) * 3)

    loose = preprocessors.run("canny", gradient, low=10, high=20)
    strict = preprocessors.run("canny", gradient, low=250, high=400)

    assert loose.tobytes() != strict.tobytes()
    assert sum(loose.convert("L").tobytes()) > sum(strict.convert("L").tobytes())


def test_inverted_thresholds_are_refused():
    with pytest.raises(PreprocessorError, match="must be below"):
        preprocessors.run("canny", _photo(), low=300, high=100)


def test_unknown_control_type_lists_the_options():
    with pytest.raises(PreprocessorError, match="Available:"):
        preprocessors.run("scribble", _photo())


@pytest.mark.parametrize("kind", ["depth", "pose"])
def test_uninstalled_preprocessors_say_what_to_install(kind):
    """The user must learn what is missing, not see an import error."""
    with pytest.raises(PreprocessorError, match="Settings"):
        preprocessors.run(kind, _photo())


def test_a_source_image_is_required():
    with pytest.raises(PreprocessorError, match="needs a source image"):
        preprocessors.run("canny", None)


def test_control_map_node_is_registered_and_light():
    """Canny must not queue behind model work for a GPU slot."""
    from backend.graph.scheduler import LIGHT, node_kind

    definition = NODE_REGISTRY["lluna.image.control_map"]

    assert definition.adapter == "control_map"
    assert node_kind(definition) == LIGHT
    assert [port.id for port in definition.outputs] == ["image"]


# --- controlnet selection ----------------------------------------------------


def _record(model_id: str, *, kind: str = "controlnet", base: str = "sdxl", enabled=True):
    manifest = ModelManifest(
        id=model_id,
        name=model_id,
        task="text-to-image",
        adapter="diffusers",
        source=ModelSource(type="local"),
        runtime=RuntimeRequirement(profile="diffusers-torch"),
        variant=ModelVariant(kind=kind, base_model=base),
    )
    return DynamicModelRecord(
        manifest=manifest, path=Path(f"/models/{model_id}"), installed=True, enabled=enabled
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


def test_schedule_window_is_validated():
    with pytest.raises(ControlNetError, match="start < end"):
        parse_selections([{"modelId": "c", "start": 0.8, "end": 0.2}])


def test_schedule_window_defaults_to_the_whole_run():
    selection = parse_selections(["canny-sdxl"])[0]

    assert (selection.start, selection.end, selection.strength) == (0.0, 1.0, 1.0)


def test_a_control_image_is_required(registry):
    """Without one there is nothing to condition on."""
    registry["canny-sdxl"] = _record("canny-sdxl")

    with pytest.raises(ControlNetError, match="no control image"):
        resolve_selections(parse_selections(["canny-sdxl"]), base_model_id="sdxl")


def test_controlnet_for_another_base_is_refused(registry):
    """This is the case that produces noise instead of an error."""
    registry["canny-sdxl"] = _record("canny-sdxl", base="stabilityai/sdxl")

    with pytest.raises(ControlNetError, match="produce noise"):
        resolve_selections(
            parse_selections([{"modelId": "canny-sdxl", "image": _photo()}]),
            base_model_id="flux",
        )


def test_a_lora_cannot_be_used_as_a_controlnet(registry):
    registry["style"] = _record("style", kind="lora")

    with pytest.raises(ControlNetError, match="not a ControlNet"):
        resolve_selections(
            parse_selections([{"modelId": "style", "image": _photo()}]), base_model_id="sdxl"
        )


def test_disabled_controlnet_is_refused(registry):
    registry["canny-sdxl"] = _record("canny-sdxl", enabled=False)

    with pytest.raises(ControlNetError, match="not enabled"):
        resolve_selections(
            parse_selections([{"modelId": "canny-sdxl", "image": _photo()}]),
            base_model_id="sdxl",
        )


def test_matching_controlnet_resolves(registry):
    registry["canny-sdxl"] = _record("canny-sdxl")

    resolved = resolve_selections(
        parse_selections([{"modelId": "canny-sdxl", "image": _photo(), "strength": 0.7}]),
        base_model_id="sdxl",
    )

    assert len(resolved) == 1
    assert resolved[0].selection.strength == 0.7


# --- pipeline call shape -----------------------------------------------------


def test_single_controlnet_passes_bare_values_not_lists():
    """diffusers takes scalars for one ControlNet and lists for several."""
    image = _photo()
    selection = ControlSelection("c", strength=0.5, start=0.1, end=0.9, image=image)
    from backend.models.controlnet import ResolvedControlNet

    kwargs = call_kwargs((ResolvedControlNet(selection, Path("/x"), "c"),))

    assert kwargs["control_image"] is image
    assert kwargs["controlnet_conditioning_scale"] == 0.5
    assert kwargs["control_guidance_start"] == 0.1
    assert kwargs["control_guidance_end"] == 0.9


def test_multiple_controlnets_pass_parallel_lists():
    from backend.models.controlnet import ResolvedControlNet

    first = ControlSelection("a", strength=0.4, image=_photo())
    second = ControlSelection("b", strength=0.9, image=_photo())
    kwargs = call_kwargs(
        (
            ResolvedControlNet(first, Path("/a"), "a"),
            ResolvedControlNet(second, Path("/b"), "b"),
        )
    )

    assert kwargs["controlnet_conditioning_scale"] == [0.4, 0.9]
    assert len(kwargs["control_image"]) == 2


def test_no_selection_passes_nothing_and_touches_no_pipeline():
    sentinel = object()

    assert call_kwargs(()) == {}
    with composed(sentinel, ()) as active:
        assert active is sentinel


# --- compatibility rule ------------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "running", "expected"),
    [
        ("sdxl", "sdxl", True),
        ("stabilityai/sdxl-base", "sdxl", True),
        ("flux", "custom:flux", True),
        ("sdxl", "flux", False),
        ("", "flux", True),
    ],
)
def test_attachment_compatibility(declared, running, expected):
    assert base_matches(declared, running) is expected
