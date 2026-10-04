"""What studio_status says about jobs, live, finished and dead. No engines.

    studio/.venv/bin/python studio/test_jobs.py
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_WORK"] = tempfile.mkdtemp(prefix="studio-work-")
from studio import jobs as J  # noqa: E402

DONE = 'DONE {"out": "/r/spot.mp4", "seconds": 12.04, "bytes": 3400000, "took": 41.2}'
_age = [0]


def log(job, *lines, name="spot"):
    p = os.path.join(J.WORK, f"job-{job}.log")
    with open(p, "w") as fh:
        fh.write("JOB " + json.dumps(dict(name=name, out="/r/x.mp4")) + "\n")
        fh.write("\n".join(lines) + "\n")
    _age[0] += 10
    os.utime(p, (1e9 + _age[0], 1e9 + _age[0]))


def running(job):
    """A process that looks like a live studio job to ps."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                             "-m", "studio.assemble", "--job", job])


def clear():
    for f in os.listdir(J.WORK):
        os.remove(os.path.join(J.WORK, f))


def test_nothing_yet():
    clear()
    assert J.status() == "Nothing has been assembled on this server yet."


def test_finished_job():
    clear()
    log("aaaaaa", DONE)
    assert J.status() == ("Job aaaaaa ('spot'): finished: /r/spot.mp4, 12.0 "
                          "seconds long, 3.4 MB, took 41 seconds."), J.status()


def test_failed_job():
    clear()
    log("bbbbbb", "FAILED ffmpeg stopped: clip-9c01 has no video stream.")
    assert J.status("bbbbbb") == ("Job bbbbbb ('spot'): stopped: ffmpeg "
                                  "stopped: clip-9c01 has no video stream.")


def test_dead_job_says_so():
    clear()
    log("cccccc", 'PROGRESS {"stage": "encoding", "percent": 40}')
    got = J.status("cccccc")
    assert "stopped before it finished" in got and "40" not in got, got


def test_running_jobs_all_listed_with_progress():
    clear()
    procs = [running("dddddd"), running("eeeeee")]
    try:
        log("dddddd", 'PROGRESS {"stage": "encoding", "percent": 40}', name="one")
        log("eeeeee", 'PROGRESS {"stage": "drawing", "percent": 0}', name="two")
        log("ffffff", DONE, name="newest")
        got = J.status().splitlines()
        assert len(got) == 3, got
        assert got[0].startswith("Job ffffff ('newest'): finished"), got
        assert "Job dddddd ('one'): encoding, 40% done." in got, got
        assert "Job eeeeee ('two'): drawing, 0% done." in got, got
    finally:
        for p in procs:
            p.kill()
            p.wait()


def test_unknown_or_odd_job_ids():
    clear()
    for job in ("123456", "../../etc"):
        got = J.status(job)
        assert got.startswith(f"There is no job {job} on this server."), got


def test_start_writes_header_and_runs():
    clear()
    job = J.new()
    log_path = J.start(job, "json.tool", ["--help"], dict(name="probe", out="/r/p"))
    with open(log_path) as fh:
        first = fh.readline()
    assert first.startswith("JOB ") and json.loads(first[4:])["name"] == "probe", first


def test_a_finished_job_names_what_it_made():
    job = "aa11bb"
    log = os.path.join(J.WORK, f"job-{job}.log")
    with open(log, "w") as fh:
        fh.write('JOB {"name": "animate pic-1a2b"}\n')
        fh.write('DONE {"out": "/m/out.mp4", "seconds": 5.1, "bytes": 2000000, "took": 70, "asset": "clip-9c01"}\n')
    said = J.status(job)
    assert "clip-9c01" in said and "finished" in said, said


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
