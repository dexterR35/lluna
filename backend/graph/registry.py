"""Backend-owned catalog of Lluna workflow nodes."""

from __future__ import annotations

import threading

from backend.graph.schema import (
    NodeCompanion,
    NodeDefinition,
    ParameterCondition,
    ParameterDefinition,
    PortDefinition,
)
from backend.graph.types import PortType


def port(
    id: str,
    label: str,
    type: PortType,
    *,
    required: bool = False,
    multiple: bool = False,
) -> PortDefinition:
    return PortDefinition(
        id=id,
        label=label,
        type=type,
        required=required,
        multiple=multiple,
    )


def parameter(id: str, label: str, type: str, default=None, **kwargs) -> ParameterDefinition:
    return ParameterDefinition(id=id, label=label, type=type, default=default, **kwargs)


def option(value: str, label: str, model_id: str, description: str = "") -> dict:
    return {"value": value, "label": label, "modelId": model_id, "description": description}


UPSCALE_MODELS = [
    option(
        "RealESRGAN_x2plus",
        "Real-ESRGAN ×2",
        "realesrgan-x2",
        "Balanced detail restoration and 2× enlargement.",
    ),
    option(
        "RealESRGAN_x4plus",
        "Real-ESRGAN ×4",
        "realesrgan-x4",
        "Maximum enlargement with higher memory use.",
    ),
    option(
        "SUPIR",
        "SUPIR · diffusion restoration",
        "supir",
        "Professional photo-realistic restoration with quality/fidelity tuning (CUDA).",
    ),
    option(
        "SeedVR2_3B",
        "SeedVR2 · 3B",
        "seedvr2-3b",
        "Official one-step image/video restoration with a lower-memory 3B transformer (CUDA).",
    ),
    option(
        "SeedVR2_7B",
        "SeedVR2 · 7B",
        "seedvr2-7b",
        "Higher-capacity one-step image/video restoration (CUDA, very high VRAM).",
    ),
]
BIREFNET_MODELS = [
    option("BiRefNet", "BiRefNet · general", "birefnet", "Official general-purpose model."),
    option("BiRefNet_dynamic", "BiRefNet · dynamic", "birefnet-dynamic", "Better across mixed image resolutions."),
    option("BiRefNet_HR", "BiRefNet · HR", "birefnet-hr", "High-resolution background removal."),
    option("BiRefNet_HR-matting", "BiRefNet · HR matting", "birefnet-hr-matting", "High-resolution soft-alpha matting."),
    option("BiRefNet_lite-2K", "BiRefNet · Lite 2K", "birefnet-lite-2k", "Lower-memory 2K model."),
    option("BiRefNet-matting", "BiRefNet · matting", "birefnet-matting", "Trimap-free soft-alpha matting."),
]
SUPIR_POSITIVE_PROMPT = (
    "Cinematic, High Contrast, highly detailed, taken using a Canon EOS R camera, "
    "hyper detailed photo - realistic maximum detail, 32k, Color Grading, ultra HD, "
    "extreme meticulous detailing, skin pore detailing, hyper sharpness, perfect without deformations."
)
SUPIR_NEGATIVE_PROMPT = (
    "painting, oil painting, illustration, drawing, art, sketch, cartoon, CG Style, "
    "3D render, unreal engine, blurring, dirty, messy, worst quality, low quality, "
    "frames, watermark, signature, jpeg artifacts, deformed, lowres, over-smooth"
)
GENERATE_MODELS = [
    option(
        "FLUX.2-klein-base-4B",
        "FLUX.2 Klein Base 4B",
        "generate:FLUX.2-klein-base-4B",
        "Recommended balance of quality and memory.",
    ),
    option(
        "FLUX.2-klein-4B",
        "FLUX.2 Klein 4B",
        "generate:FLUX.2-klein-4B",
        "Fast distilled 4B generation.",
    ),
    option(
        "FLUX.2-klein-base-9B",
        "FLUX.2 Klein Base 9B",
        "generate:FLUX.2-klein-base-9B",
        "Higher-quality base model.",
    ),
    option(
        "FLUX.2-klein-9B",
        "FLUX.2 Klein 9B",
        "generate:FLUX.2-klein-9B",
        "Fast higher-capacity generation.",
    ),
    option(
        "FLUX.2-dev", "FLUX.2 Dev", "generate:FLUX.2-dev", "Large non-commercial development model."
    ),
    option(
        "FLUX.2-klein-9b-fp8",
        "FLUX.2 Klein 9B FP8",
        "generate:FLUX.2-klein-9b-fp8",
        "Lower-memory FP8 variant.",
    ),
    option("Qwen-Image", "Qwen-Image", "generate:Qwen-Image", "Apache-licensed image generation."),
]
IMAGE_EDIT_MODELS = [item for item in GENERATE_MODELS if item["value"] != "Qwen-Image"]
GENERATE_DTYPE_OPTIONS = [
    {"value": "auto", "label": "Auto (recommended)"},
    {"value": "bf16", "label": "BF16"},
    {"value": "fp16", "label": "FP16"},
    {"value": "fp32", "label": "FP32 · highest precision, more VRAM"},
    {"value": "fp8", "label": "FP8 · CUDA only"},
    {"value": "int8", "label": "INT8 · custom models only, needs bitsandbytes"},
    {"value": "int4", "label": "INT4 · custom models only, needs bitsandbytes"},
]


def node(schema_id: str, name: str, category: str, description: str, **kwargs) -> NodeDefinition:
    return NodeDefinition(
        schema_id=schema_id, name=name, category=category, description=description, **kwargs
    )


