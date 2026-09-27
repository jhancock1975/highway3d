"""What lecture_status says, with and without a job id. No server, no Blender.

    lectern/.mcpvenv/bin/python lectern/test_status.py

Cider's router sees only the latest message, so "is my lecture done yet?"
arrives with no job id; without a default it never got an answer. And a
render killed by the Mac going down leaves a log that ends mid-PROGRESS,
which read back as "typesetting: 5 of 5" forever.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
WORK = tempfile.mkdtemp(prefix="lectern-status-")
os.environ["LECTERN_WORK"] = WORK
os.environ["LECTERN_RENDERS"] = tempfile.mkdtemp(prefix="lectern-renders-")
from lectern import mcp_server as M  # noqa: E402

DONE = 'DONE {"out": "/r/sky.mp4", "minutes": 1.1, "shots": 5, "bytes": 42000000, "hours": 0.2}'
_age = [0]


def log(job, *lines, title=None, lecture="sky"):
    """A job log, each one newer than the last."""
    p = os.path.join(WORK, f"job-{job}.log")
    with open(p, "w") as fh:
        if title:
            fh.write("JOB " + json.dumps(dict(lecture=lecture, title=title)) + "\n")
        fh.write("\n".join(lines) + "\n")
    _age[0] += 10
    os.utime(p, (1e9 + _age[0], 1e9 + _age[0]))


def build(job):
    """A process that looks like a running build to ps."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                             "lectern.build", "--script", "x.yaml", "--job", job])


def clear():
    for f in os.listdir(WORK):
        os.remove(os.path.join(WORK, f))


def test_nothing_rendered_yet():
    clear()
    assert M.lecture_status() == "No lecture has been rendered on this server yet."
    assert M.lecture_status("  ") == "No lecture has been rendered on this server yet."


def test_no_job_names_the_newest():
    clear()
    log("aaaaaa", DONE, title="Old One")
    log("bbbbbb", DONE, title="Why the Sky Is Blue")
    got = M.lecture_status()
    assert got.startswith("Job bbbbbb ('Why the Sky Is Blue'): Finished: /r/sky.mp4"), got
    assert "aaaaaa" not in got, got


def test_a_render_the_crash_killed_says_so():
    clear()
    log("cccccc", 'PROGRESS {"stage": "typesetting", "done": 5, "total": 5}',
        title="Why the Sky Is Blue")
    got = M.lecture_status("cccccc")
    assert "stopped before it finished" in got, got
    assert "Rendering 'sky' again with lecture_render" in got, got
    assert "5 of 5" not in got, got


def test_a_log_from_before_the_header():
    clear()
    log("88839f", 'PROGRESS {"stage": "typesetting", "done": 5, "total": 5}')
    got = M.lecture_status()
    assert got.startswith("Job 88839f: That render stopped"), got
    assert "Rendering it again" in got, got


def test_every_running_render_is_listed():
    clear()
    procs = [build("dddddd"), build("eeeeee")]
    try:
        log("dddddd", 'PROGRESS {"stage": "rendering", "done": 3, "total": 5}',
            title="Sky")
        log("eeeeee", 'PROGRESS {"stage": "narrating", "done": 1, "total": 5}',
            title="Sea")
        log("ffffff", 'PROGRESS {"stage": "rendering", "done": 1, "total": 9}',
            title="Dead")
        log("999999", DONE, title="Newest")
        got = M.lecture_status().splitlines()
        assert len(got) == 3, got
        assert got[0].startswith("Job 999999 ('Newest'): Finished"), got
        assert "Job dddddd ('Sky'): rendering: 3 of 5." in got, got
        assert "Job eeeeee ('Sea'): narrating: 1 of 5." in got, got
    finally:
        for p in procs:
            p.kill()
            p.wait()


def test_a_job_id_reads_as_it_did():
    clear()
    proc = build("121212")
    try:
        log("121212", 'PROGRESS {"stage": "rendering", "done": 2, "total": 5, "eta_hours": 1.5}',
            title="Sky")
        assert M.lecture_status("121212") == "rendering: 2 of 5, about 1.5 hours to go."
    finally:
        proc.kill()
        proc.wait()
    got = M.lecture_status("nope00")
    assert got.startswith("There is no job nope00 on this server."), got


def test_start_writes_the_header():
    clear()

    class Fake:
        pid = 1

    real = M.subprocess.Popen
    M.subprocess.Popen = lambda *a, **k: Fake()
    try:
        doc = M._load("why-the-sky-is-blue")
        M._start("why-the-sky-is-blue", doc)
    finally:
        M.subprocess.Popen = real
    (name,) = os.listdir(WORK)
    with open(os.path.join(WORK, name)) as fh:
        head = M._head([fh.readline().strip()])
    assert head["lecture"] == "why-the-sky-is-blue", head
    assert head["title"] == doc["title"], head


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
