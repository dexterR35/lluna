"""Backend-owned catalog of Midgard workflow nodes."""

from __future__ import annotations

from backend.graph.schema import NodeDefinition, ParameterDefinition, PortDefinition
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


def node(schema_id: str, name: str, category: str, description: str, **kwargs) -> NodeDefinition:
    return NodeDefinition(
        schema_id=schema_id, name=name, category=category, description=description, **kwargs
    )


_NODES = [
    node(
        "midgard.input.image",
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
        "midgard.input.images",
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
        "midgard.input.video",
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
        "midgard.input.mask",
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
        "midgard.input.prompt",
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
        "midgard.input.llava",
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
        "midgard.input.number",
        "Number",
        "Input/Values",
        "Provides a numeric value.",
        kind="input",
        outputs=[port("value", "Number", PortType.NUMBER)],
        parameters=[parameter("value", "Value", "number", 0)],
        adapter="literal",
    ),
    node(
        "midgard.input.integer",
        "Integer",
        "Input/Values",
        "Provides an integer value.",
        kind="input",
        outputs=[port("value", "Integer", PortType.INTEGER)],
        parameters=[parameter("value", "Value", "integer", 0)],
        adapter="literal",
    ),
    node(
        "midgard.input.boolean",
        "Boolean",
        "Input/Values",
        "Provides a boolean value.",
        kind="input",
        outputs=[port("value", "Boolean", PortType.BOOLEAN)],
        parameters=[parameter("value", "Value", "boolean", False)],
        adapter="literal",
    ),
    node(
        "midgard.generate.image",
        "Generate Image",
        "Image/Generate",
        "Generates an image locally with an installed Diffusers model.",
        icon="sparkles",
        inputs=[port("prompt", "Prompt", PortType.PROMPT, required=True)],
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
        ],
        capabilities=["diffusers"],
        required_models=["flux"],
        supports_preview=True,
        adapter="generate",
    ),
    node(
        "midgard.image.upscale",
        "Upscale Image",
        "Image/Enhance",
        "Upscales image queues with Real-ESRGAN or diffusion-based SUPIR restoration.",
        icon="zoom-in",
        inputs=[
            port("image", "Image queue", PortType.IMAGE, required=True, multiple=True),
            port("llava", "LLaVA settings", PortType.MODEL),
        ],
        outputs=[port("image", "Images", PortType.IMAGE, multiple=True)],
        parameters=[
            parameter("model", "Model", "model", "RealESRGAN_x2plus", options=UPSCALE_MODELS),
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
        required_models=["realesrgan-x2"],
        supports_preview=True,
        adapter="enhance",
    ),
    node(
        "midgard.image.low_light",
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
        "midgard.image.composite",
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
        "midgard.mask.select_object",
        "Select Object",
        "Mask/Selection",
        "Creates a mask from clicks or a text description.",
        icon="mouse-pointer-2",
        inputs=[port("image", "Image", PortType.IMAGE, required=True)],
        outputs=[port("mask", "Mask", PortType.MASK)],
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
        adapter="select_subject",
    ),
    node(
        "midgard.image.lama_retouch",
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
        "midgard.image.remove_text",
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
        "midgard.video.remove_text",
        "Remove Text from Video",
        "Video/Remove",
        "Removes subtitles or text while preserving source timing and audio.",
        icon="captions-off",
        inputs=[port("video", "Video", PortType.VIDEO, required=True)],
        outputs=[port("video", "Video", PortType.VIDEO)],
        required_models=["paddleocr-server", "sttn-auto"],
        supports_preview=True,
        adapter="subtitle",
    ),
    node(
        "midgard.output.preview_image",
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
        "midgard.output.preview_video",
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
        "midgard.output.save_image",
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
        "midgard.output.save_video",
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


def list_nodes() -> list[NodeDefinition]:
    values = [definition.model_copy(deep=True) for definition in NODE_REGISTRY.values()]
    from backend.models.capability_resolver import builtin_contract

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
        from backend.models.runtime_profiles import runtime_status

        custom_records = [
            record
            for record in DynamicModelRegistry.instance().records()
            if record.installed
            and record.enabled
            and record.manifest.is_configured()
            and runtime_status(record.manifest)["compatible"]
            and record.manifest.adapter == "diffusers"
            and record.manifest.task == "text-to-image"
        ]
        custom = []
        for record in custom_records:
            model_option = option(
                f"custom:{record.manifest.id}",
                record.manifest.name,
                record.manifest.id,
                record.manifest.description or "Custom Diffusers model.",
            )
            model_option["variant"] = record.manifest.variant.to_dict()
            model_option["capabilities"] = record.manifest.capabilities.to_dict(
                record.manifest.task
            )
            custom.append(model_option)
        if custom:
            generate = next(item for item in values if item.schema_id == "midgard.generate.image")
            model_parameter = next(item for item in generate.parameters if item.id == "model")
            model_parameter.options.extend(custom)
    except (ImportError, OSError, ValueError):
        pass
    return values


def get_node(schema_id: str) -> NodeDefinition:
    definition = next((item for item in list_nodes() if item.schema_id == schema_id), None)
    if definition is None:
        raise KeyError(f"Unknown node schema: {schema_id}")
    return definition
