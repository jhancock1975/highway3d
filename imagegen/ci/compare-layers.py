#!/usr/bin/env python3
"""Check that an image starts with exactly the base image's layers (same digests).

vast hosts keep vastai/comfy's layers cached by digest, so they only stay free to pull
if our image reuses those blobs unchanged instead of re-compressing them.

Usage: compare-layers.py BASE_REF IMAGE_REF   (linux/amd64 is compared)
"""

import json
import subprocess
import sys


def raw_manifest(ref):
    out = subprocess.run(["docker", "buildx", "imagetools", "inspect", "--raw", ref],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def layers(ref):
    manifest = raw_manifest(ref)
    if "manifests" in manifest:  # an index: pick linux/amd64
        digest = next(m["digest"] for m in manifest["manifests"]
                      if m.get("platform", {}).get("architecture") == "amd64"
                      and m.get("platform", {}).get("os") == "linux")
        repo = ref.rsplit("@", 1)[0]
        if ":" in repo.rsplit("/", 1)[-1]:
            repo = repo.rsplit(":", 1)[0]
        manifest = raw_manifest(f"{repo}@{digest}")
    return [layer["digest"] for layer in manifest["layers"]]


def main():
    base_ref, image_ref = sys.argv[1], sys.argv[2]
    base, ours = layers(base_ref), layers(image_ref)
    if ours[:len(base)] != base:
        print(f"Base layer digests differ from {base_ref}; vast hosts would download them again.")
        return 1
    print(f"All {len(base)} base layers match {base_ref}; {len(ours) - len(base)} layers are new.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
