#!/usr/bin/env python3
"""How the studio shares out this machine's GPUs, as KEY=VALUE lines for /etc/studio-gpus.env.

    gpu-plan.py            asks nvidia-smi
    gpu-plan.py --from -   reads nvidia-smi's CSV (index, memory.total in MiB) from stdin

One GPU: vLLM takes STUDIO_LLM_GB of it (40 GB unless set: the FP8 weights, a 64k context and
its cache), as VLLM_GPU_UTIL, the fraction vLLM asks for, and ComfyUI, ACE-Step and Blender
share the rest one job at a time. Two or more: vLLM has GPU 0 to itself and the work goes on
the others (STUDIO_WORK_GPUS, and ComfyUI on the first of them). A VLLM_GPU_UTIL set by hand
wins. No GPU: only STUDIO_GPU_COUNT=0. Stdlib only.
"""

import argparse
import os
import subprocess
import sys

LLM_GB = 40.0
DEDICATED = 0.9


def read(source: str) -> list[tuple[int, float]]:
    if source == "-":
        text = sys.stdin.read()
    else:
        try:
            text = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.total", "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired):
            text = ""
    gpus = []
    for line in text.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 2:
            try:
                gpus.append((int(parts[0]), float(parts[1])))
            except ValueError:
                pass
    return gpus


def plan(gpus: list[tuple[int, float]], env: dict) -> dict:
    out = {"STUDIO_GPU_COUNT": str(len(gpus))}
    if not gpus:
        return out
    out["STUDIO_LLM_GPU"] = str(gpus[0][0])
    if len(gpus) >= 2:
        util, work = DEDICATED, [g[0] for g in gpus[1:]]
        out["COMFYUI_CUDA_DEVICE"] = str(work[0])
    else:
        gb = float(env.get("STUDIO_LLM_GB") or LLM_GB)
        util, work = min(DEDICATED, max(0.1, round(gb / (gpus[0][1] / 1024), 2))), [gpus[0][0]]
    out["VLLM_GPU_UTIL"] = env.get("VLLM_GPU_UTIL") or f"{util:g}"
    out["STUDIO_WORK_GPUS"] = ",".join(str(g) for g in work)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="source", default="nvidia-smi")
    a = ap.parse_args()
    for k, v in plan(read(a.source), os.environ).items():
        print(f"{k}={v}")


if __name__ == "__main__":
    main()
