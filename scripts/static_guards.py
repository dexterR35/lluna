#!/usr/bin/env python3
"""Fail CI when removed desktop stacks or forbidden UI frameworks return."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
errors=[]
production_python=[*(ROOT/"backend").rglob("*.py"),ROOT/"install.py",ROOT/"midgard.py",*(ROOT/"packaging").glob("*.py")]
removed_import=re.compile(r"^\s*(?:from|import)\s+(?:PySide6|PyQt\d*|qfluentwidgets|qframelesswindow|ui|backend\.config)\b",re.MULTILINE)
for path in production_python:
    if "scenedetect" in path.parts: continue
    text=path.read_text(encoding="utf-8",errors="replace")
    if removed_import.search(text): errors.append(f"Removed GUI import: {path.relative_to(ROOT)}")
for removed in ("gui.py","ui","run_gui.sh","run_gui.bat"):
    if (ROOT/removed).exists(): errors.append(f"Legacy desktop path exists: {removed}")
packages=json.loads((ROOT/"frontend"/"package.json").read_text(encoding="utf-8"))
all_dependencies={**packages.get("dependencies",{}),**packages.get("devDependencies",{})}
for forbidden in ("@chakra-ui/react","@mui/material","@mantine/core","@radix-ui/react-dialog","bootstrap","antd","primereact","@fluentui/react","styled-components","@emotion/react"):
    if forbidden in all_dependencies: errors.append(f"Forbidden UI framework dependency: {forbidden}")
for source in (ROOT/"frontend"/"src").rglob("*"):
    if source.is_file() and source.suffix not in {".js",".jsx",".css"}: errors.append(f"Frontend application source must be JS/JSX/CSS: {source.relative_to(ROOT)}")
if errors:
    print("\n".join(errors),file=sys.stderr);raise SystemExit(1)
print("Static desktop guards passed: Electron-only, Qt-free Python, no forbidden UI framework.")
