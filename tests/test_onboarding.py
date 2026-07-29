from backend.onboarding.state import OnboardingState, OnboardingStep


def test_onboarding_resumes_round_trip(tmp_path) -> None:
    state = OnboardingState(save_directory=str(tmp_path / "results")).advance().advance()
    restored = OnboardingState.from_dict(state.to_dict())
    assert restored == state
    assert restored.current_step is OnboardingStep.HARDWARE


def test_onboarding_finish_is_idempotent() -> None:
    complete = OnboardingState().finish()
    assert complete.completed
    assert complete.current_step is OnboardingStep.READY
    assert complete.advance() == complete
