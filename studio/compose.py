"""Music from a description, by ACE-Step 1.5 on this machine's GPU.

    lectern/.musicvenv/bin/python -m studio.compose --description "slow sad piano, rain on glass" --seconds 40 --job 1a2b3c

Runs under lectern/.musicvenv, where ACE-Step is installed. ACE-Step is MIT
licensed; its authors trained it on licensed and public-domain music and say
its output may be used commercially. It uses the turbo model (8 steps,
guidance baked in), as cartoon/score.py does. A cue is instrumental unless
lyrics are given, and 10 seconds to 10 minutes long. ACE_HOME holds
checkpoints/ (acestep-v15-turbo, acestep-5Hz-lm-1.7B, Qwen3-Embedding-0.6B,
vae). The cue is filed in the library as a music- id.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(HERE, "lectern", ".musicvenv", "bin", "python")
ACE_HOME = os.environ.get("ACE_HOME", os.path.expanduser("~/.cache/ace-step"))
DIT = os.environ.get("ACE_DIT", "acestep-v15-turbo")
LM = "acestep-5Hz-lm-1.7B"
TURBO = "turbo" in DIT
MIN_SECONDS, MAX_SECONDS = 10.0, 600.0


def progress(stage: str) -> None:
    print("PROGRESS " + json.dumps({"stage": stage}), flush=True)


def params(description: str, seconds: float, lyrics: str = "", seed: int = -1) -> dict:
    """ACE-Step's generation settings, as plain values."""
    if not description.strip():
        raise ValueError("music needs a description: instruments, mood, tempo, style")
    sung = bool(lyrics.strip())
    return dict(caption=description.strip(),
                lyrics=lyrics.strip() if sung else "[Instrumental]",
                instrumental=not sung,
                duration=round(max(MIN_SECONDS, min(MAX_SECONDS, float(seconds))), 1),
                inference_steps=8 if TURBO else 50, guidance_scale=7.0,
                shift=3.0 if TURBO else 1.0,
                seed=random.randrange(2_000_000_000) if seed is None or int(seed) < 0 else int(seed))


def device(torch) -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def compose(description: str, seconds: float, lyrics: str = "", seed: int = -1,
            folder: str | None = None) -> tuple[str, dict]:
    """Generate the cue and write it as a WAV; returns (path, settings)."""
    import soundfile as sf
    import torch
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    p = params(description, seconds, lyrics, seed)
    folder = folder or tempfile.mkdtemp(prefix="studio-music-")
    dev = device(torch)
    progress(f"loading ACE-Step on the {dev.upper()}")
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=ACE_HOME, config_path=DIT, device=dev)
    if not ok:
        raise RuntimeError(f"ACE-Step's music model did not load: {msg}")
    lm = LLMHandler()
    msg, ok = lm.initialize(checkpoint_dir=os.path.join(ACE_HOME, "checkpoints"), lm_model_path=LM,
                            backend="mlx" if dev == "mps" else "pt", device=dev)
    if not ok:
        raise RuntimeError(f"ACE-Step's planner did not load: {msg}")
    progress(f"composing {p['duration']:.0f} seconds")
    r = generate_music(dit, lm, GenerationParams(**p),
                       GenerationConfig(batch_size=1, use_random_seed=False, seeds=[p["seed"]],
                                        audio_format="wav"),
                       save_dir=os.path.join(folder, "ace-out"))
    if not r.success:
        raise RuntimeError(f"ACE-Step failed: {r.error}")
    a = r.audios[0]["tensor"].detach().cpu().float().numpy()
    path = os.path.join(folder, "music.wav")
    sf.write(path, a.T if a.ndim == 2 else a, int(r.audios[0]["sample_rate"]))
    del dit, lm
    if dev == "cuda":
        torch.cuda.empty_cache()
    return path, p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--description", required=True)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--lyrics", default="")
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--job", default="")
    a = ap.parse_args()
    began = time.time()
    folder = tempfile.mkdtemp(prefix="studio-music-")
    try:
        path, p = compose(a.description, a.seconds, a.lyrics, a.seed, folder)
        sys.path.insert(0, HERE)
        from studio import library
        note = library.add(path, "music", source=f"ace-step 1.5 ({DIT})", move=True,
                           description=p["caption"], lyrics=p["lyrics"], seed=p["seed"])
    except Exception as e:
        print("FAILED " + (str(e).strip() or type(e).__name__), flush=True)
        sys.exit(1)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    print("DONE " + json.dumps(dict(out=note["path"], seconds=note["seconds"],
                                    bytes=os.path.getsize(note["path"]),
                                    took=time.time() - began, asset=note["id"])), flush=True)


if __name__ == "__main__":
    main()
