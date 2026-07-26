import os
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path

# qfluentwidgets prints a Pro promo tip on import - silence it
_qfw_stdout = StringIO()
with redirect_stdout(_qfw_stdout):
    from qfluentwidgets import (qconfig, ConfigItem, QConfig, OptionsValidator, BoolValidator, OptionsConfigItem,
                                EnumSerializer, RangeValidator, RangeConfigItem, ConfigValidator, Theme)
from backend.tools.constant import (
    InpaintMode,
    SubtitleDetectMode,
    BgRemoveMode,
    EnhanceMode,
    DenoiseStrength,
    LowLightMode,
    GenerateMode,
)
import configparser

# Project version
VERSION = "1.4.0"
PROJECT_HOME_URL = "https://github.com/midgard-app/midgard"
PROJECT_ISSUES_URL = PROJECT_HOME_URL + "/issues"
PROJECT_RELEASES_URL = PROJECT_HOME_URL + "/releases"
PROJECT_UPDATE_URLS = [
    "https://api.github.com/repos/midgard-app/midgard/releases/latest",
]

# Hardware acceleration master switch
HARDWARE_ACCELERATION_OPTION = True

# Groups never written to config.json (hardcoded every launch)
_EPHEMERAL_CONFIG_GROUPS = frozenset({"UI", "Window", "QFluentWidgets"})