_NODES = [
    node(
        "lluna.input.image",
        "Load Image",
        "Input/Media",
        "Loads an image through a desktop file grant.",
        kind="input",
        icon="image",
        outputs=[port("image", "Image", PortType.IMAGE)],
        parameters=[parameter("pathGrantId", "Image file", "file", required=True)],
        supports_preview=True,
        adapter="load_image",
    ),
    node(
        "lluna.input.images",
        "Load Images",
        "Input/Media",
        "Loads an ordered image queue through desktop file grants (max 10).",
        kind="input",
        icon="images",
        outputs=[port("images", "Images", PortType.IMAGE, multiple=True)],
        parameters=[parameter("pathGrantIds", "Image files", "files", [], required=True)],
        supports_preview=True,
        adapter="load_images",
    ),
    node(
        "lluna.input.video",
        "Load Video",
        "Input/Media",
        "Loads a video through a desktop file grant.",
        kind="input",
        icon="film",
        outputs=[port("video", "Video", PortType.VIDEO)],
        parameters=[parameter("pathGrantId", "Video file", "file", required=True)],
        supports_preview=True,
        adapter="load_video",
    ),
    node(
        "lluna.input.mask",
        "Load Mask",
        "Input/Media",
        "Loads a grayscale mask.",
        kind="input",
        icon="scan",
        outputs=[port("mask", "Mask", PortType.MASK)],
        parameters=[parameter("pathGrantId", "Mask file", "file", required=True)],
        supports_preview=True,
        adapter="load_mask",
    ),
    node(
        "lluna.input.prompt",
        "Prompt",
        "Input/Values",
        "Provides a text-to-image prompt.",
        kind="input",
        icon="text-cursor-input",
        outputs=[port("prompt", "Prompt", PortType.PROMPT)],
        parameters=[parameter("value", "Prompt", "textarea", "")],
        adapter="literal",
    ),
    node(
        "lluna.input.llava",
        "LLaVA Caption",
        "Input/AI",
        "Configures the automatic LLaVA image description used by SUPIR restoration.",
        kind="input",
        icon="sparkles",
        outputs=[port("config", "LLaVA settings", PortType.MODEL)],
        parameters=[
            parameter(
                "temperature",
                "Temperature",
                "number",
                0.2,
                minimum=0,
                maximum=1,
                step=0.1,
                description="Controls caption creativity. Lower values are more literal and repeatable.",
            ),
            parameter(
                "topP",
                "Top-p",
                "number",
                0.7,
                minimum=0,
                maximum=1,
                step=0.1,
                description="Limits token sampling to the most likely choices; lower values are more focused.",
            ),
            parameter(
                "question",
                "Instruction",
                "textarea",
                "Describe this image and its style in a very detailed manner. The image is a realistic photography, not an art painting.",
                description="Tells LLaVA what visual details to describe for SUPIR's restoration prompt.",
            ),
            parameter(
                "load8Bit",
                "8-bit model (lower VRAM)",
                "boolean",
                False,
                description="Loads LLaVA in 8-bit precision to reduce VRAM use, with a possible quality or speed tradeoff.",
            ),
        ],
        required_models=["supir"],
        cache_policy="none",
        adapter="llava_config",
    ),
    node(
        "lluna.input.describe_image",
        "Describe Image",
        "Image/Describe",
        "Generates a text description of an image with a custom vision-language model, usable as a prompt elsewhere.",
        icon="sparkles",
        inputs=[port("image", "Image", PortType.IMAGE, required=True)],
        outputs=[port("prompt", "Description", PortType.PROMPT)],
        parameters=[
            parameter("model", "Model", "model", "", options=[]),
            parameter(
                "instruction",
                "Instruction",
                "textarea",
                "Describe this image in detail.",
                description="Tells the model what visual details to describe.",
            ),
            parameter(
                "temperature",
                "Temperature",
                "number",
                0.2,
                minimum=0,
                maximum=1,
                step=0.1,
                capability="temperature",
                description="Controls description creativity. Lower values are more literal and repeatable.",
            ),
            parameter(
                "topP",
                "Top-p",
                "number",
                0.7,
                minimum=0,
                maximum=1,
                step=0.1,
                capability="topP",
                description="Limits token sampling to the most likely choices; lower values are more focused.",
            ),
            parameter(
                "maxNewTokens",
                "Max length",
                "integer",
                200,
                minimum=1,
                maximum=2000,
                capability="maxNewTokens",
                description="Upper bound on how many tokens the description can contain.",
            ),
        ],
        required_models=[],
        cache_policy="none",
        adapter="describe_image",
    ),
    node(
        "lluna.input.number",
        "Number",
        "Input/Values",
        "Provides a numeric value.",
        kind="input",
        outputs=[port("value", "Number", PortType.NUMBER)],
        parameters=[parameter("value", "Value", "number", 0)],
        adapter="literal",
    ),
    node(
        "lluna.input.integer",
        "Integer",
        "Input/Values",
        "Provides an integer value.",
        kind="input",
        outputs=[port("value", "Integer", PortType.INTEGER)],
        parameters=[parameter("value", "Value", "integer", 0)],
        adapter="literal",
    ),
    node(
        "lluna.input.boolean",
        "Boolean",
        "Input/Values",
        "Provides a boolean value.",
        kind="input",
        outputs=[port("value", "Boolean", PortType.BOOLEAN)],
        parameters=[parameter("value", "Value", "boolean", False)],
        adapter="literal",
    ),
    node(
        "lluna.generate.image",
        "Generate Image",
        "Image/Generate",
        "Generates an image locally with an installed Diffusers model.",
        icon="sparkles",
        inputs=[
            port("prompt", "Prompt", PortType.PROMPT, required=True),
            port("control", "Control", PortType.CONTROL, required=False, multiple=True),
        ],
        outputs=[port("image", "Image", PortType.IMAGE)],
        parameters=[
            parameter("model", "Model", "model", "FLUX.2-klein-base-4B", options=GENERATE_MODELS),
            parameter(
                "width", "Width", "integer", 768, minimum=64, maximum=8192, capability="width"
            ),
            parameter(
                "height", "Height", "integer", 768, minimum=64, maximum=8192, capability="height"
            ),
            parameter("steps", "Steps", "integer", 4, minimum=1, maximum=250, capability="steps"),
            parameter(
                "guidance",
                "Guidance",
                "number",
                4.0,
                minimum=0,
                maximum=20,
                step=0.1,
                capability="guidance",
            ),
            parameter(
                "negativePrompt", "Negative prompt", "textarea", "", capability="negativePrompt"
            ),
            parameter(
                "seed",
                "Seed",
                "integer",
                -1,
                description="Use -1 for a random seed.",
                capability="seed",
            ),
            parameter(
                "dtype",
                "Precision",
                "select",
                "auto",
                options=GENERATE_DTYPE_OPTIONS,
                description="Lower precision uses less VRAM; FP32 is slower but most exact.",
                capability="dtype",
            ),
            parameter(
                "loras",
                "LoRAs",
                "lora-list",
                [],
                description=(
                    "Optional adapters composed onto the model above, each with its own "
                    "weight. Import LoRAs from Settings -> Models -> Add model."
                ),
                capability="lora",
            ),
        ],
        capabilities=["diffusers"],
        required_models=["flux"],
        supports_preview=True,
        adapter="generate",
    ),
    node(
        "lluna.generate.image.edit",
        "Edit Image",
        "Image/Generate",
        "Transforms a reference image with a prompt using an image-conditioned Diffusers model.",
        icon="wand-sparkles",
        inputs=[
            port("image", "Reference image", PortType.IMAGE, required=True),
            port("prompt", "Prompt", PortType.PROMPT, required=True),
            port("control", "Control", PortType.CONTROL, required=False, multiple=True),
        ],
        outputs=[port("image", "Image", PortType.IMAGE)],
        parameters=[
            parameter("model", "Model", "model", "FLUX.2-klein-base-4B", options=IMAGE_EDIT_MODELS),
            parameter("width", "Width", "integer", 768, minimum=64, maximum=8192, capability="width"),
            parameter("height", "Height", "integer", 768, minimum=64, maximum=8192, capability="height"),
            parameter("steps", "Steps", "integer", 4, minimum=1, maximum=250, capability="steps"),
            parameter("guidance", "Guidance", "number", 4.0, minimum=0, maximum=20, step=0.1, capability="guidance"),
            parameter("denoiseStrength", "Denoise strength", "number", 0.65, minimum=0.01, maximum=1, step=0.01, description="Lower values preserve more of the reference image.", capability="denoiseStrength"),
            parameter("negativePrompt", "Negative prompt", "textarea", "", capability="negativePrompt"),
            parameter("seed", "Seed", "integer", -1, description="Use -1 for a random seed.", capability="seed"),
            parameter(
                "dtype",
                "Precision",
                "select",
                "auto",
                options=GENERATE_DTYPE_OPTIONS,
                description="Lower precision uses less VRAM; FP32 is slower but most exact.",
                capability="dtype",
            ),
            parameter(
                "loras",
                "LoRAs",
                "lora-list",
                [],
                description=(
                    "Optional adapters composed onto the model above, each with its own "
                    "weight. Import LoRAs from Settings -> Models -> Add model."
                ),
                capability="lora",
            ),
        ],
        capabilities=["diffusers", "image-to-image"],
        required_models=["flux"],
        supports_preview=True,
        adapter="generate",
    ),
    node(
        "lluna.image.upscale",
        "Upscale Image",
        "Image/Enhance",
        "Upscales image queues with Real-ESRGAN, SUPIR, or official SeedVR2 restoration.",
        icon="zoom-in",
        inputs=[
            port("image", "Image queue", PortType.IMAGE, required=True, multiple=True),
            port("llava", "LLaVA settings", PortType.MODEL),
        ],
        outputs=[port("image", "Images", PortType.IMAGE, multiple=True)],
        parameters=[
            parameter("model", "Model", "model", "RealESRGAN_x2plus", options=UPSCALE_MODELS),
            parameter(
                "seedvrTargetLongEdge",
                "SeedVR2 target long edge",
                "integer",
                2048,
                minimum=512,
                maximum=8192,
                step=16,
                description="Target output size. SeedVR2 preserves the input aspect ratio.",
                visible_for_models=["SeedVR2_3B", "SeedVR2_7B"],
            ),
            parameter(
                "seedvrSpSize",
                "SeedVR2 GPU group size",
                "integer",
                1,
                minimum=1,
                maximum=8,
                description="Use one process per GPU for long videos; keep 1 for images.",
                visible_for_models=["SeedVR2_3B", "SeedVR2_7B"],
            ),
            parameter(
                "seedvrSeed",
                "SeedVR2 seed",
                "integer",
                666,
                minimum=-1,
                maximum=2147483647,
                visible_for_models=["SeedVR2_3B", "SeedVR2_7B"],
            ),
            parameter(
                "denoise",
                "Pre-denoise",
                "boolean",
                False,
                visible_for_models=["RealESRGAN_x2plus", "RealESRGAN_x4plus"],
            ),
            parameter(
                "denoiseStrength",
                "Denoise strength",
                "select",
                "safe",
                options=[
                    {"value": "safe", "label": "Safe"},
                    {"value": "medium", "label": "Medium"},
                ],
                visible_for_models=["RealESRGAN_x2plus", "RealESRGAN_x4plus"],
            ),
            parameter(
                "maxLongEdge",
                "Maximum long edge",
                "integer",
                5000,
                minimum=256,
                maximum=32768,
                description="Caps the final image size to manage memory.",
                visible_for_models=["RealESRGAN_x2plus", "RealESRGAN_x4plus"],
            ),
            parameter(
                "supirPreset",
                "Tuning preset",
                "select",
                "quality",
                options=[
                    {"value": "quality", "label": "Quality · more detail"},
                    {"value": "fidelity", "label": "Fidelity · closer to input"},
                    {"value": "custom", "label": "Custom"},
                ],
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "supirVariant",
                "Checkpoint",
                "select",
                "Q",
                options=[
                    {"value": "Q", "label": "v0-Q · general quality"},
                    {"value": "F", "label": "v0-F · light degradation"},
                ],
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "upscale",
                "Upscale factor",
                "integer",
                2,
                minimum=1,
                maximum=8,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "minSize",
                "Minimum output side",
                "integer",
                1024,
                minimum=512,
                maximum=2048,
                step=64,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "edmSteps",
                "EDM sampling steps",
                "integer",
                50,
                minimum=1,
                maximum=200,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "sStage1",
                "Stage 1 restoration",
                "number",
                -1.0,
                minimum=-1,
                maximum=6,
                step=1,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "sStage2",
                "Stage 2 guidance",
                "number",
                1.0,
                minimum=0,
                maximum=1,
                step=0.05,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "sCfg",
                "Text guidance (CFG)",
                "number",
                4.0,
                minimum=1,
                maximum=15,
                step=0.1,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "seed",
                "Seed",
                "integer",
                1234,
                minimum=-1,
                maximum=2147483647,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "sChurn",
                "EDM churn",
                "number",
                5,
                minimum=0,
                maximum=40,
                step=1,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "sNoise",
                "EDM noise",
                "number",
                1.01,
                minimum=1,
                maximum=1.1,
                step=0.001,
                visible_for_models=["SUPIR"],
            ),
            parameter("prompt", "Image description", "textarea", "", visible_for_models=["SUPIR"]),
            parameter(
                "positivePrompt",
                "Additive positive prompt",
                "textarea",
                SUPIR_POSITIVE_PROMPT,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "negativePrompt",
                "Negative prompt",
                "textarea",
                SUPIR_NEGATIVE_PROMPT,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "colorFixType",
                "Color correction",
                "select",
                "Wavelet",
                options=[
                    {"value": "None", "label": "None"},
                    {"value": "AdaIn", "label": "AdaIN"},
                    {"value": "Wavelet", "label": "Wavelet"},
                ],
                visible_for_models=["SUPIR"],
            ),
            parameter("linearCfg", "Linear CFG", "boolean", True, visible_for_models=["SUPIR"]),
            parameter(
                "cfgStart",
                "Linear CFG start",
                "number",
                1.0,
                minimum=1,
                maximum=9,
                step=0.5,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "linearStage2", "Linear Stage 2", "boolean", False, visible_for_models=["SUPIR"]
            ),
            parameter(
                "stage2Start",
                "Stage 2 start",
                "number",
                0.0,
                minimum=0,
                maximum=1,
                step=0.05,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "gammaCorrection",
                "Gamma correction",
                "number",
                1.0,
                minimum=0.1,
                maximum=2,
                step=0.1,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "diffDtype",
                "Diffusion precision",
                "select",
                "fp16",
                options=[
                    {"value": "fp32", "label": "FP32"},
                    {"value": "fp16", "label": "FP16"},
                    {"value": "bf16", "label": "BF16"},
                ],
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "aeDtype",
                "Autoencoder precision",
                "select",
                "bf16",
                options=[
                    {"value": "fp32", "label": "FP32"},
                    {"value": "bf16", "label": "BF16"},
                ],
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "useLlava",
                "Automatic LLaVA caption",
                "boolean",
                True,
                description="Adds a separate LLaVA Caption node when enabled and removes it when disabled.",
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "loadingHalfParams",
                "Half-precision model load",
                "boolean",
                False,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "useTileVae",
                "Tiled VAE (lower VRAM)",
                "boolean",
                False,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "encoderTileSize",
                "VAE encoder tile",
                "integer",
                512,
                minimum=128,
                maximum=1024,
                step=64,
                visible_for_models=["SUPIR"],
            ),
            parameter(
                "decoderTileSize",
                "VAE decoder tile",
                "integer",
                64,
                minimum=32,
                maximum=256,
                step=32,
                visible_for_models=["SUPIR"],
            ),
        ],
        capabilities=["pytorch"],
        required_models=[],
        supports_preview=True,
        adapter="enhance",
        companions=[
            NodeCompanion(
                schema_id="lluna.input.llava",
                target_port="llava",
                source_port="config",
                when=[
                    ParameterCondition(parameter_id="model", equals="SUPIR"),
                    ParameterCondition(parameter_id="useLlava", equals=True),
                ],
            )
        ],
    ),
    node(
        "lluna.video.upscale",
        "Upscale Video",
        "Video/Enhance",
        "Restores and upscales video with official SeedVR2 temporal inference.",
        icon="film",
        inputs=[port("video", "Video", PortType.VIDEO, required=True)],
        outputs=[port("video", "Video", PortType.VIDEO)],
        parameters=[
            parameter(
                "model",
                "Model",
                "model",
                "SeedVR2_3B",
                options=[item for item in UPSCALE_MODELS if item["value"].startswith("SeedVR2")],
            ),
            parameter(
                "seedvrTargetLongEdge",
                "Target long edge",
                "integer",
                2048,
                minimum=512,
                maximum=8192,
                step=16,
            ),
            parameter(
                "seedvrSpSize",
                "GPU group size",
                "integer",
                1,
                minimum=1,
                maximum=8,
                description="One process per GPU for long videos.",
            ),
            parameter(
                "seedvrSeed",
                "Seed",
                "integer",
                666,
                minimum=-1,
                maximum=2147483647,
            ),
        ],
        capabilities=["pytorch"],
        required_models=[],
        supports_preview=True,
        adapter="enhance",
    ),
    node(
        "lluna.image.remove_background",
        "Remove Background",
        "Image/Remove",
        "Creates a transparent foreground using an installed BiRefNet variant.",
        icon="layers",
        inputs=[port("image", "Image queue", PortType.IMAGE, required=True, multiple=True)],
        outputs=[
            port("image", "Transparent images", PortType.IMAGE, multiple=True),
            port("mask", "Segmentation masks", PortType.MASK, multiple=True),
            port("alpha", "Soft alpha", PortType.ALPHA, multiple=True),
        ],
        parameters=[
            parameter("model", "Model", "model", "BiRefNet", options=BIREFNET_MODELS),
            parameter("resolution", "Inference resolution", "integer", 1024, minimum=256, maximum=2304, step=32),
            parameter(
                "precision", "Inference precision", "select", "auto",
                options=[
                    {"value": "auto", "label": "Auto"},
                    {"value": "fp16", "label": "FP16 · faster/lower VRAM"},
                    {"value": "fp32", "label": "FP32 · maximum compatibility"},
                ],
            ),
            parameter("threshold", "Alpha threshold", "number", 0.5, minimum=0, maximum=1, step=0.01),
            parameter("feather", "Edge feather", "integer", 0, minimum=0, maximum=32, step=1),
            parameter(
                "outputMode", "Output", "select", "transparent",
                options=[
                    {"value": "transparent", "label": "Transparent PNG"},
                    {"value": "white", "label": "White background"},
                    {"value": "black", "label": "Black background"},
                    {"value": "custom", "label": "Custom color"},
                ],
            ),
            parameter("backgroundColor", "Custom background", "text", "#ffffff"),
        ],
        supports_preview=True,
        cache_policy="none",
        adapter="birefnet",
    ),
    node(
        "lluna.image.low_light",
        "Fix Low Light",
        "Image/Enhance",
        "Restores one dark image or an ordered image queue with MIRNet.",
        icon="sun",
        inputs=[port("image", "Image queue", PortType.IMAGE, required=True, multiple=True)],
        outputs=[port("image", "Images", PortType.IMAGE, multiple=True)],
        parameters=[
            parameter(
                "model",
                "Model",
                "model",
                "MIRNet_LOL",
                options=[
                    option("MIRNet_LOL", "MIRNet LOL", "mirnet", "Low-light image restoration.")
                ],
            )
        ],
        required_models=["mirnet"],
        supports_preview=True,
        adapter="low_light",
    ),
    node(
        "lluna.image.effects",
        "Image Effects",
        "Image/Adjust",
        "Applies a saved color or detail effect so the preview and exported image match.",
        icon="sparkles",
        inputs=[port("image", "Image queue", PortType.IMAGE, required=True, multiple=True)],
        outputs=[port("image", "Images", PortType.IMAGE, multiple=True)],
        parameters=[
            parameter(
                "preset",
                "Effect",
                "select",
                "none",
                options=[
                    {"value": "none", "label": "Original"},
                    {"value": "vivid", "label": "Vivid"},
                    {"value": "soft", "label": "Soft light"},
                    {"value": "warm", "label": "Warm"},
                    {"value": "cool", "label": "Cool"},
                    {"value": "mono", "label": "Monochrome"},
                ],
            ),
            parameter(
                "brightness", "Brightness", "number", 1.0,
                minimum=0.25, maximum=2.0, step=0.05,
            ),
            parameter("contrast", "Contrast", "number", 1.0, minimum=0.25, maximum=2.0, step=0.05),
            parameter(
                "saturation", "Saturation", "number", 1.0,
                minimum=0.0, maximum=2.0, step=0.05,
            ),
            parameter("blur", "Blur", "number", 0.0, minimum=0.0, maximum=20.0, step=0.5),
            parameter("sharpen", "Sharpen", "number", 0.0, minimum=0.0, maximum=5.0, step=0.25),
        ],
        supports_preview=True,
        adapter="image_effects",
    ),
    node(
        "lluna.image.composite",
        "Composite Background",
        "Image/Compose",
        "Places transparent foregrounds over generated or uploaded backgrounds.",
        icon="layers",
        inputs=[
            port("foreground", "Foregrounds", PortType.IMAGE, required=True, multiple=True),
            port("background", "Backgrounds", PortType.IMAGE, required=True, multiple=True),
        ],
        outputs=[port("image", "Composites", PortType.IMAGE, multiple=True)],
        parameters=[
            parameter(
                "fit",
                "Background fit",
                "select",
                "cover",
                options=[
                    {"value": "cover", "label": "Cover"},
                    {"value": "contain", "label": "Contain"},
                    {"value": "stretch", "label": "Stretch"},
                ],
            )
        ],
        supports_preview=True,
        adapter="composite",
    ),
    node(
        "lluna.image.control_map",
        "Control Map",
        "Image/Compose",
        "Turns an image into a structural hint (edges, depth, pose) for ControlNet.",
        icon="git-branch",
        inputs=[port("image", "Source image", PortType.IMAGE, required=True)],
        outputs=[port("image", "Control map", PortType.IMAGE)],
        parameters=[
            parameter(
                "kind",
                "Control type",
                "select",
                "canny",
                options=[
                    {
                        "value": "canny",
                        "label": "Canny edges",
                        "description": "Built in, no download. Preserves composition.",
                    },
                    {
                        "value": "depth",
                        "label": "Depth map",
                        "description": "Preserves 3D layout. Needs the depth model installed.",
                    },
                    {
                        "value": "pose",
                        "label": "Human pose",
                        "description": "Preserves posture. Needs the pose model installed.",
                    },
                ],
            ),
            parameter(
                "low",
                "Edge low threshold",
                "integer",
                100,
                minimum=0,
                maximum=500,
                description="Canny only. Lower keeps fainter edges.",
            ),
            parameter(
                "high",
                "Edge high threshold",
                "integer",
                200,
                minimum=1,
                maximum=1000,
                description="Canny only. Must be above the low threshold.",
            ),
        ],
        supports_preview=True,
        adapter="control_map",
    ),
    node(
        "lluna.image.controlnet",
        "ControlNet",
        "Image/Generate",
        "Steers a generation model with a control map, without changing the prompt.",
        icon="git-branch",
        inputs=[port("image", "Control map", PortType.IMAGE, required=True)],
        outputs=[port("control", "Control", PortType.CONTROL)],
        parameters=[
            parameter(
                "model",
                "ControlNet",
                "model",
                "",
                options=[],
                description="Install ControlNets from Settings -> Models -> Add model.",
            ),
            parameter(
                "strength",
                "Strength",
                "number",
                1.0,
                minimum=0,
                maximum=2,
                step=0.05,
                description="How strongly the control map constrains the result.",
                capability="controlStrength",
            ),
            parameter(
                "start",
                "Start",
                "number",
                0.0,
                minimum=0,
                maximum=1,
                step=0.05,
                description="Fraction of the run where guidance begins.",
                capability="controlStart",
            ),
            parameter(
                "end",
                "End",
                "number",
                1.0,
                minimum=0,
                maximum=1,
                step=0.05,
                description="Fraction of the run where guidance ends. Ending early frees the model to add detail.",
                capability="controlEnd",
            ),
        ],
        cache_policy="none",
        adapter="controlnet",
    ),
    node(
        "lluna.mask.select_object",
        "Select Object",
        "Mask/Selection",
        "Creates a mask from clicks or a text description.",
        icon="mouse-pointer-2",
        inputs=[port("image", "Image", PortType.IMAGE, required=True)],
        outputs=[
            port("source_image", "Source Image", PortType.IMAGE),
            port("mask", "Mask", PortType.MASK),
        ],
        parameters=[
            parameter(
                "text",
                "Object name",
                "text",
                "",
                description="Name the object to find, or leave blank and select it with preview clicks.",
            ),
            parameter(
                "points",
                "Selection points",
                "json",
                [],
                description="Pixel coordinates selected in the shared preview.",
            ),
            parameter("labels", "Point labels", "json", []),
            parameter("moreComplex", "High quality", "boolean", False),
        ],
        required_models=["sam2", "grounding-dino"],
        supports_preview=True,
        cache_policy="none",
        adapter="select_subject",
    ),
    node(
        "lluna.image.lama_retouch",
        "LaMa Retouch",
        "Image/Retouch",
        "Fills a masked region using the bundled LaMa model.",
        icon="paintbrush",
        inputs=[
            port("image", "Image", PortType.IMAGE, required=True),
            port("mask", "Mask", PortType.MASK, required=True),
        ],
        outputs=[port("image", "Image", PortType.IMAGE)],
        required_models=["lama"],
        supports_preview=True,
        adapter="lama_retouch",
    ),
    node(
        "lluna.image.remove_text",
        "Remove Text from Image",
        "Image/Remove",
        "Detects and removes text from an image.",
        inputs=[port("image", "Image", PortType.IMAGE, required=True)],
        outputs=[port("image", "Image", PortType.IMAGE)],
        required_models=["paddleocr-server", "lama"],
        supports_preview=True,
        adapter="subtitle",
    ),
    node(
        "lluna.video.remove_text",
        "Remove Text from Video",
        "Video/Remove",
        "Removes subtitles or text while preserving source timing and audio.",
        schema_version=2,
        icon="captions-off",
        inputs=[port("video", "Video", PortType.VIDEO, required=True)],
        outputs=[port("video", "Video", PortType.VIDEO)],
        parameters=[
            parameter(
                "subAreas",
                "Removal areas",
                "regions",
                [],
                description="Rectangles selected on the source video, stored as pixel coordinates.",
            )
        ],
        required_models=["paddleocr-server", "sttn-auto"],
        supports_preview=True,
        adapter="subtitle",
    ),
    node(
        "lluna.video.remove_background",
        "Remove Background from Video",
        "Video/Remove",
        "Runs BiRefNet on every frame, preserving the source frame rate and audio when possible.",
        icon="layers",
        inputs=[port("video", "Video", PortType.VIDEO, required=True)],
        outputs=[port("video", "Foreground video", PortType.VIDEO)],
        parameters=[
            parameter("model", "Model", "model", "BiRefNet", options=BIREFNET_MODELS),
            parameter("resolution", "Inference resolution", "integer", 1024, minimum=256, maximum=2304, step=32),
            parameter(
                "precision", "Inference precision", "select", "auto",
                options=[
                    {"value": "auto", "label": "Auto"},
                    {"value": "fp16", "label": "FP16 · faster/lower VRAM"},
                    {"value": "fp32", "label": "FP32 · maximum compatibility"},
                ],
            ),
            parameter("threshold", "Alpha threshold", "number", 0.5, minimum=0, maximum=1, step=0.01),
            parameter("feather", "Edge feather", "integer", 0, minimum=0, maximum=32, step=1),
            parameter(
                "outputMode", "Output", "select", "transparent",
                options=[
                    {"value": "transparent", "label": "Transparent MOV"},
                    {"value": "white", "label": "White background MP4"},
                    {"value": "black", "label": "Black background MP4"},
                    {"value": "custom", "label": "Custom color MP4"},
                ],
            ),
            parameter("backgroundColor", "Custom background", "text", "#ffffff"),
        ],
        supports_preview=True,
        adapter="birefnet",
    ),
    node(
        "lluna.output.preview_image",
        "Preview Image",
        "Output/Preview",
        "Shows one image or an ordered image queue on the node.",
        kind="output",
        icon="eye",
        inputs=[port("image", "Images", PortType.IMAGE, required=True, multiple=True)],
        outputs=[port("image", "Images", PortType.IMAGE, multiple=True)],
        supports_preview=True,
        adapter="passthrough",
    ),
    node(
        "lluna.output.preview_mask",
        "Preview Mask",
        "Output/Preview",
        "Shows a grayscale segmentation mask or image mask on the node.",
        kind="output",
        icon="scan",
        inputs=[port("mask", "Masks", PortType.MASK, required=True, multiple=True)],
        outputs=[port("mask", "Masks", PortType.MASK, multiple=True)],
        supports_preview=True,
        adapter="passthrough",
    ),
    node(
        "lluna.output.preview_alpha",
        "Preview Alpha",
        "Output/Preview",
        "Shows the soft alpha channel on the node.",
        kind="output",
        icon="scan",
        inputs=[port("alpha", "Alpha", PortType.ALPHA, required=True, multiple=True)],
        outputs=[port("alpha", "Alpha", PortType.ALPHA, multiple=True)],
        supports_preview=True,
        adapter="passthrough",
    ),
    node(
        "lluna.output.preview_video",
        "Preview Video",
        "Output/Preview",
        "Shows a proxy video preview.",
        kind="output",
        icon="play",
        inputs=[port("video", "Video", PortType.VIDEO, required=True)],
        outputs=[port("video", "Video", PortType.VIDEO)],
        supports_preview=True,
        adapter="passthrough",
    ),
    node(
        "lluna.output.save_image",
        "Save Image",
        "Output/Save",
        "Saves one image or an image queue to a user-selected folder.",
        kind="output",
        icon="save",
        inputs=[port("image", "Image", PortType.IMAGE, required=True, multiple=True)],
        outputs=[port("image", "Saved Image", PortType.IMAGE, multiple=True)],
        parameters=[
            parameter("destinationGrantId", "Destination folder", "directory", ""),
            parameter(
                "conflictPolicy",
                "If a file already exists",
                "select",
                "ask",
                options=[
                    {"value": "ask", "label": "Ask before replacing"},
                    {"value": "replace", "label": "Replace existing"},
                    {"value": "keep-both", "label": "Keep both"},
                ],
            ),
        ],
        side_effects=True,
        cache_policy="none",
        adapter="save",
    ),
    node(
        "lluna.output.save_video",
        "Save Video",
        "Output/Save",
        "Copies a video artifact to a user-selected destination.",
        kind="output",
        icon="save",
        inputs=[port("video", "Video", PortType.VIDEO, required=True)],
        outputs=[port("video", "Saved Video", PortType.VIDEO)],
        parameters=[parameter("destinationGrantId", "Destination", "saveFile", "")],
        side_effects=True,
        cache_policy="none",
        adapter="save",
    ),
]

