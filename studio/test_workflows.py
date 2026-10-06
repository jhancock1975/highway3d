"""The ComfyUI graphs: wired up, and carrying what they were asked for. No ComfyUI.

    studio/.venv/bin/python studio/test_workflows.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import workflows as W  # noqa: E402


def links_resolve(graph):
    for nid, node in graph.items():
        for name, value in node["inputs"].items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                assert value[0] in graph, f"node {nid} input {name} points at missing node {value[0]}"


def test_chroma_is_wired_and_carries_the_request():
    g = W.chroma_t2i("a red fox in snow", 1344, 768, count=3, seed=42, negative="blurry")
    links_resolve(g)
    kinds = {n["class_type"] for n in g.values()}
    assert {"UNETLoader", "CLIPLoader", "T5TokenizerOptions", "ModelSamplingAuraFlow", "KSampler",
            "EmptySD3LatentImage", "VAEDecode", "SaveImage"} <= kinds, kinds
    by = {n["class_type"]: n["inputs"] for n in g.values()}
    assert by["EmptySD3LatentImage"] == {"width": 1344, "height": 768, "batch_size": 3}
    assert by["KSampler"]["seed"] == 42 and by["KSampler"]["steps"] == 26 and by["KSampler"]["cfg"] == 3.8
    assert by["KSampler"]["scheduler"] == "beta" and by["ModelSamplingAuraFlow"]["shift"] == 1.0
    texts = sorted(n["inputs"]["text"] for n in g.values() if n["class_type"] == "CLIPTextEncode")
    assert texts == ["a red fox in snow", "blurry"], texts
    assert by["UNETLoader"]["unet_name"] == "Chroma1-HD.safetensors"
    assert by["CLIPLoader"] == {"clip_name": "t5xxl_enconly.safetensors", "type": "chroma", "device": "default"}


def test_chroma_uses_the_standard_negative_when_none_given():
    g = W.chroma_t2i("x", 1024, 1024)
    assert W.CHROMA_NEGATIVE in [n["inputs"].get("text") for n in g.values()]


def test_wan_is_wired_and_splits_the_steps():
    g = W.wan_i2v("studio-1a2b.png", "she turns away", 832, 480, 81, seed=7)
    links_resolve(g)
    assert g["5"] == {"class_type": "LoadImage", "inputs": {"image": "studio-1a2b.png"}}
    w = g["8"]["inputs"]
    assert (w["width"], w["height"], w["length"], w["batch_size"]) == (832, 480, 81, 1)
    hi, lo = g["11"]["inputs"], g["12"]["inputs"]
    assert (hi["start_at_step"], hi["end_at_step"], lo["start_at_step"]) == (0, 4, 4)
    assert hi["noise_seed"] == lo["noise_seed"] == 7 and hi["cfg"] == lo["cfg"] == 1.0
    assert hi["add_noise"] == "enable" and lo["add_noise"] == "disable"
    assert g["9"]["inputs"]["shift"] == g["10"]["inputs"]["shift"] == 8.0
    assert g["1"]["inputs"]["unet_name"] == W.WAN["high"] and g["2"]["inputs"]["unet_name"] == W.WAN["low"]
    assert g["6"]["inputs"]["text"] == "she turns away" and g["7"]["inputs"]["text"] == W.WAN_NEGATIVE
    assert g["14"]["inputs"]["fps"] == 16.0
    assert g["15"]["class_type"] == "SaveVideo" and g["15"]["inputs"]["format"] == "mp4"


def test_frames_are_sixteen_a_second_plus_one_and_capped():
    assert W.frames(5) == 81 and W.frames(1) == 17
    assert W.frames(0.2) == 17 and W.frames(9) == 81


def test_nearest_aspect():
    sizes = W.WAN_SIZES["draft"]
    assert W.nearest_aspect(1344, 768, sizes) == "16:9"
    assert W.nearest_aspect(768, 1344, sizes) == "9:16"
    assert W.nearest_aspect(1000, 1010, sizes) == "1:1"
    assert W.nearest_aspect(320, 240, sizes) == "4:3"


def test_every_size_is_a_multiple_of_sixteen():
    for table in (W.CHROMA_SIZES, W.WAN_SIZES["draft"], W.WAN_SIZES["final"]):
        for w, h in table.values():
            assert w % 16 == 0 and h % 16 == 0, (w, h)



def test_gguf_chroma_files_use_the_gguf_loaders():
    import subprocess
    code = ("import json; from studio import workflows as W; "
            "print(json.dumps(W.chroma_t2i('a lighthouse', 1024, 1024)))")
    env = dict(os.environ, STUDIO_CHROMA_UNET="Chroma1-HD-Q6_K.gguf", STUDIO_CHROMA_CLIP="t5-v1_1-xxl-encoder-Q6_K.gguf")
    r = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(HERE), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    g = json.loads(r.stdout)
    assert g["1"] == {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "Chroma1-HD-Q6_K.gguf"}}, g["1"]
    assert g["2"] == {"class_type": "CLIPLoaderGGUF",
                      "inputs": {"clip_name": "t5-v1_1-xxl-encoder-Q6_K.gguf", "type": "chroma"}}, g["2"]
    assert g["5"]["inputs"]["model"] == ["1", 0] and g["3"]["inputs"]["clip"] == ["2", 0]


def test_the_server_keeps_its_safetensors_loaders():
    g = W.chroma_t2i("a lighthouse", 1024, 1024)
    assert g["1"]["class_type"] == "UNETLoader" and g["2"]["class_type"] == "CLIPLoader", (g["1"], g["2"])

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
