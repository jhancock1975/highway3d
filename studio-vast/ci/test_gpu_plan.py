"""gpu-plan.py: how the studio shares out the machine's GPUs, from nvidia-smi's answer.

    python3 studio-vast/ci/test_gpu_plan.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IN_REPO = os.path.join(HERE, "..", "ROOT", "opt", "studio-vast", "bin", "gpu-plan.py")
PLAN = os.environ.get("STUDIO_GPU_PLAN") or (IN_REPO if os.path.exists(IN_REPO) else "/opt/studio-vast/bin/gpu-plan.py")


def plan(csv, **env):
    r = subprocess.run([sys.executable, PLAN, "--from", "-"], input=csv, capture_output=True, text=True,
                       env={**os.environ, **env}, timeout=30)
    assert r.returncode == 0, r.stderr
    out = {}
    for line in r.stdout.splitlines():
        k, _, v = line.partition("=")
        out[k] = v.strip("'\"")
    return out


def test_one_rtx_pro_6000_gives_vllm_40_gb_of_96():          # 0.42, as proven on the GPU
    p = plan("0, 97887\n")
    assert p["STUDIO_GPU_COUNT"] == "1" and p["VLLM_GPU_UTIL"] == "0.42", p
    assert p["STUDIO_WORK_GPUS"] == "0" and "COMFYUI_CUDA_DEVICE" not in p, p


def test_a_bigger_card_gives_vllm_the_same_40_gb():
    assert plan("0, 143771\n")["VLLM_GPU_UTIL"] == "0.28"      # H200
    assert plan("0, 183359\n")["VLLM_GPU_UTIL"] == "0.22"      # B200


def test_two_cards_give_vllm_one_and_the_rest_the_other():
    p = plan("0, 97887\n1, 97887\n")
    assert p["STUDIO_GPU_COUNT"] == "2" and p["STUDIO_LLM_GPU"] == "0", p
    assert p["VLLM_GPU_UTIL"] == "0.9" and p["STUDIO_WORK_GPUS"] == "1" and p["COMFYUI_CUDA_DEVICE"] == "1", p


def test_four_cards_put_the_work_on_three():
    p = plan("0, 183359\n1, 183359\n2, 183359\n3, 183359\n")
    assert p["STUDIO_WORK_GPUS"] == "1,2,3" and p["COMFYUI_CUDA_DEVICE"] == "1", p


def test_a_small_card_still_gives_vllm_its_40_gb():
    assert plan("0, 49140\n")["VLLM_GPU_UTIL"] == "0.83"        # 40 GB of a 48 GB card


def test_a_vllm_share_set_by_hand_wins():
    assert plan("0, 97887\n", VLLM_GPU_UTIL="0.5")["VLLM_GPU_UTIL"] == "0.5"


def test_the_director_can_be_given_more_gb():
    assert plan("0, 97887\n", STUDIO_LLM_GB="60")["VLLM_GPU_UTIL"] == "0.63"


def test_no_gpu_says_so():
    p = plan("")
    assert p["STUDIO_GPU_COUNT"] == "0" and "VLLM_GPU_UTIL" not in p, p


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
