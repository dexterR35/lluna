#!/usr/bin/env python3
"""Build the frozen Python sidecar and Electron desktop distributable."""
from __future__ import annotations
import argparse, importlib.util, json, platform, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"packaging"/"backend-sidecar.spec"
REQUIRED=(ROOT/"midgard.py", ROOT/"frontend"/"forge.config.js", ROOT/"package-lock.json", ROOT/"backend"/"interface"/"en.ini")
def validate_repository(strict_python=True):
    errors=[]
    if strict_python and sys.version_info[:2] != (3,12): errors.append(f"Python 3.12 is required; received {sys.version_info.major}.{sys.version_info.minor}.")
    for path in REQUIRED:
        if not path.is_file(): errors.append(f"Required packaging resource is missing: {path}")
    if not SPEC.is_file(): errors.append(f"Sidecar specification is missing: {SPEC}")
    if shutil.which("npm") is None: errors.append("Node.js/npm is required for Electron packaging.")
    return tuple(errors)
def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument("--validate-only",action="store_true");parser.add_argument("--clean",action="store_true");parser.add_argument("--sidecar-only",action="store_true");parser.add_argument("--profile",choices=["cpu","cuda","directml","mps"],default="cpu");parser.add_argument("--architecture",default="x64");args=parser.parse_args(argv)
    errors=validate_repository(strict_python=not args.validate_only)
    if errors:
        for error in errors: print(f"ERROR: {error}",file=sys.stderr)
        return 1
    if args.validate_only: print("Electron packaging inputs are valid.");return 0
    if importlib.util.find_spec("PyInstaller") is None: print("ERROR: Install requirements-packaging.txt.",file=sys.stderr);return 1
    platform_name="windows" if sys.platform=="win32" else "macos" if sys.platform=="darwin" else "linux"
    metadata=ROOT/"build"/"release-metadata"/"midgard_release.json";metadata.parent.mkdir(parents=True,exist_ok=True);metadata.write_text(json.dumps({"platform":platform_name,"architecture":args.architecture,"profile":args.profile},indent=2)+"\n",encoding="utf-8")
    command=[sys.executable,"-m","PyInstaller","--noconfirm","--distpath",str(ROOT/"build"/"backend-sidecar"),"--workpath",str(ROOT/"build"/"pyinstaller"),str(SPEC)]
    if args.clean: command.insert(3,"--clean")
    code=subprocess.call(command,cwd=ROOT)
    if code or args.sidecar_only:return code
    return subprocess.call(["npm","run","make"],cwd=ROOT)
if __name__=="__main__":raise SystemExit(main())