class Config(QConfig):
    # Window size - fixed default, always centered (not persisted)
    windowW = 1280
    windowH = 750

    # Window / dialog sizes (not theme chrome)
    retouchWindowW = 1200
    retouchWindowH = 800
    videoPreviewWidth = 960
    videoPreviewWidthCompact = 640

    # UI behavior
    navCollapsible = False
    navReturnButtonVisible = False
    micaEnabled = False
    updateCheckDelayMs = 2000
    infoBarDurationMs = 3000
    restartTooltipDurationMs = 5000
    retouchProgressHideMs = 900

    # Zoom / preview rendering (Photoshop-like viewport over full-res pixels)
    minZoom = 0.05   # 5% - zoom out
    maxZoom = 8.0    # 800% - zoom in
    zoomStep = 1.25
    # 0 = original image size (no downsample). Applies to all previews/dialogs.
    previewMaxSide = 0
    retouchPreviewMaxSide = 0
    checkerboardTile = 12
    selectionEdgeSize = 10

    # Retouch canvas
    retouchMaxHistory = 40
    retouchMaskOverlayAlpha = 170
    retouchSelectionOverlayAlpha = 90
    retouchPenCloseRadius = 8
    # Coalesce paint/lasso viewport rebuilds while dragging (ms); 0 = every event
    retouchPaintRefreshMs = 16

    # Single config item storing all selection areas
    # Default is one area; format: "ymin,ymax,xmin,xmax;ymin,ymax,xmin,xmax;..."
    # Areas are separated by semicolons
    subtitleSelectionAreas = ConfigItem("Main", "SubtitleSelectionAreas", "0.88,0.99,0.15,0.85")

    """
    Available inpaint algorithm modes:
    - InpaintMode.STTN_AUTO: Smart erase variant
    - InpaintMode.STTN_DET: With subtitle detection, no smart erase
    - InpaintMode.LAMA: Works well on animated videos; moderate speed; cannot skip subtitle detection
    - InpaintMode.PROPAINTER: High VRAM usage; slower; better for videos with very intense motion
    """
    # Inpaint algorithm - STTN Smart Inpainting is the first-install / factory default
    inpaintMode = OptionsConfigItem("Main", "InpaintMode", InpaintMode.STTN_AUTO, OptionsValidator(InpaintMode), EnumSerializer(InpaintMode))
    
    subtitleDetectMode =  OptionsConfigItem("Main", "SubtitleDetectMode", SubtitleDetectMode.PP_OCRv5_SERVER, OptionsValidator(SubtitleDetectMode), EnumSerializer(SubtitleDetectMode))

    # Background removal model (images only; separate from inpaint)
    # BiRefNet General is the default high-quality cutout model
    bgRemoveMode = OptionsConfigItem(
        "BgRemove",
        "Mode",
        BgRemoveMode.BIREFNET,
        OptionsValidator(BgRemoveMode),
        EnumSerializer(BgRemoveMode),
    )
    # Comma-separated rembg model ids that are On (appear in Run dropdown when installed)
    bgRemoveEnabledModels = ConfigItem(
        "BgRemove",
        "EnabledModels",
        "birefnet-general,u2net_human_seg,isnet-anime,u2net_cloth_seg",
        ConfigValidator(),
    )

    # Real-ESRGAN enhance (Remove BG) - x2plus default; x4plus opt-in via Settings
    enhanceMode = OptionsConfigItem(
        "Enhance",
        "Mode",
        EnhanceMode.X2PLUS,
        OptionsValidator(EnhanceMode),
        EnumSerializer(EnhanceMode),
    )
    enhanceEnabledModels = ConfigItem(
        "Enhance",
        "EnabledModels",
        "RealESRGAN_x2plus",
        ConfigValidator(),
    )
    enhanceMaxLongEdge = ConfigItem("Enhance", "MaxLongEdge", 5000)
    enhanceDenoiseEnabled = ConfigItem("Enhance", "DenoiseEnabled", False, BoolValidator())
    enhanceDenoiseStrength = OptionsConfigItem(
        "Enhance",
        "DenoiseStrength",
        DenoiseStrength.SAFE,
        OptionsValidator(DenoiseStrength),
        EnumSerializer(DenoiseStrength),
    )

    # MIRNet low-light enhance (dedicated Low Light page)
    lowLightMode = OptionsConfigItem(
        "LowLight",
        "Mode",
        LowLightMode.MIRNET_LOL,
        OptionsValidator(LowLightMode),
        EnumSerializer(LowLightMode),
    )
    lowLightEnabledModels = ConfigItem(
        "LowLight",
        "EnabledModels",
        "MIRNet_LOL",
        ConfigValidator(),
    )
    lowLightMaxLongEdge = ConfigItem("LowLight", "MaxLongEdge", 2048)

    # FLUX.2 text-to-image (Home dashboard Generate) — Settings install / On / Off
    generateMode = OptionsConfigItem(
        "Generate",
        "Mode",
        GenerateMode.FLUX2_KLEIN_4B,
        OptionsValidator(GenerateMode),
        EnumSerializer(GenerateMode),
    )
    # Empty until Install (large weights; nothing On by default)
    generateEnabledModels = ConfigItem(
        "Generate",
        "EnabledModels",
        "__none__",
        ConfigValidator(),
    )
    generateWidth = ConfigItem("Generate", "Width", 1024)
    generateHeight = ConfigItem("Generate", "Height", 1024)
    generateSteps = ConfigItem("Generate", "Steps", 4)

    # Select Object (SAM2 + Grounding DINO) - hidden pair; More complex in Settings
    selectObjectMoreComplex = ConfigItem(
        "SelectObject",
        "MoreComplex",
        False,
        BoolValidator(),
    )

    # Shared inference worker
    jobWatchdogSec = ConfigItem("Infer", "JobWatchdogSec", 90)
    inferIdleReleaseSec = ConfigItem("Infer", "IdleReleaseSec", 60)
    # Soft defaults applied once when still at factory values (see soft_defaults.py)
    softDefaultsApplied = ConfigItem("Infer", "SoftDefaultsApplied", False, BoolValidator())

    # Pixel tolerance settings
    # Used to detect false non-subtitle regions (subtitle boxes are usually wider than tall;
    # if height exceeds width by more than this many pixels, treat as a false detection)
    subtitleYXAxisDifferencePixel = RangeConfigItem("Main", "SubtitleYXAxisDifferencePixel", 10, RangeValidator(0, 300))
    # Expand mask size so auto-detected boxes are not too small and leave text edges/residue during inpaint
    subtitleAreaDeviationPixel = RangeConfigItem("Main", "SubtitleAreaDeviationPixel", 10, RangeValidator(1, 300))
    # Used to decide whether two text boxes are on the same subtitle line (within this height difference)
    subtitleAreaYAxisDifferencePixel = RangeConfigItem("Main", "SubtitleAreaYAxisDifferencePixel", 20, RangeValidator(0, 300))
    # Used to decide whether two subtitle boxes are similar; if X and Y deviations are within thresholds, treat as the same box
    subtitleAreaPixelToleranceYPixel = RangeConfigItem("Main", "SubtitleAreaPixelToleranceYPixel", 20, RangeValidator(0, 300))
    subtitleAreaPixelToleranceXPixel = RangeConfigItem("Main", "SubtitleAreaPixelToleranceXPixel", 20, RangeValidator(0, 300))
    subtitleTimelineBackwardFrameCount = RangeConfigItem("Main", "SubtitleTimelineBackwardFrameCount", 3, RangeValidator(0, 300))
    subtitleTimelineForwardFrameCount = RangeConfigItem("Main", "SubtitleTimelineForwardFrameCount", 3, RangeValidator(0, 300))
    # The following parameters only apply when using the STTN algorithm
    """
    1. STTN_SKIP_DETECTION
    Meaning: Whether to skip detection
    Effect: Setting True skips subtitle detection and saves a lot of time, but may incorrectly process
            frames without subtitles or miss some subtitles to remove

    2. STTN_NEIGHBOR_STRIDE
    Meaning: Neighbor frame stride. To fill missing regions in frame 50 with STTN_NEIGHBOR_STRIDE=5,
             the algorithm uses frames 45, 40, etc. as references.
    Effect: Controls density of reference frame selection; larger stride uses fewer, more sparse
            references; smaller stride uses more, denser references.

    3. STTN_REFERENCE_LENGTH
    Meaning: Number of reference frames; STTN looks at several frames before/after each frame to repair for context
    Effect: Increasing this uses more VRAM and improves quality, but slows processing

    4. STTN_MAX_LOAD_NUM
    Meaning: Maximum number of video frames STTN loads at once
    Effect: Larger values are slower but look better
    Note: STTN_MAX_LOAD_NUM must be greater than STTN_NEIGHBOR_STRIDE and STTN_REFERENCE_LENGTH
    """
    # Reference frame stride
    sttnNeighborStride = RangeConfigItem("Sttn", "NeighborStride", 5, RangeValidator(1, 100))
    # Number of reference frames
    sttnReferenceLength = RangeConfigItem("Sttn", "ReferenceLength", 10, RangeValidator(1, 100))
    # Maximum number of frames STTN processes at once
    sttnMaxLoadNum = RangeConfigItem("Sttn", "MaxLoadNum", 50, RangeValidator(1, 300))
    getSttnMaxLoadNum = lambda self: max(self.sttnMaxLoadNum.value, self.sttnNeighborStride.value * self.sttnReferenceLength.value)
    
    # The following parameters only apply when using the PROPAINTER algorithm
    # Set based on your GPU VRAM: larger max concurrent images improve quality but need more VRAM
    # For 1280x720p: 80 needs ~25GB VRAM, 50 needs ~19GB
    # For 720x480p: 80 needs ~8GB VRAM, 50 needs ~7GB
    propainterMaxLoadNum = RangeConfigItem("ProPainter", "MaxLoadNum", 70, RangeValidator(1, 300))

    # Whether to use hardware acceleration
    hardwareAcceleration = ConfigItem("Main", "HardwareAcceleration", HARDWARE_ACCELERATION_OPTION, BoolValidator())
    
    # Check for app updates on startup
    checkUpdateOnStartup = ConfigItem("Main", "CheckUpdateOnStartup", True, BoolValidator())

    # Video save directory
    saveDirectory = ConfigItem("Main", "SaveDirectory", "", ConfigValidator())

    def toDict(self, serialize=True):
        """Persist only functional settings - skip theme / UI / window geometry."""
        items = super().toDict(serialize=serialize)
        for group in _EPHEMERAL_CONFIG_GROUPS:
            items.pop(group, None)
        return items


CONFIG_FILE = 'config/config.json'
config = Config()
qconfig.load(CONFIG_FILE, config)

# Theme is hardcoded in ui.theme - keep in memory only, never from/to JSON
qconfig.set(config.themeMode, Theme.DARK, save=False)

# No %-interpolation - UI strings may contain "100%" etc.
tr = configparser.ConfigParser(interpolation=None)
TRANSLATION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'interface', 'en.ini')
tr.read(TRANSLATION_FILE, encoding='utf-8')

# Project base directory
BASE_DIR = str(Path(os.path.abspath(__file__)).parent)

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
