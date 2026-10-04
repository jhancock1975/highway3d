"""cartoon.score's settings.

    cartoon/.venv/bin/python cartoon/test_score.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_ace_step_home_comes_from_the_environment():
    r = subprocess.run([sys.executable, "-c", "from cartoon import score; print(score.ACE_HOME)"], cwd=ROOT,
                       env={**os.environ, "ACE_HOME": "/workspace/models/ace-step"}, capture_output=True, text=True)
    assert r.stdout.strip() == "/workspace/models/ace-step", r.stdout + r.stderr[-500:]


if __name__ == "__main__":
    bad = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as e:
                bad += 1
                print("FAIL", name, str(e)[:300])
    sys.exit(1 if bad else 0)
