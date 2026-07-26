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
    OPENCV = "opencv"

@unique
class SubtitleDetectMode(Enum):
    """
    Subtitle detection algorithm enum
    """
    PP_OCRv5_MOBILE = "PP_OCRv5_MOBILE"
    PP_OCRv5_SERVER = "PP_OCRv5_SERVER"


@unique
class BgRemoveMode(Enum):
    """
    Image-only background-removal models (rembg / ONNX).
    Includes large high-quality models (BiRefNet family, BRIA, IS-Net).
    """
    # Fast / classic
    U2NET = "u2net"
    U2NETP = "u2netp"
    U2NET_HUMAN = "u2net_human_seg"
    U2NET_CLOTH = "u2net_cloth_seg"
    SILUETA = "silueta"
    # Strong general
    ISNET = "isnet-general-use"
    ISNET_ANIME = "isnet-anime"
    # Large / best quality
    BIREFNET = "birefnet-general"
    BIREFNET_LITE = "birefnet-general-lite"
    BIREFNET_PORTRAIT = "birefnet-portrait"
    BIREFNET_MASSIVE = "birefnet-massive"
    BIREFNET_DIS = "birefnet-dis"
    BIREFNET_HRSOD = "birefnet-hrsod"
    BIREFNET_COD = "birefnet-cod"
    BRIA_RMBG = "bria-rmbg"


@unique
class EnhanceMode(Enum):
    """Real-ESRGAN upscale models for Remove BG Enhance."""

    X2PLUS = "RealESRGAN_x2plus"
    X4PLUS = "RealESRGAN_x4plus"
