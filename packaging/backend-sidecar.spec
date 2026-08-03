# -*- mode: python ; coding: utf-8 -*-
"""Frozen, windowless Python control-plane sidecar for Electron."""
from pathlib import Path
import sys
from PyInstaller.utils.hooks import can_import_module, collect_data_files, collect_submodules
ROOT = Path(SPECPATH).resolve().parent

def data(source, destination):
    return (str(source), destination)

datas = [data(ROOT / "backend/interface/en.ini", "backend/interface")]
release_metadata = ROOT / "build/release-metadata/midgard_release.json"
if release_metadata.is_file(): datas.append(data(release_metadata, "."))
for path in (ROOT / "backend/models/V5").rglob("*"):
    if path.is_file(): datas.append(data(path, str(path.parent.relative_to(ROOT))))
ffmpeg_roots = {"win32": ROOT / "backend/ffmpeg/win_x64", "darwin": ROOT / "backend/ffmpeg/macos", "linux": ROOT / "backend/ffmpeg/linux_x64"}
for path in ffmpeg_roots.get(sys.platform, ffmpeg_roots["linux"]).rglob("*"):
    if path.is_file(): datas.append(data(path, str(path.parent.relative_to(ROOT))))
for relative in (
    "backend/models/sttn-auto/infer_model.pth", "backend/models/sttn-det/sttn.pth",
    "backend/models/big-lama/fs_manifest.csv", "backend/models/propainter/fs_manifest.csv",
):
    source = ROOT / relative
    if source.is_file(): datas.append(data(source, str(source.parent.relative_to(ROOT))))
for package in ("rembg", "paddleocr"):
    if can_import_module(package): datas += collect_data_files(package)
hiddenimports = ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"]
if can_import_module("rembg.sessions"): hiddenimports += collect_submodules("rembg.sessions")
for package in ("diffusers", "accelerate", "transformers", "huggingface_hub", "torch_directml"):
    if can_import_module(package): hiddenimports += collect_submodules(package)
a = Analysis([str(ROOT / "midgard.py")], pathex=[str(ROOT)], binaries=[], datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["PySide6", "qfluentwidgets", "qframelesswindow", "tensorboard", "jupyter", "IPython", "pytest", "fastapi.testclient"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="midgard-backend", console=False, debug=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="midgard-backend")
