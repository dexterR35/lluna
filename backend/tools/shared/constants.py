from enum import Enum, unique


@unique
class InpaintMode(Enum):
    """
    Image inpainting algorithm enum
    """

    STTN_AUTO = "sttn-auto"
    STTN_DET = "sttn-det"
    LAMA = "lama"
    PROPAINTER = "propainter"


@unique
class SubtitleDetectMode(Enum):
    """
    Subtitle detection algorithm enum
    """

    PP_OCRv5_MOBILE = "PP_OCRv5_MOBILE"
    PP_OCRv5_SERVER = "PP_OCRv5_SERVER"


@unique
class EnhanceMode(Enum):
    """Real-ESRGAN upscale models for Remove BG Enhance."""

    X2PLUS = "RealESRGAN_x2plus"
    X4PLUS = "RealESRGAN_x4plus"


@unique
class LowLightMode(Enum):
    """MIRNet low-light enhancement (PyTorch, same-size restore)."""

    MIRNET_LOL = "MIRNet_LOL"


@unique
class GenerateMode(Enum):
    """Text-to-image models loaded locally through Diffusers."""

    FLUX2_KLEIN_4B = "FLUX.2-klein-4B"
    FLUX2_KLEIN_9B = "FLUX.2-klein-9B"
    FLUX2_KLEIN_BASE_4B = "FLUX.2-klein-base-4B"
    FLUX2_KLEIN_BASE_9B = "FLUX.2-klein-base-9B"
    FLUX2_DEV = "FLUX.2-dev"
    FLUX2_KLEIN_9B_FP8 = "FLUX.2-klein-9b-fp8"
    QWEN_IMAGE = "Qwen-Image"


@unique
class DenoiseStrength(Enum):
    """Safe denoise strength before Real-ESRGAN (restoration-only, no upscale)."""

    SAFE = "safe"
    MEDIUM = "medium"
