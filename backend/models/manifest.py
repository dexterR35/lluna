"""Versioned manifests for built-in and user-installed Midgard models."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

MANIFEST_FILENAME = "midgard-model.json"
MANIFEST_SCHEMA_VERSION = 1
MODEL_FILE_EXTENSIONS = {
    ".safetensors",
    ".onnx",
    ".pth",
    ".pt",
    ".ckpt",
    ".bin",
    ".pdmodel",
    ".pdiparams",
}
SUPPORTED_ADAPTERS = {
    "diffusers",
    "transformers",
    "onnx",
    "paddle",
    "midgard-native",
    "python-worker",
    "supir",
}
SUPPORTED_TASKS = {
    "text-to-image",
    "image-to-image",
    "image-segmentation",
    "object-detection",
    "image-upscaling",
    "image-restoration",
    "inpainting",
    "text-recognition",
    "text-generation",
    "automatic-speech-recognition",
    "custom",
}
SUPPORTED_VARIANTS = {
    "base",
    "distilled",
    "quantized",
    "lora",
    "controlnet",
    "inpainting",
    "upscaler",
    "finetune",
    "unknown",
}
CAPABILITY_PROVENANCE = {
    "reviewed-catalog",
    "reviewed-manifest",
    "huggingface-metadata",
    "local-inspection",
    "unknown",
}
_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")


class ManifestError(ValueError):
    """Raised when a model manifest is unsafe or invalid."""


def normalize_model_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", str(value).strip().lower()).strip("-._")
    if not normalized:
        normalized = "custom-model"
    return normalized[:128].rstrip("-._")


def _strings(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ManifestError(f"{name} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


@dataclass(frozen=True)
class ModelSource:
    type: str
    repo: str = ""
    revision: str = ""
    url: str = ""
    allow_patterns: tuple[str, ...] = ()
    local_name: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ModelSource":
        source_type = str(raw.get("type", "local")).strip().lower()
        if source_type not in {"huggingface", "local", "bundled", "url"}:
            raise ManifestError(f"Unsupported source type: {source_type}")
        repo = str(raw.get("repo", "")).strip()
        if source_type == "huggingface":
            parts = repo.split("/")
            if len(parts) != 2 or any(not part or part in {".", ".."} for part in parts):
                raise ManifestError("Hugging Face repo must have the form owner/model")
        local_name = str(raw.get("localName", raw.get("local_name", ""))).strip()
        if local_name and Path(local_name).name != local_name:
            raise ManifestError("source.localName must be a file or folder name")
        return cls(
            type=source_type,
            repo=repo,
            revision=str(raw.get("revision", "")).strip(),
            url=str(raw.get("url", "")).strip(),
            allow_patterns=_strings(
                raw.get("allowPatterns", raw.get("allow_patterns")),
                "source.allowPatterns",
            ),
            local_name=local_name,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            **({"repo": self.repo} if self.repo else {}),
            **({"revision": self.revision} if self.revision else {}),
            **({"url": self.url} if self.url else {}),
            **({"allowPatterns": list(self.allow_patterns)} if self.allow_patterns else {}),
            **({"localName": self.local_name} if self.local_name else {}),
        }


@dataclass(frozen=True)
class RuntimeRequirement:
    profile: str
    packages: tuple[str, ...] = ()
    isolated: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RuntimeRequirement":
        profile = str(raw.get("profile", "")).strip()
        if not profile:
            raise ManifestError("runtime.profile is required")
        return cls(
            profile=profile,
            packages=_strings(raw.get("packages"), "runtime.packages"),
            isolated=bool(raw.get("isolated", False)),
        )


@dataclass(frozen=True)
class HardwareRequirement:
    backends: tuple[str, ...] = ("cpu",)
    minimum_ram_mb: int = 0
    minimum_vram_mb: int = 0
    minimum_disk_mb: int = 0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "HardwareRequirement":
        backends = _strings(raw.get("backends", ["cpu"]), "hardware.backends") or ("cpu",)
        allowed = {"cpu", "cuda", "directml", "mps"}
        if any(item not in allowed for item in backends):
            raise ManifestError("hardware.backends contains an unsupported backend")
        numbers = {
            "minimum_ram_mb": raw.get("minimumRamMb", raw.get("minimum_ram_mb", 0)),
            "minimum_vram_mb": raw.get("minimumVramMb", raw.get("minimum_vram_mb", 0)),
            "minimum_disk_mb": raw.get("minimumDiskMb", raw.get("minimum_disk_mb", 0)),
        }
        for name, value in numbers.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ManifestError(f"hardware.{name} must be a non-negative number")
        return cls(backends, *(int(numbers[name]) for name in numbers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "backends": list(self.backends),
            "minimumRamMb": self.minimum_ram_mb,
            "minimumVramMb": self.minimum_vram_mb,
            "minimumDiskMb": self.minimum_disk_mb,
        }


@dataclass(frozen=True)
class SecurityPolicy:
    trust_remote_code: bool = False
    prefer_safetensors: bool = True
    allow_pickle: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SecurityPolicy":
        return cls(
            trust_remote_code=bool(raw.get("trustRemoteCode", raw.get("trust_remote_code", False))),
            prefer_safetensors=bool(
                raw.get("preferSafetensors", raw.get("prefer_safetensors", True))
            ),
            allow_pickle=bool(raw.get("allowPickle", raw.get("allow_pickle", False))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trustRemoteCode": self.trust_remote_code,
            "preferSafetensors": self.prefer_safetensors,
            "allowPickle": self.allow_pickle,
        }


@dataclass(frozen=True)
class ModelVariant:
    kind: str = "unknown"
    base_model: str = ""
    quantization: str = ""
    architecture: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ModelVariant":
        kind = str(raw.get("kind", "unknown")).strip().lower()
        if kind not in SUPPORTED_VARIANTS:
            raise ManifestError(f"Unsupported model variant: {kind}")
        return cls(
            kind=kind,
            base_model=str(raw.get("baseModel", raw.get("base_model", ""))).strip(),
            quantization=str(raw.get("quantization", "")).strip().lower(),
            architecture=str(raw.get("architecture", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "baseModel": self.base_model,
            "quantization": self.quantization,
            "architecture": self.architecture,
        }


@dataclass(frozen=True)
class NumberCapability:
    default: float
    minimum: float
    maximum: float
    values: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ManifestError("Capability minimum cannot exceed maximum")
        if not self.minimum <= self.default <= self.maximum:
            raise ManifestError("Capability default must be inside its range")
        if self.values and (
            any(value < self.minimum or value > self.maximum for value in self.values)
            or self.default not in self.values
        ):
            raise ManifestError(
                "Capability values must include the default and stay inside the range"
            )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], name: str) -> "NumberCapability":
        try:
            default = float(raw["default"])
            minimum = float(raw.get("minimum", default))
            maximum = float(raw.get("maximum", default))
            values = tuple(float(value) for value in raw.get("values", ()))
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(
                f"capabilities.{name} must define numeric default/minimum/maximum"
            ) from exc
        return cls(default, minimum, maximum, values)

    def to_dict(self, *, integer: bool = False) -> dict[str, Any]:
        convert = int if integer else float
        return {
            "default": convert(self.default),
            "minimum": convert(self.minimum),
            "maximum": convert(self.maximum),
            **({"values": [convert(value) for value in self.values]} if self.values else {}),
        }


@dataclass(frozen=True)
class ModelCapabilities:
    provenance: str = "unknown"
    tasks: tuple[str, ...] = ()
    negative_prompt: bool | None = None
    guidance: bool | None = None
    seed: bool | None = None
    steps: NumberCapability | None = None
    guidance_scale: NumberCapability | None = None
    supported_widths: tuple[int, ...] = ()
    supported_heights: tuple[int, ...] = ()
    width_multiple: int | None = None
    height_multiple: int | None = None
    dtypes: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    lora_strength: NumberCapability | None = None
    control_strength: NumberCapability | None = None
    control_start: NumberCapability | None = None
    control_end: NumberCapability | None = None
    denoise_strength: NumberCapability | None = None
    scales: tuple[int, ...] = ()
    tile_size: NumberCapability | None = None
    tile_overlap: NumberCapability | None = None

    def __post_init__(self) -> None:
        if self.provenance not in CAPABILITY_PROVENANCE:
            raise ManifestError(f"Unsupported capability provenance: {self.provenance}")
        if any(task not in SUPPORTED_TASKS for task in self.tasks):
            raise ManifestError("capabilities.tasks contains an unsupported task")
        for name in ("supported_widths", "supported_heights", "scales"):
            if any(value <= 0 for value in getattr(self, name)):
                raise ManifestError(f"capabilities.{name} must contain positive integers")
        for name in ("width_multiple", "height_multiple"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ManifestError(f"capabilities.{name} must be positive")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ModelCapabilities":
        def number(key: str) -> NumberCapability | None:
            value = raw.get(key)
            return NumberCapability.from_mapping(value, key) if isinstance(value, Mapping) else None

        def integers(key: str) -> tuple[int, ...]:
            value = raw.get(key, ())
            if not isinstance(value, (list, tuple)):
                raise ManifestError(f"capabilities.{key} must be a list")
            try:
                return tuple(int(item) for item in value)
            except (TypeError, ValueError) as exc:
                raise ManifestError(f"capabilities.{key} must contain integers") from exc

        def optional_bool(key: str) -> bool | None:
            value = raw.get(key)
            if value is None:
                return None
            if not isinstance(value, bool):
                raise ManifestError(f"capabilities.{key} must be a boolean")
            return value

        def optional_integer(key: str) -> int | None:
            value = raw.get(key)
            if value is None:
                return None
            if isinstance(value, bool):
                raise ManifestError(f"capabilities.{key} must be an integer")
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise ManifestError(f"capabilities.{key} must be an integer") from exc

        return cls(
            provenance=str(raw.get("provenance", "unknown")).strip().lower(),
            tasks=_strings(raw.get("tasks"), "capabilities.tasks"),
            negative_prompt=optional_bool("negativePrompt"),
            guidance=optional_bool("guidance"),
            seed=optional_bool("seed"),
            steps=number("steps"),
            guidance_scale=number("guidanceScale"),
            supported_widths=integers("supportedWidths"),
            supported_heights=integers("supportedHeights"),
            width_multiple=optional_integer("widthMultiple"),
            height_multiple=optional_integer("heightMultiple"),
            dtypes=_strings(raw.get("dtypes"), "capabilities.dtypes"),
            inputs=_strings(raw.get("inputs"), "capabilities.inputs"),
            outputs=_strings(raw.get("outputs"), "capabilities.outputs"),
            lora_strength=number("loraStrength"),
            control_strength=number("controlStrength"),
            control_start=number("controlStart"),
            control_end=number("controlEnd"),
            denoise_strength=number("denoiseStrength"),
            scales=integers("scales"),
            tile_size=number("tileSize"),
            tile_overlap=number("tileOverlap"),
        )

    def unresolved(self, primary_task: str) -> tuple[str, ...]:
        missing: list[str] = []
        if self.provenance == "unknown":
            missing.append("provenance")
        if primary_task not in self.tasks:
            missing.append("tasks")
        if not self.inputs:
            missing.append("inputs")
        if not self.outputs:
            missing.append("outputs")
        if primary_task in {"text-to-image", "image-to-image", "inpainting"}:
            if self.steps is None:
                missing.append("steps")
            if self.guidance is None:
                missing.append("guidance")
            if self.negative_prompt is None:
                missing.append("negativePrompt")
            if self.seed is None:
                missing.append("seed")
            if not (self.supported_widths or self.width_multiple):
                missing.append("supportedWidths")
            if not (self.supported_heights or self.height_multiple):
                missing.append("supportedHeights")
            if not self.dtypes:
                missing.append("dtypes")
        if primary_task == "image-upscaling" and not self.scales:
            missing.append("scales")
        if primary_task == "inpainting" and self.denoise_strength is None:
            missing.append("denoiseStrength")
        return tuple(dict.fromkeys(missing))

    def is_complete(self, primary_task: str) -> bool:
        return not self.unresolved(primary_task)

    def to_dict(self, primary_task: str) -> dict[str, Any]:
        return {
            "provenance": self.provenance,
            "complete": self.is_complete(primary_task),
            "unresolved": list(self.unresolved(primary_task)),
            "tasks": list(self.tasks),
            "negativePrompt": self.negative_prompt,
            "guidance": self.guidance,
            "seed": self.seed,
            "steps": self.steps.to_dict(integer=True) if self.steps else None,
            "guidanceScale": self.guidance_scale.to_dict() if self.guidance_scale else None,
            "supportedWidths": list(self.supported_widths),
            "supportedHeights": list(self.supported_heights),
            "widthMultiple": self.width_multiple,
            "heightMultiple": self.height_multiple,
            "dtypes": list(self.dtypes),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "loraStrength": self.lora_strength.to_dict() if self.lora_strength else None,
            "controlStrength": self.control_strength.to_dict() if self.control_strength else None,
            "controlStart": self.control_start.to_dict() if self.control_start else None,
            "controlEnd": self.control_end.to_dict() if self.control_end else None,
            "denoiseStrength": self.denoise_strength.to_dict() if self.denoise_strength else None,
            "scales": list(self.scales),
            "tileSize": self.tile_size.to_dict(integer=True) if self.tile_size else None,
            "tileOverlap": self.tile_overlap.to_dict(integer=True) if self.tile_overlap else None,
        }


@dataclass(frozen=True)
class ModelManifest:
    id: str
    name: str
    task: str
    adapter: str
    source: ModelSource
    runtime: RuntimeRequirement
    hardware: HardwareRequirement = field(default_factory=HardwareRequirement)
    security: SecurityPolicy = field(default_factory=SecurityPolicy)
    variant: ModelVariant = field(default_factory=ModelVariant)
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    schema: int = MANIFEST_SCHEMA_VERSION
    description: str = ""
    license: str = "See upstream model card"
    gated: bool = False
    expected_files: tuple[str, ...] = ()
    expected_size_bytes: int | None = None
    needs_configuration: bool = False

    def __post_init__(self) -> None:
        if self.schema != MANIFEST_SCHEMA_VERSION:
            raise ManifestError(f"Unsupported model manifest schema: {self.schema}")
        if not _ID_RE.fullmatch(self.id):
            raise ManifestError(
                "Model id must use lowercase letters, numbers, dots, dashes, or underscores"
            )
        if not self.name.strip():
            raise ManifestError("Model name is required")
        if self.task not in SUPPORTED_TASKS:
            raise ManifestError(f"Unsupported model task: {self.task}")
        if self.adapter not in SUPPORTED_ADAPTERS:
            raise ManifestError(f"Unsupported model adapter: {self.adapter}")
        for relative in self.expected_files:
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts:
                raise ManifestError("expectedFiles must stay inside the model folder")

    def configuration_issues(self) -> tuple[str, ...]:
        issues = list(self.capabilities.unresolved(self.task))
        if self.task in {"text-to-image", "image-to-image", "inpainting"}:
            if self.variant.kind == "unknown":
                issues.append("variant.kind")
            if self.variant.kind == "quantized" and not self.variant.quantization:
                issues.append("variant.quantization")
            if self.variant.kind in {"lora", "controlnet"} and not self.variant.base_model:
                issues.append("variant.baseModel")
            if self.variant.kind == "lora" and self.capabilities.lora_strength is None:
                issues.append("loraStrength")
            if self.variant.kind == "controlnet":
                if self.capabilities.control_strength is None:
                    issues.append("controlStrength")
                if self.capabilities.control_start is None:
                    issues.append("controlStart")
                if self.capabilities.control_end is None:
                    issues.append("controlEnd")
        return tuple(dict.fromkeys(issues))

    def is_configured(self) -> bool:
        return not self.needs_configuration and not self.configuration_issues()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ModelManifest":
        if not isinstance(raw, Mapping):
            raise ManifestError("Model manifest must be an object")
        size = raw.get("expectedSizeBytes", raw.get("expected_size_bytes"))
        if size is not None and (
            isinstance(size, bool) or not isinstance(size, (int, float)) or size < 0
        ):
            raise ManifestError("expectedSizeBytes must be a non-negative number")
        return cls(
            schema=int(raw.get("schema", MANIFEST_SCHEMA_VERSION)),
            id=str(raw.get("id", "")).strip(),
            name=str(raw.get("name", raw.get("displayName", ""))).strip(),
            description=str(raw.get("description", "")).strip(),
            task=str(raw.get("task", "custom")).strip().lower(),
            adapter=str(raw.get("adapter", "python-worker")).strip().lower(),
            license=str(raw.get("license", "See upstream model card")).strip(),
            gated=bool(raw.get("gated", False)),
            source=ModelSource.from_mapping(dict(raw.get("source", {}))),
            runtime=RuntimeRequirement.from_mapping(dict(raw.get("runtime", {}))),
            hardware=HardwareRequirement.from_mapping(dict(raw.get("hardware", {}))),
            security=SecurityPolicy.from_mapping(dict(raw.get("security", {}))),
            variant=ModelVariant.from_mapping(dict(raw.get("variant", {}))),
            capabilities=ModelCapabilities.from_mapping(dict(raw.get("capabilities", {}))),
            expected_files=_strings(
                raw.get("expectedFiles", raw.get("expected_files")), "expectedFiles"
            ),
            expected_size_bytes=int(size) if size is not None else None,
            needs_configuration=bool(raw.get("needsConfiguration", False)),
        )

    @classmethod
    def from_file(cls, path: Path) -> "ModelManifest":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ManifestError(f"Could not read {path.name}: {exc}") from exc
        return cls.from_mapping(raw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task": self.task,
            "adapter": self.adapter,
            "license": self.license,
            "gated": self.gated,
            "source": self.source.to_dict(),
            "runtime": {
                "profile": self.runtime.profile,
                "packages": list(self.runtime.packages),
                "isolated": self.runtime.isolated,
            },
            "hardware": self.hardware.to_dict(),
            "security": self.security.to_dict(),
            "variant": self.variant.to_dict(),
            "capabilities": self.capabilities.to_dict(self.task),
            "expectedFiles": list(self.expected_files),
            "expectedSizeBytes": self.expected_size_bytes,
            "needsConfiguration": self.needs_configuration or bool(self.configuration_issues()),
            "configurationIssues": list(self.configuration_issues()),
        }


def model_files(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        return (path,) if path.suffix.lower() in MODEL_FILE_EXTENSIONS else ()
    try:
        return tuple(
            item
            for item in path.rglob("*")
            if item.is_file() and item.suffix.lower() in MODEL_FILE_EXTENSIONS
        )
    except OSError:
        return ()


def infer_adapter(path: Path) -> tuple[str, str, str]:
    files = model_files(path)
    suffixes = {item.suffix.lower() for item in files}
    if ".onnx" in suffixes:
        return "onnx", "onnx-runtime", "custom"
    if (path / "model_index.json").is_file() if path.is_dir() else False:
        return "diffusers", "diffusers-torch", "text-to-image"
    if (path / "config.json").is_file() if path.is_dir() else False:
        return "transformers", "transformers-torch", "custom"
    if suffixes & {".pdmodel", ".pdiparams"}:
        return "paddle", "paddle", "custom"
    return "python-worker", "custom-python", "custom"


def inferred_manifest(path: Path) -> ModelManifest:
    adapter, runtime, task = infer_adapter(path)
    from backend.models.capability_resolver import inspect_local_contract

    variant, capabilities = inspect_local_contract(path, task=task, adapter=adapter)
    identifier = normalize_model_id(path.stem if path.is_file() else path.name)
    expected = (
        (path.name,)
        if path.is_file()
        else tuple(str(item.relative_to(path)) for item in model_files(path))
    )
    legacy_pickle = any(
        item.suffix.lower() in {".pth", ".pt", ".ckpt", ".bin"} for item in model_files(path)
    )
    return ModelManifest(
        id=identifier,
        name=(path.stem if path.is_file() else path.name)
        .replace("-", " ")
        .replace("_", " ")
        .title(),
        description="Discovered locally; review its task and runtime before enabling.",
        task=task,
        adapter=adapter,
        source=ModelSource("local", local_name=path.name),
        runtime=RuntimeRequirement(runtime, isolated=runtime == "custom-python"),
        security=SecurityPolicy(False, not legacy_pickle, legacy_pickle),
        variant=variant,
        capabilities=capabilities,
        expected_files=expected,
        needs_configuration=True,
    )
