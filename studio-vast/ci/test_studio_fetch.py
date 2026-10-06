"""studio-fetch.py, the model downloader that restarts a stalled download, against a stand-in hf.

    python3 studio-vast/ci/test_studio_fetch.py
"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
IN_REPO = os.path.join(HERE, "..", "ROOT", "opt", "studio-vast", "bin", "studio-fetch.py")
FETCH = os.environ.get("STUDIO_FETCH") or (IN_REPO if os.path.exists(IN_REPO) else "/opt/studio-vast/bin/studio-fetch.py")

# The stand-in: `hf download REPO --revision REV --local-dir DEST`. What it does on each run is
# read from $PLAN, one word per run: done (write 3 MB, exit 0), stall (write 1 MB, then hang),
# fail (exit 1). Every run is logged to $RUNS.
FAKE_HF = r'''#!/usr/bin/env python3
import os, sys, time
args = sys.argv[1:]
dest = args[args.index("--local-dir") + 1]
runs = os.environ["RUNS"]
n = sum(1 for _ in open(runs)) if os.path.exists(runs) else 0
open(runs, "a").write(" ".join(args) + "\n")
plan = os.environ["PLAN"].split()
step = plan[min(n, len(plan) - 1)]
os.makedirs(os.path.join(dest, ".cache"), exist_ok=True)
part = os.path.join(dest, ".cache", "model.incomplete")
if step == "fail":
    print("hf: 503 from the CDN", file=sys.stderr)
    sys.exit(1)
with open(part, "ab") as fh:
    fh.write(b"x" * 1_000_000)
    fh.flush()
    if step == "stall":
        time.sleep(3600)
    for _ in range(2):
        time.sleep(0.2)
        fh.write(b"x" * 1_000_000)
        fh.flush()
os.replace(part, os.path.join(dest, "model.safetensors"))
'''


def run(plan, *extra, dest=None):
    work = tempfile.mkdtemp(prefix="studio-fetch-")
    hf = os.path.join(work, "hf")
    with open(hf, "w") as fh:
        fh.write(FAKE_HF)
    os.chmod(hf, 0o755)
    dest = dest or os.path.join(work, "llm")
    runs = os.path.join(work, "runs")
    env = dict(os.environ, STUDIO_HF=hf, PLAN=plan, RUNS=runs, HF_HOME=os.path.join(work, "hf-home"))
    began = time.time()
    r = subprocess.run([sys.executable, FETCH, "huihui-ai/some-model", "abc123", dest,
                        "--poll", "0.2", "--grace", "1", "--window", "1.5", "--min-mbps", "0.5",
                        "--pause", "0.1", *extra], env=env, capture_output=True, text=True, timeout=60)
    n = sum(1 for _ in open(runs)) if os.path.exists(runs) else 0
    return r, dest, n, time.time() - began


def test_a_download_that_finishes_is_marked_complete():
    r, dest, n, _ = run("done")
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.exists(os.path.join(dest, ".complete")) and n == 1, (os.listdir(dest), n)


def test_a_stalled_download_is_restarted_and_finishes():
    r, dest, n, took = run("stall done")
    assert r.returncode == 0, r.stdout + r.stderr
    assert n == 2 and os.path.exists(os.path.join(dest, ".complete")), (n, os.listdir(dest))
    assert "stalled" in r.stdout and took < 20, (r.stdout, took)


def test_the_restart_resumes_into_the_same_folder():
    _, dest, _, _ = run("stall done")
    assert os.path.getsize(os.path.join(dest, "model.safetensors")) == 4_000_000


def test_a_download_that_keeps_failing_gives_up_and_says_why():
    r, dest, n, _ = run("fail", "--attempts", "3")
    assert r.returncode == 1 and n == 3, (r.returncode, n, r.stdout)
    assert not os.path.exists(os.path.join(dest, ".complete"))
    with open(os.path.join(dest, ".failed")) as fh:
        why = fh.read()
    assert "3 attempts" in why and "503" in why, why


def test_an_earlier_failure_mark_is_cleared_by_a_success():
    dest = os.path.join(tempfile.mkdtemp(prefix="studio-fetch-"), "llm")
    os.makedirs(dest)
    open(os.path.join(dest, ".failed"), "w").write("old")
    r, dest, _, _ = run("done", dest=dest)
    assert r.returncode == 0 and not os.path.exists(os.path.join(dest, ".failed")), os.listdir(dest)


def test_nothing_is_fetched_when_already_complete():
    dest = os.path.join(tempfile.mkdtemp(prefix="studio-fetch-"), "llm")
    os.makedirs(dest)
    open(os.path.join(dest, ".complete"), "w").close()
    r, _, n, _ = run("fail", dest=dest)
    assert r.returncode == 0 and n == 0, (r.returncode, n)


if __name__ == "__main__":
    bad = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:
                bad += 1
                print("FAIL", name, type(e).__name__, str(e)[:300])
    sys.exit(1 if bad else 0)
