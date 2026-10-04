"""ACE-Step music, with ACE-Step and torch stood in for, so it runs anywhere.

    studio/.venv/bin/python studio/test_compose.py
"""
import os
import sys
import tempfile
import threading
import time
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["STUDIO_MEDIA"] = tempfile.mkdtemp(prefix="studio-media-")
os.environ["STUDIO_GPU_LOCK"] = os.path.join(tempfile.mkdtemp(prefix="studio-gpu-"), "gpu.lock")
from studio import compose, gpu  # noqa: E402

CALLS = {}


def fake_modules(cuda=True):
    torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: cuda, empty_cache=lambda: None),
                                  backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)))

    class Handler:
        def initialize_service(self, project_root, config_path, device):
            CALLS["dit"] = (project_root, config_path, device)
            return "ok", True

    class LLM:
        def initialize(self, checkpoint_dir, lm_model_path, backend, device):
            CALLS["lm"] = (checkpoint_dir, lm_model_path, backend, device)
            return "ok", True

    class Tensor:
        def __init__(self, a):
            self.a = a

        def detach(self):
            return self

        def cpu(self):
            return self

        def float(self):
            return self

        def numpy(self):
            return self.a

    def generate_music(dit, lm, params, config, save_dir=None):
        CALLS["params"] = params
        audio = np.zeros((2, int(params.duration * 48000)), dtype=np.float32)
        return types.SimpleNamespace(success=True, error="", audios=[{"tensor": Tensor(audio), "sample_rate": 48000}])

    inference = types.SimpleNamespace(GenerationParams=lambda **k: types.SimpleNamespace(**k),
                                      GenerationConfig=lambda **k: types.SimpleNamespace(**k),
                                      generate_music=generate_music)
    sys.modules.update({"torch": torch, "acestep": types.ModuleType("acestep"),
                        "acestep.handler": types.SimpleNamespace(AceStepHandler=Handler),
                        "acestep.inference": inference,
                        "acestep.llm_inference": types.SimpleNamespace(LLMHandler=LLM)})
    return torch


def test_length_is_kept_between_ten_seconds_and_ten_minutes():
    assert compose.params("piano", 5)["duration"] == 10.0
    assert compose.params("piano", 900)["duration"] == 600.0
    assert compose.params("piano", 42.26)["duration"] == 42.3


def test_instrumental_unless_lyrics_are_given():
    p = compose.params("sad piano", 30)
    assert p["instrumental"] is True and p["lyrics"] == "[Instrumental]"
    s = compose.params("torch song", 30, lyrics="[verse]\nYou came back")
    assert s["instrumental"] is False and s["lyrics"].startswith("[verse]")


def test_turbo_settings_and_a_given_seed():
    p = compose.params("x", 20, seed=7)
    assert (p["inference_steps"], p["shift"], p["seed"]) == (8, 3.0, 7)
    assert compose.params("x", 20)["seed"] >= 0


def test_device_prefers_cuda():
    assert compose.device(fake_modules(cuda=True)) == "cuda"
    assert compose.device(fake_modules(cuda=False)) == "cpu"


def test_compose_writes_a_wav_of_the_asked_length():
    fake_modules(cuda=True)
    path, p = compose.compose("melancholy synth, rain", 12, seed=3, folder=tempfile.mkdtemp())
    import soundfile as sf
    info = sf.info(path)
    assert abs(info.duration - 12.0) < 0.01 and info.channels == 2, info
    assert CALLS["dit"][2] == "cuda" and CALLS["lm"][2] == "pt"
    assert CALLS["params"].caption == "melancholy synth, rain"


def test_empty_description_is_refused():
    try:
        compose.params("  ", 30)
    except ValueError as e:
        assert "description" in str(e)
    else:
        raise AssertionError("empty description accepted")



def test_ace_step_waits_while_another_job_has_the_gpu():
    import contextlib
    import io
    fake_modules(cuda=True)
    CALLS.pop("dit", None)
    out, done = io.StringIO(), []
    with contextlib.redirect_stdout(out):
        with gpu.hold():
            t = threading.Thread(target=lambda: done.append(
                compose.compose("rain", 10, seed=1, folder=tempfile.mkdtemp())))
            t.start()
            time.sleep(0.5)
            assert "dit" not in CALLS, "ACE-Step loaded while another job had the GPU"
        t.join(30)
    assert done and "dit" in CALLS, CALLS
    assert "waiting for the GPU: another job is using it" in out.getvalue(), out.getvalue()


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