NODE_REGISTRY = {definition.schema_id: definition for definition in _NODES}


# `_build_catalog` deep-copies every node definition and recomputes each model's
# capability contract. That's too expensive to redo on every `get_node()` call -
# validation and inference call it once per node (and, for batch nodes, once per
# item). The result is cached and only rebuilt when the dynamic model registry
# changes through a Lluna-owned mutation.
_catalog_lock = threading.RLock()
_catalog_cache: list[NodeDefinition] | None = None
_catalog_registry_ref: object | None = None
_catalog_unsubscribe = None


def _invalidate_catalog_cache() -> None:
    global _catalog_cache
    with _catalog_lock:
        _catalog_cache = None


def _rebind_catalog_listener_locked() -> None:
    """(Re)subscribe to whichever DynamicModelRegistry instance is current.

    Tests swap the singleton instance directly (`monkeypatch.setattr(..., "_instance", ...)`),
    so identity - not just "have we ever subscribed" - has to be checked on every call.
    """
    global _catalog_registry_ref, _catalog_unsubscribe
    try:
        from backend.models.dynamic_registry import DynamicModelRegistry

        current = DynamicModelRegistry.instance()
    except (ImportError, OSError, ValueError):
        return
    if current is _catalog_registry_ref:
        return
    global _catalog_cache
    if _catalog_unsubscribe is not None:
        _catalog_unsubscribe()
    _catalog_registry_ref = current
    _catalog_unsubscribe = current.subscribe(_invalidate_catalog_cache)
    _catalog_cache = None


