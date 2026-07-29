# -*- mode: python ; coding: utf-8 -*-
"""Portable onedir package; user-installed optional models are not bundled."""

from pathlib import Path
import sys

from PyInstaller.utils.hooks import (
    can_import_module,
    collect_data_files,
    collect_submodules,
)

ROOT = Path(SPECPATH).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.core.build_info import VERSION


def data_file(source, destination):
    return (str(source), destination)


datas = [
    data_file(ROOT / "backend/interface/en.ini", "backend/interface"),
    data_file(ROOT / "ui/icon/icon_48.png", "ui/icon"),
    data_file(ROOT / "ui/icon/icon_1024.PNG", "ui/icon"),
]
release_metadata = ROOT / "build/release-metadata/midgard_release.json"
if release_metadata.is_file():
    datas.append(data_file(release_metadata, "."))
if sys.platform.startswith("linux"):
    datas.append(
        data_file(
            ROOT / "packaging/linux/midgard.desktop",
            "share/applications",
        )
    )

# Only repository-shipped core artifacts are bundled. In particular, never
# sweep backend/models recursively: that directory may contain multi-GB user
# downloads which are deliberately excluded from release artifacts.
for path in (ROOT / "backend/models/V5").rglob("*"):
    if path.is_file():
        datas.append(data_file(path, str(path.parent.relative_to(ROOT))))
for relative in (
    "backend/models/sttn-auto/infer_model.pth",
    "backend/models/sttn-det/sttn.pth",
    "backend/models/big-lama/fs_manifest.csv",
    "backend/models/big-lama/big-lama_1.pt",
    "backend/models/big-lama/big-lama_2.pt",
    "backend/models/big-lama/big-lama_3.pt",
    "backend/models/big-lama/big-lama_4.pt",
    "backend/models/big-lama/big-lama_5.pt",
    "backend/models/propainter/fs_manifest.csv",
    "backend/models/propainter/ProPainter_1.pth",
    "backend/models/propainter/ProPainter_2.pth",
    "backend/models/propainter/ProPainter_3.pth",
    "backend/models/propainter/ProPainter_4.pth",
    "backend/models/propainter/raft-things.pth",
    "backend/models/propainter/recurrent_flow_completion.pth",
):
    source = ROOT / relative
    if source.is_file():
        datas.append(data_file(source, str(source.parent.relative_to(ROOT))))

ffmpeg_by_platform = {
    "win32": ROOT / "backend/ffmpeg/win_x64",
    "darwin": ROOT / "backend/ffmpeg/macos",
    "linux": ROOT / "backend/ffmpeg/linux_x64",
}
ffmpeg_root = ffmpeg_by_platform.get(sys.platform)
if ffmpeg_root:
    for path in ffmpeg_root.rglob("*"):
        if path.is_file():
            datas.append(data_file(path, str(path.parent.relative_to(ROOT))))

for package in ("qfluentwidgets", "qframelesswindow", "rembg", "paddleocr"):
    if can_import_module(package):
        datas += collect_data_files(package)

hiddenimports = []
for package in (
    "qfluentwidgets",
    "qframelesswindow",
    "showinfm",
    "rembg.sessions",
):
    if can_import_module(package):
        hiddenimports += collect_submodules(package)
for optional in (
    "diffusers",
    "accelerate",
    "transformers",
    "huggingface_hub",
    "torch_directml",
):
    if can_import_module(optional):
        hiddenimports += collect_submodules(optional)

a = Analysis(
    [str(ROOT / "midgard.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tensorboard", "jupyter", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Midgard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Midgard",
)
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Midgard.app",
        bundle_identifier="studio.midgard.desktop",
        info_plist={
            "CFBundleDisplayName": "Midgard",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
