#!/usr/bin/env python3
"""Check the studio's provisioning manifests without downloading anything.

- every download URL answers a token-less HEAD with 200, through Hugging Face's redirects,
  and reports a size;
- every destination is under /workspace, and no two share one;
- every `hf download REPO --revision SHA` in post_commands, and every repo studio-models.sh fetches
  with studio-fetch.py, names a public, ungated repo at a
  commit that exists;
- none.yaml downloads nothing.

    check-model-urls.py PROVISIONING_DIR
"""
import json
import os
import re
import subprocess
import sys

import yaml


def head(url):
    env = {k: v for k, v in os.environ.items() if k not in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")}
    out = subprocess.run(["curl", "--connect-timeout", "10", "--max-time", "60", "-sIL", url],
                         capture_output=True, text=True, env=env).stdout
    statuses, length = [], None
    for line in out.splitlines():
        low = line.lower()
        if low.startswith("http/"):
            statuses.append(int(line.split()[1]))
            length = None
        elif low.startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    return statuses, length


def api(path):
    out = subprocess.run(["curl", "--connect-timeout", "10", "--max-time", "60", "-s",
                          f"https://huggingface.co/api/models/{path}"], capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except ValueError:
        return {}


def check_repo(repo, rev):
    """(bytes, problems) for one pinned repo."""
    info = api(f"{repo}/revision/{rev}")
    if info.get("sha") == rev and not info.get("gated") and not info.get("private"):
        size = sum(s.get("size", 0) or 0 for s in api(f"{repo}?blobs=true").get("siblings", []))
        print(f"ok    {size / 1e9:6.2f} GB  {repo}@{rev[:8]} (public, not gated)")
        return size, 0
    print(f"FAIL  {repo}@{rev} is missing, gated or private")
    return 0, 1


def main(folder):
    bad = 0
    total = 0
    fetcher = os.path.join(folder, "..", "..", "supervisor-scripts", "studio-models.sh")
    if os.path.exists(fetcher):
        pins = re.findall(r'"\$FETCH" (\S+) ([0-9a-f]{40})', open(fetcher).read())
        print(f"== studio-models.sh: {len(pins)} repos")
        if not pins:
            print("FAIL  studio-models.sh fetches nothing")
            bad += 1
        for repo, rev in pins:
            size, problems = check_repo(repo, rev)
            total, bad = total + size, bad + problems
    for name in sorted(os.listdir(folder)):
        m = yaml.safe_load(open(os.path.join(folder, name)))
        downloads, posts = m.get("downloads") or [], m.get("post_commands") or []
        print(f"== {name}: {len(downloads)} downloads, {len(posts)} post commands")
        if name == "none.yaml" and (downloads or posts):
            print("FAIL  none.yaml must download nothing")
            bad += 1
        dests = [d["dest"] for d in downloads]
        if len(dests) != len(set(dests)):
            print("FAIL  two downloads share a destination")
            bad += 1
        for d in downloads:
            if not d["dest"].startswith("${WORKSPACE:-/workspace}/"):
                print(f"FAIL  {d['dest']} is not under /workspace")
                bad += 1
            statuses, length = head(d["url"])
            if statuses and statuses[-1] == 200 and length:
                total += length
                print(f"ok    {length / 1e9:6.2f} GB  {d['url'].split('/resolve/')[0].split('huggingface.co/')[1]}  {os.path.basename(d['dest'])}")
            else:
                print(f"FAIL  {d['url']} answered {statuses}")
                bad += 1
        for cmd in posts:
            for repo, rev in re.findall(r"hf download (\S+) --revision ([0-9a-f]{40})", cmd):
                size, problems = check_repo(repo, rev)
                total, bad = total + size, bad + problems
    print(f"\ntotal about {total / 1e9:.1f} GB; {bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv[1])
