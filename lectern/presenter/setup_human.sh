#!/usr/bin/env bash
# Fetch and install everything presenter/human.py builds the professor from.
#
#   MPFB 2.0.17 (MakeHuman Plugin For Blender, GPL-3.0; the GPL covers the
#   add-on, not what is rendered with it) plus the MakeHuman asset packs it
#   dresses him in. Everything goes into a project-local Blender user
#   directory, lectern/.blender, so the user's own Blender prefs are never
#   touched. Run human.py with the same BLENDER_USER_RESOURCES.
#
# Every download is pinned by sha256. A zip that does not match is deleted
# and the script stops -- a changed upstream asset changes the character.
#
#   lectern/presenter/setup_human.sh            # install
#   ASSET_CACHE=/some/dir setup_human.sh        # reuse zips already downloaded
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LECTERN="$(dirname "$HERE")"
export BLENDER_USER_RESOURCES="${BLENDER_USER_RESOURCES:-$LECTERN/.blender}"
BLENDER="${BLENDER:-$(command -v blender || echo /opt/homebrew/bin/blender)}"
DL="$BLENDER_USER_RESOURCES/downloads"
DATA="$BLENDER_USER_RESOURCES/extensions/.user/user_default/mpfb/data"
mkdir -p "$DL"

EXT=https://extensions.blender.org/download
MH=https://files.makehumancommunity.org

# name | url | sha256 | licence
MANIFEST="
mpfb-v2.0.17.zip|$EXT/sha256:4f0a879d64a39bf646fbf5f53601ac678855da329d650617dca5737548239a87/add-on-mpfb-v2.0.17.zip|4f0a879d64a39bf646fbf5f53601ac678855da329d650617dca5737548239a87|GPL-3.0
makehuman_system_assets_cc0.zip|$MH/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip|b542127a8e25547c7c29c19f2d1d2adb9a664c80396ecd694095dbc8028a0107|CC0
visemes02.zip|$MH/functional/visemes02.zip|a69ab6fb95ddd5f56f70acc7e859f5f9c6ae613c527d577ea1571eff2183d29e|CC0
faceunits01.zip|$MH/functional/faceunits01.zip|d113107bd7eb59f3af4df6fc0ec29bfcc593f496d0b336aec14f086a80ce7146|CC0
shirts02_ccby.zip|$MH/asset_packs/shirts02/shirts02_ccby.zip|d711ca9f73212de855257ac08422e1e0ccb802e5231315c2a360d0fcfea5033e|CC-BY
pants01_cc0.zip|$MH/asset_packs/pants01/pants01_cc0.zip|e4e0ec60db34f279be291a83cfd7b342a7c5cf09bb7676682a5f39f4f6ac4ad9|CC0
pants02_ccby.zip|$MH/asset_packs/pants02/pants02_ccby.zip|9dbcd65e03ab100977079b6960e91c334bed92e948aeda5423f11997a133904a|CC-BY
shoes02_ccby.zip|$MH/asset_packs/shoes02/shoes02_ccby.zip|1b544d87dd8b3d3a9c8317e4f059be456491be979cbc9984fc53f403046f5061|CC-BY
skins02_cc0.zip|$MH/asset_packs/skins02/skins02_cc0.zip|1613f1ef3afca53094511d26620ed7cf1d2dedc29ed3d384d60bdebe250698ae|CC0
bodyparts05_cc0.zip|$MH/asset_packs/bodyparts05/bodyparts05_cc0.zip|262bba42246f85b2a91f493dd920296b258a3b4544eb495c91c4d08e57c528fd|CC0
eyebrows01_cc0.zip|$MH/asset_packs/eyebrows01/eyebrows01_cc0.zip|5425891dce613bef85c7117f7843cd49d57d1fb28127e76d77d2a2eaccb4fe78|CC0
"

sha() { shasum -a 256 "$1" | cut -d' ' -f1; }

fetch() {  # name url sha
  local name=$1 url=$2 want=$3 dst="$DL/$1"
  if [[ -f "$dst" && "$(sha "$dst")" == "$want" ]]; then return; fi
  if [[ -n "${ASSET_CACHE:-}" && -f "$ASSET_CACHE/$name" ]]; then
    cp "$ASSET_CACHE/$name" "$dst"
  else
    echo "fetching $name"
    curl --connect-timeout 10 --max-time 1800 -fsSL -o "$dst.part" "$url"
    mv "$dst.part" "$dst"
  fi
  local got; got="$(sha "$dst")"
  if [[ "$got" != "$want" ]]; then
    rm -f "$dst"
    echo "sha256 mismatch for $name: got $got want $want" >&2
    exit 1
  fi
}

while IFS='|' read -r name url want lic; do
  [[ -z "$name" ]] && continue
  fetch "$name" "$url" "$want"
done <<< "$MANIFEST"

# the add-on
if [[ ! -f "$BLENDER_USER_RESOURCES/extensions/user_default/mpfb/blender_manifest.toml" ]]; then
  "$BLENDER" --background --factory-startup --command extension install-file \
    -r user_default -e "$DL/mpfb-v2.0.17.zip"
fi

# the packs: MPFB's own "load pack" operator is nothing more than an unzip
# into its user data directory
mkdir -p "$DATA"
while IFS='|' read -r name url want lic; do
  [[ -z "$name" || "$name" == mpfb-* ]] && continue
  stamp="$DATA/.installed-$name-$want"
  [[ -f "$stamp" ]] && continue
  echo "installing $name ($lic)"
  unzip -qo "$DL/$name" -d "$DATA"
  touch "$stamp"
done <<< "$MANIFEST"

echo "ok: BLENDER_USER_RESOURCES=$BLENDER_USER_RESOURCES"
