#!/usr/bin/env bash
set -euo pipefail

version="${1:?version is required}"
profile="${2:-mps}"
architecture="${3:-x64}"
app_path="${4:-dist/Midgard.app}"
output_dir="${5:-release}"

if [[ ! -d "$app_path" ]]; then
  echo "Missing app bundle: $app_path" >&2
  exit 1
fi

mkdir -p "$output_dir"
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
cp -R "$app_path" "$staging/Midgard.app"
cp "$(dirname -- "$0")/INSTALL.txt" "$staging/Read Me.txt"
ln -s /Applications "$staging/Applications"

output="$output_dir/Midgard-$version-macos-$architecture-$profile.dmg"
hdiutil create \
  -volname "Midgard $version" \
  -srcfolder "$staging" \
  -ov \
  -format UDZO \
  "$output"
echo "$output"
