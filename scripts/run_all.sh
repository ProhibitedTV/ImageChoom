#!/usr/bin/env bash
set -euo pipefail

scripts/check_layout.sh

choom run workflows/cinematic_wallpaper.choom --timeout 180
choom run workflows/anime_poster.choom --timeout 180
choom run workflows/photo_real_portrait.choom --timeout 180
choom run workflows/wallpaper_pack_fast.choom --timeout 180
choom run workflows/wallpaper_pack_hd.choom --timeout 180

echo "All ImageChoom workflows completed. Check outputs/."
