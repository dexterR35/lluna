"""Runtime validation for model-specific parameter contracts."""

from __future__ import annotations

from typing import Any, Mapping


def _number_issue(name: str, value: Any, contract: Mapping[str, Any]) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"{name} must be numeric."
    minimum = contract.get("minimum")
    maximum = contract.get("maximum")
    values = contract.get("values") or []
    if minimum is not None and value < minimum:
        return f"{name} must be at least {minimum}."
    if maximum is not None and value > maximum:
        return f"{name} must be at most {maximum}."
    if values and value not in values:
        return f"{name} must be one of {', '.join(str(item) for item in values)}."
    return None


def validate_generation_inputs(
    capabilities: Mapping[str, Any], inputs: Mapping[str, Any]
) -> tuple[str, ...]:
    """Validate declared generation inputs without inferring missing capabilities."""
    if not capabilities.get("complete"):
        return ("Model capabilities are incomplete; review its manifest before use.",)

    issues: list[str] = []
    for key, label, supported_key, multiple_key in (
        ("width", "Width", "supportedWidths", "widthMultiple"),
        ("height", "Height", "supportedHeights", "heightMultiple"),
    ):
        value = inputs.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            issues.append(f"{label} must be an integer.")
            continue
        supported = capabilities.get(supported_key) or []
        multiple = capabilities.get(multiple_key)
        if supported and value not in supported:
            issues.append(f"{label} must be one of {', '.join(str(item) for item in supported)}.")
        elif multiple and value % int(multiple):
            issues.append(f"{label} must be a multiple of {multiple}.")

    if inputs.get("steps") is not None:
        if not isinstance(capabilities.get("steps"), Mapping):
            issues.append("This model does not declare inference steps.")
        elif issue := _number_issue("Steps", inputs["steps"], capabilities["steps"]):
            issues.append(issue)

    guidance = inputs.get("guidance")
    if guidance is not None:
        if capabilities.get("guidance") is not True:
            issues.append("This model does not support guidance.")
        elif isinstance(capabilities.get("guidanceScale"), Mapping):
            if issue := _number_issue("Guidance", guidance, capabilities["guidanceScale"]):
                issues.append(issue)

    if str(inputs.get("negativePrompt") or "").strip() and capabilities.get("negativePrompt") is not True:
        issues.append("This model does not support negative prompts.")
    seed = inputs.get("seed")
    if seed is not None and seed != -1 and capabilities.get("seed") is not True:
        issues.append("This model does not support a seed.")
    return tuple(issues)
