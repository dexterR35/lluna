"""Backend-owned catalog of Midgard workflow nodes."""

from __future__ import annotations

from backend.graph.schema import NodeDefinition, ParameterDefinition, PortDefinition
from backend.graph.types import PortType


def port(id: str, label: str, type: PortType, *, required: bool = False) -> PortDefinition:
    return PortDefinition(id=id, label=label, type=type, required=required)


def parameter(id: str, label: str, type: str, default=None, **kwargs) -> ParameterDefinition:
    return ParameterDefinition(id=id, label=label, type=type, default=default, **kwargs)


def option(value: str, label: str, model_id: str, description: str = "") -> dict:
    return {"value": value, "label": label, "modelId": model_id, "description": description}


BACKGROUND_MODELS = [
    option("birefnet-general", "BiRefNet General", "bg-remove:birefnet-general", "Best general-purpose cutouts."),
    option("birefnet-general-lite", "BiRefNet Lite", "bg-remove:birefnet-general-lite", "Faster general-purpose removal."),
    option("birefnet-portrait", "BiRefNet Portrait", "bg-remove:birefnet-portrait", "Optimized for people and portraits."),
    option("u2net_human_seg", "U²-Net Human", "bg-remove:u2net_human_seg", "Fast human segmentation."),
    option("u2net_cloth_seg", "U²-Net Clothing", "bg-remove:u2net_cloth_seg", "Separates clothing categories."),
    option("isnet-anime", "IS-Net Anime", "bg-remove:isnet-anime", "Illustration and anime artwork."),
    option("isnet-general-use", "IS-Net General", "bg-remove:isnet-general-use", "Balanced classic segmentation."),
    option("bria-rmbg", "BRIA RMBG", "bg-remove:bria-rmbg", "High-quality general background removal."),
]
UPSCALE_MODELS = [
    option("RealESRGAN_x2plus", "Real-ESRGAN ×2", "realesrgan-x2", "Balanced detail restoration and 2× enlargement."),
    option("RealESRGAN_x4plus", "Real-ESRGAN ×4", "realesrgan-x4", "Maximum enlargement with higher memory use."),
]
GENERATE_MODELS = [
    option("FLUX.2-klein-base-4B", "FLUX.2 Klein Base 4B", "generate:FLUX.2-klein-base-4B", "Recommended balance of quality and memory."),
    option("FLUX.2-klein-4B", "FLUX.2 Klein 4B", "generate:FLUX.2-klein-4B", "Fast distilled 4B generation."),
    option("FLUX.2-klein-base-9B", "FLUX.2 Klein Base 9B", "generate:FLUX.2-klein-base-9B", "Higher-quality base model."),
    option("FLUX.2-klein-9B", "FLUX.2 Klein 9B", "generate:FLUX.2-klein-9B", "Fast higher-capacity generation."),
    option("FLUX.2-dev", "FLUX.2 Dev", "generate:FLUX.2-dev", "Large non-commercial development model."),
    option("FLUX.2-klein-9b-fp8", "FLUX.2 Klein 9B FP8", "generate:FLUX.2-klein-9b-fp8", "Lower-memory FP8 variant."),
    option("Qwen-Image", "Qwen-Image", "generate:Qwen-Image", "Apache-licensed image generation."),
]


def node(schema_id: str, name: str, category: str, description: str, **kwargs) -> NodeDefinition:
    return NodeDefinition(schema_id=schema_id, name=name, category=category, description=description, **kwargs)


