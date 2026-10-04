#!/usr/bin/env python3
"""Download one Hugging Face repo at a pinned revision into a folder, and keep it moving.

    studio-fetch.py REPO REVISION DEST

`hf download` sometimes slows to a crawl and stays there: on one host the director's 55.6 GB
ran at 870 MB/s to 77% and then at under 1 MB/s for the best part of an hour. So this runs it,
and every POLL seconds measures how much DEST and Hugging Face's chunk cache have grown. Past
the first GRACE seconds, if the last WINDOW seconds brought less than MIN_MBPS, it stops the
download and starts it again, which carries on from what is already on disk. A download that
exits with an error is tried again too, up to ATTEMPTS times in all.

DEST/.complete marks a finished download (nothing is fetched when it is there already) and
DEST/.failed says why it gave up. hf's own output goes to DEST.log beside the folder. The hf
command is $STUDIO_HF, else /venv/main/bin/hf, else hf on the PATH. Stdlib only.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time


def log(msg: str) -> None:
    print(f"studio-fetch: {msg}", flush=True)


def hf_command() -> str:
    if os.environ.get("STUDIO_HF"):
        return os.environ["STUDIO_HF"]
    if os.access("/venv/main/bin/hf", os.X_OK):
        return "/venv/main/bin/hf"
    return shutil.which("hf") or "hf"


def chunk_cache() -> str:
    home = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    return os.environ.get("HF_XET_CACHE") or os.path.join(home, "xet")


def size(folders: list[str]) -> int:
    total = 0
    for folder in folders:
        for d, _, files in os.walk(folder):
            for f in files:
                try:
                    total += os.lstat(os.path.join(d, f)).st_size
                except OSError:
                    pass
    return total


def stop(p: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, 10), (signal.SIGKILL, 10)):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            return
        try:
            p.wait(wait)
            return
        except subprocess.TimeoutExpired:
            pass


def last_line(path: str) -> str:
    try:
        with open(path, errors="replace") as fh:
            lines = [x.strip() for x in fh.read().replace("\r", "\n").splitlines() if x.strip()]
    except OSError:
        return ""
    return lines[-1][:300] if lines else ""


def attempt(cmd: list[str], dest: str, out: str, poll: float, grace: float, window: float,
            min_mbps: float) -> tuple[bool, str]:
    """One run of hf: (finished, why not)."""
    watch = [dest, chunk_cache()]
    with open(out, "a") as fh:
        p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
    began = time.time()
    samples = [(began, size(watch))]
    while p.poll() is None:
        time.sleep(poll)
        now = time.time()
        samples.append((now, size(watch)))
        samples = [s for s in samples if now - s[0] <= window + 2 * poll]
        if now - began < grace:
            continue
        old = next((s for s in samples if now - s[0] >= window), None)
        if old is None:
            continue
        rate = (samples[-1][1] - old[1]) / (now - old[0]) / 1e6
        if rate < min_mbps:
            stop(p)
            log(f"stalled at {rate:.2f} MB/s over the last {window:.0f} s; starting it again")
            return False, f"it stalled at {rate:.2f} MB/s"
    if p.returncode == 0:
        return True, ""
    return False, f"hf exited {p.returncode}: {last_line(out) or 'no reason given'}"


def fetch(repo: str, revision: str, dest: str, attempts: int = 8, poll: float = 10, grace: float = 120,
          window: float = 180, min_mbps: float = 5, pause: float = 15) -> int:
    complete, failed = os.path.join(dest, ".complete"), os.path.join(dest, ".failed")
    if os.path.exists(complete):
        log(f"{repo} is already downloaded in {dest}")
        return 0
    os.makedirs(dest, exist_ok=True)
    cmd = [hf_command(), "download", repo, "--revision", revision, "--local-dir", dest]
    why = ""
    for n in range(1, attempts + 1):
        log(f"downloading {repo} at {revision[:12]} into {dest} (attempt {n} of {attempts})")
        began = time.time()
        done, why = attempt(cmd, dest, dest.rstrip("/") + ".log", poll, grace, window, min_mbps)
        if done:
            open(complete, "w").close()
            if os.path.exists(failed):
                os.remove(failed)
            log(f"{repo} finished in {time.time() - began:.0f} s")
            return 0
        log(f"attempt {n} did not finish: {why}")
        if n < attempts:
            time.sleep(pause)
    with open(failed, "w") as fh:
        fh.write(f"gave up after {attempts} attempts: {why}\n")
    log(f"gave up on {repo} after {attempts} attempts: {why}")
    return 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo")
    ap.add_argument("revision")
    ap.add_argument("dest")
    ap.add_argument("--attempts", type=int, default=8)
    ap.add_argument("--poll", type=float, default=10, help="seconds between measurements")
    ap.add_argument("--grace", type=float, default=120, help="seconds before a stall can be called")
    ap.add_argument("--window", type=float, default=180, help="seconds the rate is measured over")
    ap.add_argument("--min-mbps", type=float, default=5, help="below this many MB/s it is a stall")
    ap.add_argument("--pause", type=float, default=15, help="seconds between attempts")
    a = ap.parse_args()
    sys.exit(fetch(a.repo, a.revision, a.dest, a.attempts, a.poll, a.grace, a.window, a.min_mbps, a.pause))


if __name__ == "__main__":
    main()
