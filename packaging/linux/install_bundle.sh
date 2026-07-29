#!/usr/bin/env bash
set -euo pipefail

source_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
state_home="${XDG_STATE_HOME:-$HOME/.local/state}"
install_root="$data_home/midgard/app"
desktop_dir="$data_home/applications"
log_dir="$state_home/midgard"
log_file="$log_dir/installer.log"

mkdir -p "$log_dir"
exec > >(tee -a "$log_file") 2>&1

progress() {
  local percent="$1"
  local message="$2"
  local filled=$((percent / 5))
  local empty=$((20 - filled))
  printf '\r['
  printf '%*s' "$filled" '' | tr ' ' '#'
  printf '%*s' "$empty" '' | tr ' ' '-'
  printf '] %3d%%  %s\n' "$percent" "$message"
}

echo "Midgard installer"
echo "Log: $log_file"
echo "Python 3.12 is embedded; system Python is not required."

progress 10 "Checking package"
if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "This package requires Linux x86-64." >&2
  exit 2
fi
if [[ ! -x "$source_dir/Midgard" ]]; then
  echo "Midgard executable is missing or is not executable." >&2
  exit 3
fi

progress 25 "Preparing per-user installation"
mkdir -p "$data_home/midgard" "$desktop_dir"
staging="$data_home/midgard/.app-install-$$"
backup="$data_home/midgard/.app-backup"
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging"

progress 45 "Copying application and embedded runtime"
cp -a "$source_dir/." "$staging/"
rm -f "$staging/install-midgard.sh" "$staging/INSTALL.txt"

progress 75 "Activating installation"
if [[ -d "$install_root" ]]; then
  rm -rf "$backup"
  mv "$install_root" "$backup"
fi
if ! mv "$staging" "$install_root"; then
  [[ ! -d "$backup" ]] || mv "$backup" "$install_root"
  echo "Installation failed; the previous version was restored." >&2
  exit 4
fi

progress 90 "Creating application menu entry"
cat > "$desktop_dir/midgard.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Midgard
Comment=Local AI image and video tools
Exec=$install_root/Midgard
Icon=$install_root/_internal/ui/icon/icon_1024.PNG
Terminal=false
Categories=Graphics;AudioVideo;
StartupNotify=true
EOF
chmod 0644 "$desktop_dir/midgard.desktop"

progress 100 "Installation complete"
echo "Application: $install_root/Midgard"
echo "Settings: ${XDG_CONFIG_HOME:-$HOME/.config}/midgard"
echo "Models: $data_home/midgard/models"

if [[ "${1:-}" != "--no-launch" ]]; then
  "$install_root/Midgard" >/dev/null 2>&1 &
fi
