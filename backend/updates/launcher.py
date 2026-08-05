"""Start the platform installer after a verified release has been staged."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from backend.updates.downloader import PreparedUpdate


class UpdateLaunchError(RuntimeError):
    pass


def _linux_install_root() -> Path:
    executable = Path(sys.executable).resolve()
    return executable.parent


def _mac_app_root() -> Path:
    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.suffix == ".app":
            return parent
    raise UpdateLaunchError("Could not locate the running Lluna.app bundle.")


def _write_linux_updater(update: PreparedUpdate) -> Path:
    install_root = _linux_install_root()
    parent = install_root.parent
    script = update.path.parent / "apply-update.sh"
    q = shlex.quote
    content = f"""#!/bin/sh
set -eu
pid={os.getpid()}
while kill -0 "$pid" 2>/dev/null; do sleep 1; done
parent={q(str(parent))}
current={q(str(install_root))}
archive={q(str(update.path))}
staging="$parent/.lluna-update-{update.version}"
backup="$parent/.lluna-backup-{update.version}"
rm -rf "$staging"
mkdir -p "$staging"
tar -xzf "$archive" -C "$staging"
rm -rf "$backup"
mv "$current" "$backup"
if mv "$staging/Lluna" "$current"; then
  "$current/Lluna" >/dev/null 2>&1 &
else
  mv "$backup" "$current"
  exit 1
fi
"""
    script.write_text(content, encoding="utf-8")
    script.chmod(0o700)
    return script


def _write_macos_updater(update: PreparedUpdate) -> Path:
    app_root = _mac_app_root()
    parent = app_root.parent
    script = update.path.parent / "apply-update.sh"
    q = shlex.quote
    content = f"""#!/bin/sh
set -eu
pid={os.getpid()}
while kill -0 "$pid" 2>/dev/null; do sleep 1; done
current={q(str(app_root))}
dmg={q(str(update.path))}
parent={q(str(parent))}
mount="$(mktemp -d)"
staging="$parent/.Lluna-update-{update.version}.app"
backup="$parent/.Lluna-backup-{update.version}.app"
cleanup() {{ hdiutil detach "$mount" -quiet 2>/dev/null || true; rmdir "$mount" 2>/dev/null || true; }}
trap cleanup EXIT
hdiutil attach "$dmg" -nobrowse -readonly -mountpoint "$mount" -quiet
rm -rf "$staging"
ditto "$mount/Lluna.app" "$staging"
codesign --verify --deep --strict "$staging"
rm -rf "$backup"
mv "$current" "$backup"
if mv "$staging" "$current"; then
  open "$current"
else
  mv "$backup" "$current"
  exit 1
fi
"""
    script.write_text(content, encoding="utf-8")
    script.chmod(0o700)
    return script


def launch_prepared_update(update: PreparedUpdate) -> None:
    if not getattr(sys, "frozen", False):
        raise UpdateLaunchError("Binary updates are available only in packaged builds.")
    if update.target.platform == "windows":
        subprocess.Popen(
            [
                str(update.path),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/CLOSEAPPLICATIONS",
                "/RESTARTAPPLICATIONS",
            ],
            close_fds=True,
        )
        return
    script = (
        _write_macos_updater(update)
        if update.target.platform == "macos"
        else _write_linux_updater(update)
    )
    subprocess.Popen(
        ["/bin/sh", str(script)],
        start_new_session=True,
        close_fds=True,
    )
