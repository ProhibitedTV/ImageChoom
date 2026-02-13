#!/usr/bin/env bash
set -euo pipefail

choom run workflows/cinematic_wallpaper.choom --timeout 180
choom run workflows/anime_poster.choom --timeout 180
choom run workflows/photo_real_portrait.choom --timeout 180

echo "All ImageChoom workflows completed. Check outputs/."
