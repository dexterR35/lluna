"""Custom vision-language model image description: TransformersAdapter.run()
generation kwargs, result-text extraction, and the DynamicRuntimeManager bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from backend.models.adapters import (
    AdapterError,
    TransformersAdapter,
    _extract_description_text,
    describe_image_with_custom_model,
)


class _KwargsPipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, value: Any, **kwargs: Any) -> list[dict[str, str]]:
        self.calls.append({"value": value, **kwargs})
        return [{"generated_text": "a photo of a cat"}]


class _BareOnlyPipeline:
    """Simulates a plain captioning pipeline that rejects extra kwargs."""

    def __call__(self, value: Any, **kwargs: Any) -> list[dict[str, str]]:
        if kwargs:
            raise TypeError("unexpected keyword argument")
        return [{"generated_text": "unconditional caption"}]


def test_run_passes_generation_kwargs_when_supported() -> None:
    pipeline = _KwargsPipeline()

    result = TransformersAdapter().run(
        pipeline,
        {"image": "img", "instruction": "Describe it", "temperature": 0.3, "top_p": 0.8},
    )

    assert result == [{"generated_text": "a photo of a cat"}]
    assert pipeline.calls == [
        {"value": "img", "prompt": "Describe it", "temperature": 0.3, "top_p": 0.8}
    ]


def test_run_falls_back_to_bare_call_when_pipeline_rejects_kwargs() -> None:
    result = TransformersAdapter().run(
        _BareOnlyPipeline(), {"image": "img", "instruction": "Describe it"}
    )

    assert result == [{"generated_text": "unconditional caption"}]


def test_run_respects_cancel_event() -> None:
    import threading

    cancelled = threading.Event()
    cancelled.set()

    with pytest.raises(AdapterError, match="__cancelled__"):
        TransformersAdapter().run(_KwargsPipeline(), {"image": "img"}, cancel_event=cancelled)


@pytest.mark.parametrize(
    "result,expected",
    [
        ("a plain string", "a plain string"),
        ([{"generated_text": "list of dicts"}], "list of dicts"),
        ([{"text": "alt key"}], "alt key"),
        (["a bare string in a list"], "a bare string in a list"),
        ({"generated_text": "bare dict"}, "bare dict"),
        ([], ""),
        ({}, ""),
        ([{"score": 0.9}], ""),
        (None, ""),
    ],
)
def test_extract_description_text_handles_common_pipeline_shapes(result, expected) -> None:
    assert _extract_description_text(result) == expected


def test_describe_image_with_custom_model_returns_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.models.adapters as adapters_module

    image_path = tmp_path / "input.png"
    Image.new("RGB", (4, 4)).save(image_path)

    captured: dict[str, Any] = {}

    class _StubManager:
        def run(self, model_id, inputs, *, progress=None, cancel_event=None):
            captured["model_id"] = model_id
            captured["inputs"] = inputs
            return [{"generated_text": "a small red square"}]

    monkeypatch.setattr(adapters_module.DynamicRuntimeManager, "instance", staticmethod(lambda: _StubManager()))

    text = describe_image_with_custom_model(
        "custom-captioner",
        str(image_path),
        instruction="Describe it",
        temperature=0.3,
        top_p=0.8,
        max_new_tokens=100,
    )

    assert text == "a small red square"
    assert captured["model_id"] == "custom-captioner"
    assert captured["inputs"]["instruction"] == "Describe it"
    assert captured["inputs"]["temperature"] == 0.3
    assert captured["inputs"]["top_p"] == 0.8
    assert captured["inputs"]["max_new_tokens"] == 100
    assert isinstance(captured["inputs"]["image"], Image.Image)


def test_describe_image_with_custom_model_raises_on_empty_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.models.adapters as adapters_module

    image_path = tmp_path / "input.png"
    Image.new("RGB", (4, 4)).save(image_path)

    class _StubManager:
        def run(self, model_id, inputs, *, progress=None, cancel_event=None):
            return [{"score": 0.9}]

    monkeypatch.setattr(adapters_module.DynamicRuntimeManager, "instance", staticmethod(lambda: _StubManager()))

    with pytest.raises(AdapterError, match="did not return a text description"):
        describe_image_with_custom_model("custom-captioner", str(image_path))
