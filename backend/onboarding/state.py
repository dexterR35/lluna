"""Resumable first-run state without Qt or downloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class OnboardingStep(str, Enum):
    WELCOME = "welcome"
    PRIVACY = "privacy"
    HARDWARE = "hardware"
    MODE = "mode"
    SAVE_DIRECTORY = "save_directory"
    FEATURES = "features"
    MODELS = "models"
    REVIEW = "review"
    INSTALLING = "installing"
    READY = "ready"


_ORDER = tuple(OnboardingStep)


@dataclass(frozen=True)
class OnboardingState:
    version: int = 1
    current_step: OnboardingStep = OnboardingStep.WELCOME
    completed_steps: tuple[OnboardingStep, ...] = ()
    save_directory: str = ""
    selected_features: tuple[str, ...] = ()
    selected_models: tuple[str, ...] = ()
    accepted_licenses: tuple[str, ...] = ()
    pending_downloads: tuple[str, ...] = ()
    completed: bool = False

    def advance(self) -> "OnboardingState":
        if self.completed or self.current_step is OnboardingStep.READY:
            return self
        completed = tuple(dict.fromkeys((*self.completed_steps, self.current_step)))
        next_step = _ORDER[_ORDER.index(self.current_step) + 1]
        return OnboardingState(
            **{
                **asdict(self),
                "current_step": next_step,
                "completed_steps": completed,
            }
        )

    def finish(self) -> "OnboardingState":
        return OnboardingState(
            **{
                **asdict(self),
                "current_step": OnboardingStep.READY,
                "completed_steps": tuple(_ORDER),
                "completed": True,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["current_step"] = self.current_step.value
        data["completed_steps"] = [step.value for step in self.completed_steps]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OnboardingState":
        return cls(
            version=int(data.get("version", 1)),
            current_step=OnboardingStep(data.get("current_step", "welcome")),
            completed_steps=tuple(
                OnboardingStep(step) for step in data.get("completed_steps", ())
            ),
            save_directory=str(data.get("save_directory", "")),
            selected_features=tuple(data.get("selected_features", ())),
            selected_models=tuple(data.get("selected_models", ())),
            accepted_licenses=tuple(data.get("accepted_licenses", ())),
            pending_downloads=tuple(data.get("pending_downloads", ())),
            completed=bool(data.get("completed", False)),
        )
