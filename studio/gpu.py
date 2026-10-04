"""One GPU job at a time.

The studio's GPU work runs as separate processes: Wan through ComfyUI, ACE-Step,
cartoon's score. Beside vLLM's share there is room for one of them, not two, so
each holds this lock while it uses the card and the next one waits its turn. It
is an flock on a file in the jobs' work folder, so it is shared by every
process on the machine and let go when its holder exits, even by crashing.
"""

from __future__ import annotations

import contextlib
import fcntl
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.environ.get("STUDIO_GPU_LOCK") or os.path.join(
    os.environ.get("STUDIO_WORK", os.path.join(HERE, "studio", ".work")), "gpu.lock")
WAITING = "waiting for the GPU: another job is using it"


@contextlib.contextmanager
def hold(on_wait=None, path: str | None = None):
    """Hold the GPU for the block; if another job has it, call on_wait(WAITING) once and wait."""
    path = path or LOCK
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if on_wait:
                on_wait(WAITING)
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
