# -*- mode: python ; coding: utf-8 -*-
"""Frozen, windowless Python control-plane sidecar for Electron."""
from pathlib import Path
import sys
from PyInstaller.utils.hooks import can_import_module, collect_data_files, collect_submodules
ROOT = Path(SPECPATH).resolve().parent

def data(source, destination):
    return (str(source), destination)

datas = []
release_metadata = ROOT / "build/release-metadata/lluna_release.json"
if release_metadata.is_file(): datas.append(data(release_metadata, "."))
for path in (ROOT / "backend/models/V5").rglob("*"):
    if path.is_file(): datas.append(data(path, str(path.parent.relative_to(ROOT))))
for path in (ROOT / "backend/ai/seedvr2").rglob("*"):
    if path.is_file(): datas.append(data(path, str(path.parent.relative_to(ROOT))))
ffmpeg_roots = {"win32": ROOT / "backend/ffmpeg/win_x64", "darwin": ROOT / "backend/ffmpeg/macos", "linux": ROOT / "backend/ffmpeg/linux_x64"}
for path in ffmpeg_roots.get(sys.platform, ffmpeg_roots["linux"]).rglob("*"):
    if path.is_file(): datas.append(data(path, str(path.parent.relative_to(ROOT))))
for relative in (
    "backend/models/sttn-auto/infer_model.pth", "backend/models/sttn-det/sttn.pth",
    # big-lama.pt/ProPainter.pth are gitignored and only ever exist as their
    # split *_N.pt(h) parts plus fs_manifest.csv (see .gitignore and
    # backend/tools/media/common.py::merge_big_file_if_not_exists, which
    # reconstructs the merged file from these parts at runtime) - bundling
    # only the manifest without the parts it lists leaves the reconstruction
    # silently unable to run in a packaged build.
    "backend/models/big-lama/fs_manifest.csv",
    "backend/models/big-lama/big-lama_1.pt", "backend/models/big-lama/big-lama_2.pt",
    "backend/models/big-lama/big-lama_3.pt", "backend/models/big-lama/big-lama_4.pt",
    "backend/models/big-lama/big-lama_5.pt",
    "backend/models/propainter/fs_manifest.csv",
    "backend/models/propainter/ProPainter_1.pth", "backend/models/propainter/ProPainter_2.pth",
    "backend/models/propainter/ProPainter_3.pth", "backend/models/propainter/ProPainter_4.pth",
    "backend/models/propainter/raft-things.pth", "backend/models/propainter/recurrent_flow_completion.pth",
    # Subprocess runner scripts for isolated model runtimes (SUPIR, BiRefNet):
    # invoked by their bridge modules via a real file path in the isolated
    # venv, not imported, so PyInstaller's bytecode freezing doesn't cover
    # them - they must be bundled as plain data files at the destination
    # their bridge module's __file__.with_name(...) expects.
    "backend/ai/runtimes/supir_process.py",
    "backend/ai/runtimes/birefnet_process.py",
):
    source = ROOT / relative
    if source.is_file(): datas.append(data(source, str(source.parent.relative_to(ROOT))))
for package in ("paddleocr",):
    if can_import_module(package): datas += collect_data_files(package)
hiddenimports = ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"]
for package in ("diffusers", "accelerate", "transformers", "huggingface_hub", "torch_directml", "keyring"):
    if can_import_module(package): hiddenimports += collect_submodules(package)
a = Analysis([str(ROOT / "lluna.py")], pathex=[str(ROOT)], binaries=[], datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["PySide6", "qfluentwidgets", "qframelesswindow", "tensorboard", "jupyter", "IPython", "pytest", "fastapi.testclient"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lluna-backend", console=False, debug=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="lluna-backend")
