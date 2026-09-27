"""Background jobs: start one, and say how it is going whenever asked.

The same shape lectern's renders use. A job's log opens with a JOB line
saying what it will make, then PROGRESS lines, then DONE or FAILED. A job
whose process has gone without writing either is said to have stopped,
rather than reported at its last progress line forever -- which is what a
render killed by the Mac going down used to look like.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.environ.get("STUDIO_WORK", os.path.join(HERE, "studio", ".work"))


def new() -> str:
    return uuid.uuid4().hex[:6]


def start(job: str, module: str, args: list[str], header: dict) -> str:
    """Run `python -m module *args --job job` detached. Returns its log."""
    os.makedirs(WORK, exist_ok=True)
    log = os.path.join(WORK, f"job-{job}.log")
    with open(log, "w") as fh:
        fh.write("JOB " + json.dumps(header) + "\n")
        fh.flush()
        subprocess.Popen([sys.executable, "-m", module, *args, "--job", job],
                         cwd=HERE, stdout=fh, stderr=subprocess.STDOUT,
                         start_new_session=True)
    return log


def live() -> set[str]:
    """Jobs whose process is still running, whichever server started them."""
    r = subprocess.run(["ps", "-axww", "-o", "args="], capture_output=True,
                       text=True)
    return set(re.findall(r"-m studio\.\w+ .*--job (\w+)", r.stdout))


def _read(log: str) -> tuple[dict, str]:
    with open(log) as fh:
        lines = [x.strip() for x in fh if x.strip()]
    head = {}
    if lines and lines[0].startswith("JOB "):
        try:
            head = json.loads(lines[0][4:])
        except ValueError:
            pass
    tail = next((x for x in reversed(lines)
                 if x.startswith(("PROGRESS", "DONE", "FAILED"))), "")
    return head, tail


def _report(job: str, log: str, running: set[str]) -> str:
    head, tail = _read(log)
    name = f"Job {job} ('{head['name']}')" if head.get("name") else f"Job {job}"
    if tail.startswith("DONE"):
        d = json.loads(tail[4:])
        return (f"{name}: finished: {d['out']}, {d['seconds']:.1f} seconds "
                f"long, {d['bytes'] / 1e6:.1f} MB, took {d['took']:.0f} "
                f"seconds.")
    if tail.startswith("FAILED"):
        return f"{name}: stopped: {tail[6:].strip()}"
    if job not in running:
        return (f"{name}: stopped before it finished, without saying why: its "
                f"process is no longer running, most likely because the "
                f"server or the Mac restarted under it. Assembling the same "
                f"edit again starts it over.")
    if tail.startswith("PROGRESS"):
        d = json.loads(tail[8:])
        done = f", {d['percent']:.0f}% done" if "percent" in d else ""
        return f"{name}: {d['stage']}{done}."
    return f"{name}: started, nothing reported yet."


def status(job: str = "") -> str:
    """How a job is going; with no job, the newest and any still running."""
    running = live()
    job = job.strip()
    if job:
        log = os.path.join(WORK, f"job-{job}.log")
        if not re.fullmatch(r"\w+", job) or not os.path.exists(log):
            return (f"There is no job {job} on this server. Ask without a job "
                    f"id to hear about the most recent one.")
        return _report(job, log, running)
    logs = sorted(glob.glob(os.path.join(WORK, "job-*.log")),
                  key=os.path.getmtime, reverse=True)
    if not logs:
        return "Nothing has been assembled on this server yet."

    def job_of(p: str) -> str:
        return os.path.basename(p)[len("job-"):-len(".log")]

    shown = logs[:1] + [p for p in logs[1:] if job_of(p) in running]
    return "\n".join(_report(job_of(p), p, running) for p in shown)
