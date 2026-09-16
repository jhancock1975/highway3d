#!/usr/bin/env bash
# Fetch everything toon.py needs: Blender, ffmpeg, and the CC0 vehicle models.
# Safe to re-run; skips whatever is already present.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSETS="$(cd "$HERE/.." && pwd)/assets"
CARS="$ASSETS/cars"

say() { printf '==> %s\n' "$*"; }

install_tool() {
  local tool=$1 cask=$2
  if command -v "$tool" >/dev/null 2>&1; then
    say "$tool already installed: $(command -v "$tool")"
    return
  fi
  if command -v brew >/dev/null 2>&1; then
    say "installing $tool via Homebrew"
    if [ "$cask" = "cask" ]; then brew install --cask "$tool"; else brew install "$tool"; fi
  else
    echo "$tool missing and Homebrew not found. Install $tool manually." >&2
    exit 1
  fi
}

install_tool blender cask
install_tool ffmpeg formula

# --- CC0 vehicles: Kenney Car Kit (public domain, attribution appreciated)
mkdir -p "$CARS"
if [ -d "$CARS/kenney/Models/GLB format" ]; then
  say "car models already present"
else
  say "downloading Kenney Car Kit (CC0)"
  URL=$(curl -s --max-time 30 https://kenney.nl/assets/car-kit \
        | grep -oiE 'https?://[^"]*kenney_car-kit\.zip' | head -1)
  if [ -z "${URL:-}" ]; then
    echo "could not find the Car Kit download link; grab it from" >&2
    echo "  https://kenney.nl/assets/car-kit" >&2
    echo "and unzip into $CARS/kenney" >&2
    exit 1
  fi
  curl -sL --max-time 300 -o "$CARS/kenney_car-kit.zip" "$URL"
  unzip -oq "$CARS/kenney_car-kit.zip" -d "$CARS/kenney"
  rm -f "$CARS/kenney_car-kit.zip"
fi

COUNT=$(find "$CARS/kenney" -iname '*.glb' 2>/dev/null | wc -l | tr -d ' ')
say "car models: $COUNT"
[ "$COUNT" -ge 20 ] || { echo "expected at least 20 GLB models" >&2; exit 1; }

say "verifying Blender can render headless"
python3 "$HERE/toon.py" preview --out /tmp/toon_setup_check.png --at 6 \
  --width 480 --height 270 --samples 8 >/dev/null
say "ok -- wrote /tmp/toon_setup_check.png"
say "ready: python3 $HERE/toon.py describe"
