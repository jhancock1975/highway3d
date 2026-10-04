#!/usr/bin/env python3
"""Check the provisioning manifests without downloading anything.

- every download URL answers a token-less HEAD with 200, or a redirect that ends in 200
  (Hugging Face 302s to its CDN), and reports a real file size
- every destination is under ComfyUI's models folder and no two downloads share one
- all.yaml is exactly kroma.yaml + chroma.yaml, and none.yaml downloads nothing

Usage: check-model-urls.py PROVISIONING_DIR
Needs curl and PyYAML.
"""

import os
import subprocess
import sys

import yaml

MODELS_PREFIX = "${WORKSPACE:-/workspace}/ComfyUI/models/"


def head(url):
    """Follow redirects with HEAD requests; return (status chain, final content-length, error code header)."""
    env = {k: v for k, v in os.environ.items() if k not in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")}
    out = subprocess.run(
        ["curl", "--connect-timeout", "10", "--max-time", "60", "-sIL", url],
        capture_output=True, text=True, env=env,
    ).stdout
    statuses, length, error = [], None, None
    for line in out.splitlines():
        low = line.lower()
        if low.startswith("http/"):
            statuses.append(int(line.split()[1]))
            length = None
        elif low.startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
        elif low.startswith("x-error-code:"):
            error = line.split(":", 1)[1].strip()
    return statuses, length, error


def load(path):
    with open(path) as fh:
        data = yaml.safe_load(fh)
    assert data.get("version") == 1, f"{path}: missing 'version: 1'"
    return [(d["url"], d["dest"]) for d in data.get("downloads") or []]


def main():
    folder = sys.argv[1]
    sets = {name: load(os.path.join(folder, f"{name}.yaml")) for name in ("all", "kroma", "chroma", "none")}
    problems = []

    if sorted(sets["all"]) != sorted(sets["kroma"] + sets["chroma"]):
        problems.append("all.yaml is not exactly kroma.yaml + chroma.yaml")
    if sets["none"]:
        problems.append("none.yaml has downloads")

    dests = [d for _, d in sets["all"]]
    if len(dests) != len(set(dests)):
        problems.append("two downloads share a destination")
    for dest in dests:
        if not dest.startswith(MODELS_PREFIX):
            problems.append(f"destination outside ComfyUI's models folder: {dest}")

    sizes = {}
    for url, dest in sets["all"]:
        statuses, length, error = head(url)
        ok = (
            statuses
            and statuses[0] in (200, 301, 302, 303, 307, 308)
            and statuses[-1] == 200
            and error is None
            and length is not None
            and length > 1_000_000
        )
        verdict = "OK  " if ok else "FAIL"
        print(f"{verdict} {' -> '.join(map(str, statuses)) or 'no answer'}  "
              f"{(length or 0) / 1e9:6.2f} GB  {dest.removeprefix(MODELS_PREFIX)}\n       {url}")
        if not ok:
            problems.append(f"not downloadable without a token: {url} (statuses {statuses}, error {error})")
        sizes[url] = length or 0

    print()
    for name in ("kroma", "chroma", "all"):
        total = sum(sizes[u] for u, _ in sets[name])
        print(f"{name:>6}.yaml: {len(sets[name])} files, {total / 1e9:.2f} GB ({total:,} bytes)")

    if problems:
        print("\n" + "\n".join("PROBLEM: " + p for p in problems))
        return 1
    print("\nEvery model URL downloads without a Hugging Face token.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
