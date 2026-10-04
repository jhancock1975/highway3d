#!/usr/bin/env python3
"""Give SwarmUI per-model default settings on first boot.

SwarmUI keeps presets in its user database rather than in files, so they cannot be
shipped in the image. This waits for SwarmUI to answer on 127.0.0.1, adds one preset per
model through SwarmUI's own API, and links each preset to its model, so picking the model
in the Generate tab switches the preset on (and picking another model switches it off).

It runs once per workspace: a marker in SwarmUI's Data folder stops it from re-adding
presets the user later edits or deletes. Standard library only.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

SWARMUI = os.environ.get("SWARMUI_URL", "http://127.0.0.1:17801")
DATA_DIR = os.path.join(os.environ.get("WORKSPACE", "/workspace"), "SwarmUI", "Data")
MARKER = os.path.join(DATA_DIR, ".imagegen-defaults-v1")

# Model names are file names without ".safetensors", as SwarmUI shows them.
# SwarmUI already picks the right sampler, scheduler and sigma shift for each model
# class (Krea 2: shift 1.15; Chroma: euler, beta, shift 1); these fill in the rest.
PRESETS = [
    {
        "model": "kroma-v0.3-turbo",
        "title": "Kroma turbo",
        "description": "Kroma v0.3 turbo: 8 steps, CFG 1, sigma shift 1.15, weights kept at 16-bit "
                       "(SwarmUI would otherwise load this model in fp8). Untick Preferred DType "
                       "on GPUs under 40 GB.",
        "param_map": {"steps": "8", "cfgscale": "1", "sigmashift": "1.15", "preferreddtype": "default"},
    },
    {
        "model": "Chroma1-HD",
        "title": "Chroma1-HD",
        "description": "Chroma1-HD: 26 steps, CFG 3.8, as in the model's reference workflow. "
                       "Long, descriptive prompts and a negative prompt help.",
        "param_map": {"steps": "26", "cfgscale": "3.8"},
    },
]


def call(route, payload):
    req = urllib.request.Request(
        f"{SWARMUI}/API/{route}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def new_session(wait_seconds):
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            return call("GetNewSession", {})["session_id"]
        except (urllib.error.URLError, OSError, KeyError, ValueError):
            time.sleep(5)
    return None


def main():
    if os.path.exists(MARKER):
        return 0
    session = new_session(wait_seconds=30 * 60)
    if not session:
        print("swarmui-defaults: SwarmUI never answered, presets not added", flush=True)
        return 1

    user = call("GetMyUserData", {"session_id": session})
    existing = {p.get("title") for p in user.get("presets", [])}
    links = user.get("model_preset_links") or {}
    model_links = links.setdefault("Stable-Diffusion", {})

    for preset in PRESETS:
        if preset["title"] not in existing:
            result = call("AddNewPreset", {
                "session_id": session,
                "title": preset["title"],
                "description": preset["description"],
                "param_map": preset["param_map"],
            })
            if not result.get("success"):
                print(f"swarmui-defaults: could not add preset {preset['title']!r}: {result}", flush=True)
                return 1
            print(f"swarmui-defaults: added preset {preset['title']!r}", flush=True)
        # Never replace a link the user chose themselves.
        model_links.setdefault(preset["model"], [preset["title"]])

    result = call("SetPresetLinks", dict(links, session_id=session))
    if not result.get("success"):
        print(f"swarmui-defaults: could not link presets to models: {result}", flush=True)
        return 1

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MARKER, "w") as fh:
        fh.write("presets added: " + ", ".join(p["title"] for p in PRESETS) + "\n")
    print("swarmui-defaults: model presets linked", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
