from __future__ import annotations

from unittest.mock import Mock

import pytest

from ui.dashboard_interface import DashboardInterface


@pytest.mark.parametrize(
    "prompt",
    (
        "a portrait with a soft background",
        "upscale fantasy city at night",
        "low light photograph of a forest",
        "video game character concept art",
        "remove bg text on a futuristic poster",
        "model wearing a blue jacket",
    ),
)
def test_prompt_keywords_always_generate_images(prompt: str) -> None:
    dashboard = Mock()

    DashboardInterface._on_prompt(dashboard, prompt)

    dashboard._start_generate.assert_called_once_with(prompt)
