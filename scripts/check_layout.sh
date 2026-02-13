#!/usr/bin/env bash
set -euo pipefail

required_files=(
  "workflows/cinematic_wallpaper.choom"
  "workflows/anime_poster.choom"
  "workflows/photo_real_portrait.choom"
  "workflows/wallpaper_pack_fast.choom"
  "workflows/wallpaper_pack_hd.choom"
  "apps/wallpaper/inputs/themes.json"
)

missing=0
for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required file: $file"
    missing=1
  fi
done

if [[ $missing -ne 0 ]]; then
  echo "Layout check failed. Restore required files before running Choom commands."
  exit 1
fi

echo "Layout check passed. Canonical runnable scripts are in workflows/."