def _build_catalog() -> list[NodeDefinition]:
    values = [definition.model_copy(deep=True) for definition in NODE_REGISTRY.values()]
    from backend.models.reference.capabilities import builtin_contract

    for definition in values:
        for parameter_definition in definition.parameters:
            for model_option in parameter_definition.options:
                model_id = model_option.get("modelId")
                if not model_id:
                    continue
                variant, capabilities = builtin_contract(str(model_id))
                task = capabilities.tasks[0] if capabilities.tasks else "custom"
                model_option["variant"] = variant.to_dict()
                model_option["capabilities"] = capabilities.to_dict(task)
    try:
        from backend.models.dynamic_registry import DynamicModelRegistry
        from backend.models.reference.runtimes import runtime_status

        configured_records = [
            record
            for record in DynamicModelRegistry.instance().records()
            if record.installed
            and record.enabled
            and record.manifest.is_configured()
            and runtime_status(record.manifest)["runnable"]
        ]
        def _diffusers_option(record) -> dict:
            model_option = option(
                f"custom:{record.manifest.id}",
                record.manifest.name,
                record.manifest.id,
                record.manifest.description or "Custom Diffusers model.",
            )
            model_option["variant"] = record.manifest.variant.to_dict()
            model_option["capabilities"] = record.manifest.capabilities.to_dict(record.manifest.task)
            return model_option

        text_to_image_records = [
            record
            for record in configured_records
            if record.manifest.adapter == "diffusers" and record.manifest.task == "text-to-image"
        ]
        if text_to_image_records:
            generate = next(item for item in values if item.schema_id == "lluna.generate.image")
            model_parameter = next(item for item in generate.parameters if item.id == "model")
            model_parameter.options.extend(_diffusers_option(record) for record in text_to_image_records)

        # Image-to-image models are wired all the way through execution
        # (image + strength, see DiffusersAdapter.run/generate_with_custom_model
        # in backend/models/adapters.py), so they belong on the Edit node.
        # True mask-based inpainting isn't attached anywhere yet: no node in
        # this graph has a mask input port for a custom model to receive one.
        image_to_image_records = [
            record
            for record in configured_records
            if record.manifest.adapter == "diffusers" and record.manifest.task == "image-to-image"
        ]
        if image_to_image_records:
            edit = next(item for item in values if item.schema_id == "lluna.generate.image.edit")
            model_parameter = next(item for item in edit.parameters if item.id == "model")
            model_parameter.options.extend(_diffusers_option(record) for record in image_to_image_records)
        # Attachments are offered wherever they can attach. They are listed by
        # what they were trained for rather than filtered to the node's current
        # model: the base can change after a LoRA is picked, and the run-time
        # check in backend/models/lora.py is what actually enforces the pairing.
        def _attachment_option(record) -> dict:
            base = record.manifest.variant.base_model or "any base model"
            model_option = option(
                f"custom:{record.manifest.id}",
                record.manifest.name,
                record.manifest.id,
                record.manifest.description or f"For {base}.",
            )
            model_option["baseModel"] = record.manifest.variant.base_model
            model_option["variant"] = record.manifest.variant.to_dict()
            return model_option

        for kind, parameter_id, schema_ids in (
            (
                "lora",
                "loras",
                ("lluna.generate.image", "lluna.generate.image.edit"),
            ),
            ("controlnet", "model", ("lluna.image.controlnet",)),
        ):
            attachments = [
                record
                for record in configured_records
                if record.manifest.adapter == "diffusers"
                and record.manifest.variant.kind == kind
            ]
            if not attachments:
                continue
            attachment_options = [_attachment_option(record) for record in attachments]
            for schema_id in schema_ids:
                definition = next(
                    (item for item in values if item.schema_id == schema_id), None
                )
                if definition is None:
                    continue
                target = next(
                    (item for item in definition.parameters if item.id == parameter_id), None
                )
                if target is not None:
                    target.options.extend(attachment_options)

        birefnet_records = [
            record
            for record in configured_records
            if record.manifest.adapter == "birefnet" and record.manifest.task == "image-segmentation"
        ]
        if birefnet_records:
            custom_options = [
                option(
                    f"custom:{record.manifest.id}",
                    record.manifest.name,
                    record.manifest.id,
                    record.manifest.description or "Custom BiRefNet checkpoint.",
                )
                for record in birefnet_records
            ]
            for schema_id in ("lluna.image.remove_background", "lluna.video.remove_background"):
                definition = next(item for item in values if item.schema_id == schema_id)
                model_parameter = next(item for item in definition.parameters if item.id == "model")
                model_parameter.options.extend(custom_options)
        describe_records = [
            record
            for record in configured_records
            if record.manifest.adapter == "transformers" and record.manifest.task == "image-to-text"
        ]
        if describe_records:
            custom_options = []
            for record in describe_records:
                model_option = option(
                    f"custom:{record.manifest.id}",
                    record.manifest.name,
                    record.manifest.id,
                    record.manifest.description or "Custom image description model.",
                )
                model_option["capabilities"] = record.manifest.capabilities.to_dict(record.manifest.task)
                custom_options.append(model_option)
            definition = next(item for item in values if item.schema_id == "lluna.input.describe_image")
            model_parameter = next(item for item in definition.parameters if item.id == "model")
            model_parameter.options.extend(custom_options)
    except (ImportError, OSError, ValueError):
        pass
    return values


def _cached_catalog() -> list[NodeDefinition]:
    with _catalog_lock:
        _rebind_catalog_listener_locked()
        global _catalog_cache
        if _catalog_cache is None:
            _catalog_cache = _build_catalog()
        return _catalog_cache


def list_nodes() -> list[NodeDefinition]:
    return [definition.model_copy(deep=True) for definition in _cached_catalog()]


def get_node(schema_id: str) -> NodeDefinition:
    definition = next(
        (item for item in _cached_catalog() if item.schema_id == schema_id), None
    )
    if definition is None:
        raise KeyError(f"Unknown node schema: {schema_id}")
    return definition.model_copy(deep=True)
