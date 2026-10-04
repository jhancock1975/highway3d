"""One GPU job at a time.

    studio/.venv/bin/python studio/test_gpu.py
"""
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["STUDIO_GPU_LOCK"] = os.path.join(tempfile.mkdtemp(prefix="studio-gpu-"), "gpu.lock")
from studio import gpu  # noqa: E402


def test_a_second_job_waits_for_the_gpu_and_says_so():
    said, inside = [], threading.Event()

    def second():
        with gpu.hold(on_wait=said.append):
            inside.set()

    with gpu.hold():
        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.5)
        assert not inside.is_set(), "the second job got the GPU while the first had it"
        assert said == ["waiting for the GPU: another job is using it"], said
    t.join(5)
    assert inside.is_set(), "the second job never got the GPU"


def test_no_wait_and_nothing_said_when_the_gpu_is_free():
    said = []
    began = time.time()
    with gpu.hold(on_wait=said.append):
        pass
    assert said == [] and time.time() - began < 0.5, said


def test_a_job_that_dies_lets_go_of_the_gpu():
    p = subprocess.Popen([sys.executable, "-c", "import time; from studio import gpu\n"
                          "with gpu.hold():\n    print('held', flush=True); time.sleep(60)"],
                         cwd=ROOT, stdout=subprocess.PIPE, text=True, env=dict(os.environ))
    assert p.stdout.readline().strip() == "held"
    p.kill()
    p.wait()
    said = []
    with gpu.hold(on_wait=said.append):
        pass
    assert said == [], "a killed job kept the GPU"


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