_NODES = [
    node("midgard.input.image", "Load Image", "Input/Media", "Loads an image through a desktop file grant.", kind="input", icon="image", outputs=[port("image", "Image", PortType.IMAGE)], parameters=[parameter("pathGrantId", "Image file", "file", required=True)], adapter="load_image"),
    node("midgard.input.video", "Load Video", "Input/Media", "Loads a video through a desktop file grant.", kind="input", icon="film", outputs=[port("video", "Video", PortType.VIDEO)], parameters=[parameter("pathGrantId", "Video file", "file", required=True)], adapter="load_video"),
    node("midgard.input.mask", "Load Mask", "Input/Media", "Loads a grayscale mask.", kind="input", icon="scan", outputs=[port("mask", "Mask", PortType.MASK)], parameters=[parameter("pathGrantId", "Mask file", "file", required=True)], adapter="load_mask"),
    node("midgard.input.prompt", "Prompt", "Input/Values", "Provides a text-to-image prompt.", kind="input", icon="text-cursor-input", outputs=[port("prompt", "Prompt", PortType.PROMPT)], parameters=[parameter("value", "Prompt", "textarea", "")], adapter="literal"),
    node("midgard.input.number", "Number", "Input/Values", "Provides a numeric value.", kind="input", outputs=[port("value", "Number", PortType.NUMBER)], parameters=[parameter("value", "Value", "number", 0)], adapter="literal"),
    node("midgard.input.integer", "Integer", "Input/Values", "Provides an integer value.", kind="input", outputs=[port("value", "Integer", PortType.INTEGER)], parameters=[parameter("value", "Value", "integer", 0)], adapter="literal"),
    node("midgard.input.boolean", "Boolean", "Input/Values", "Provides a boolean value.", kind="input", outputs=[port("value", "Boolean", PortType.BOOLEAN)], parameters=[parameter("value", "Value", "boolean", False)], adapter="literal"),
    node("midgard.generate.image", "Generate Image", "Image/Generate", "Generates an image locally with an installed Diffusers model.", icon="sparkles", inputs=[port("prompt", "Prompt", PortType.PROMPT, required=True)], outputs=[port("image", "Image", PortType.IMAGE)], parameters=[parameter("model", "Model", "model", "FLUX.2-klein-base-4B", options=GENERATE_MODELS), parameter("width", "Width", "integer", 768, minimum=64, maximum=8192), parameter("height", "Height", "integer", 768, minimum=64, maximum=8192), parameter("steps", "Steps", "integer", 4, minimum=1, maximum=250), parameter("seed", "Seed", "integer", -1, description="Use -1 for a random seed.")], capabilities=["diffusers"], required_models=["flux"], supports_preview=True, adapter="generate"),
    node("midgard.image.upscale", "Upscale Image", "Image/Enhance", "Upscales an image with Real-ESRGAN.", icon="zoom-in", inputs=[port("image", "Image", PortType.IMAGE, required=True)], outputs=[port("image", "Image", PortType.IMAGE)], parameters=[parameter("model", "Model", "model", "RealESRGAN_x2plus", options=UPSCALE_MODELS), parameter("denoise", "Pre-denoise", "boolean", False), parameter("denoiseStrength", "Denoise strength", "select", "safe", options=[{"value": "safe", "label": "Safe"}, {"value": "medium", "label": "Medium"}]), parameter("maxLongEdge", "Maximum long edge", "integer", 5000, minimum=256, maximum=32768, description="Caps the final image size to manage memory.")], capabilities=["pytorch"], required_models=["realesrgan-x2"], supports_preview=True, adapter="enhance"),
    node("midgard.image.remove_background", "Remove Background", "Image/Remove", "Produces a transparent cutout using a selected local segmentation model.", icon="scissors", inputs=[port("image", "Image", PortType.IMAGE, required=True), port("protectMask", "Protect Mask", PortType.MASK)], outputs=[port("image", "Cutout", PortType.IMAGE), port("alpha", "Alpha", PortType.ALPHA)], parameters=[parameter("model", "Model", "model", "birefnet-general", options=BACKGROUND_MODELS)], capabilities=["onnx"], required_models=["rembg"], supports_preview=True, adapter="bg_remove"),
    node("midgard.image.low_light", "Fix Low Light", "Image/Enhance", "Restores a dark image with MIRNet.", icon="sun", inputs=[port("image", "Image", PortType.IMAGE, required=True)], outputs=[port("image", "Image", PortType.IMAGE)], parameters=[parameter("model", "Model", "model", "MIRNet_LOL", options=[option("MIRNet_LOL", "MIRNet LOL", "mirnet", "Low-light image restoration.")])], required_models=["mirnet"], supports_preview=True, adapter="low_light"),
    node("midgard.mask.select_object", "Select Object", "Mask/Selection", "Creates a mask from clicks or a text description.", icon="mouse-pointer-2", inputs=[port("image", "Image", PortType.IMAGE, required=True)], outputs=[port("mask", "Mask", PortType.MASK)], parameters=[parameter("text", "Object name", "text", ""), parameter("points", "Points", "json", []), parameter("moreComplex", "High quality", "boolean", False)], required_models=["sam2", "grounding-dino"], supports_preview=True, adapter="select_subject"),
    node("midgard.image.lama_retouch", "LaMa Retouch", "Image/Retouch", "Fills a masked region using the bundled LaMa model.", icon="paintbrush", inputs=[port("image", "Image", PortType.IMAGE, required=True), port("mask", "Mask", PortType.MASK, required=True)], outputs=[port("image", "Image", PortType.IMAGE)], required_models=["lama"], supports_preview=True, adapter="lama_retouch"),
    node("midgard.image.remove_text", "Remove Text from Image", "Image/Remove", "Detects and removes text from an image.", inputs=[port("image", "Image", PortType.IMAGE, required=True)], outputs=[port("image", "Image", PortType.IMAGE)], required_models=["paddleocr-server", "lama"], supports_preview=True, adapter="subtitle"),
    node("midgard.video.remove_text", "Remove Text from Video", "Video/Remove", "Removes subtitles or text while preserving source timing and audio.", icon="captions-off", inputs=[port("video", "Video", PortType.VIDEO, required=True)], outputs=[port("video", "Video", PortType.VIDEO)], required_models=["paddleocr-server", "sttn-auto"], supports_preview=True, adapter="subtitle"),
    node("midgard.output.preview_image", "Preview Image", "Output/Preview", "Shows the final image artifact on the node.", kind="output", icon="eye", inputs=[port("image", "Image", PortType.IMAGE, required=True)], outputs=[port("image", "Image", PortType.IMAGE)], supports_preview=True, adapter="passthrough"),
    node("midgard.output.preview_video", "Preview Video", "Output/Preview", "Shows a proxy video preview.", kind="output", icon="play", inputs=[port("video", "Video", PortType.VIDEO, required=True)], outputs=[port("video", "Video", PortType.VIDEO)], supports_preview=True, adapter="passthrough"),
    node("midgard.output.save_image", "Save Image", "Output/Save", "Copies an image artifact to a user-selected destination.", kind="output", icon="save", inputs=[port("image", "Image", PortType.IMAGE, required=True)], outputs=[port("image", "Saved Image", PortType.IMAGE)], parameters=[parameter("destinationGrantId", "Destination", "saveFile", "")], side_effects=True, cache_policy="none", adapter="save"),
    node("midgard.output.save_video", "Save Video", "Output/Save", "Copies a video artifact to a user-selected destination.", kind="output", icon="save", inputs=[port("video", "Video", PortType.VIDEO, required=True)], outputs=[port("video", "Saved Video", PortType.VIDEO)], parameters=[parameter("destinationGrantId", "Destination", "saveFile", "")], side_effects=True, cache_policy="none", adapter="save"),
]

NODE_REGISTRY = {definition.schema_id: definition for definition in _NODES}


def list_nodes() -> list[NodeDefinition]:
    return list(NODE_REGISTRY.values())


def get_node(schema_id: str) -> NodeDefinition:
    try:
        return NODE_REGISTRY[schema_id]
    except KeyError as exc:
        raise KeyError(f"Unknown node schema: {schema_id}") from exc
