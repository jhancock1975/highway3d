"""The two ComfyUI graphs the studio runs, in ComfyUI's API format.

Both were checked against ComfyUI v0.38.0's /prompt validation and use only
core nodes, so nothing beyond vast's ComfyUI image is needed:

- keyframes: Chroma1-HD (Apache-2.0), as in its author's reference workflow
  (lodestones/Chroma1-HD@0e0c60ec): T5 tokenizer padding 0, AuraFlow shift 1,
  26 steps of euler/beta at CFG 3.8. Without the AuraFlow node ComfyUI falls
  back to Chroma's Flux-style shift of 1.15, a different schedule.
- animation: Wan2.2-Remix NSFW image-to-video v3.0 (FX-FeiHou/wan2.2-Remix),
  with the lightx2v four-step LoRAs already merged in, so none is added: 8
  steps split 4/4 between the high- and low-noise experts, CFG 1, shift 8,
  16 frames a second, saved as h264 at CRF 19 like the author's workflow.
"""

from __future__ import annotations

import math

CHROMA = dict(unet="Chroma1-HD.safetensors", clip="t5xxl_enconly.safetensors",
              vae="Flux/ae.safetensors")
WAN = dict(high="Wan2.2_Remix_NSFW_i2v_14b_high_lighting_fp8_e4m3fn_v3.0.safetensors",
           low="Wan2.2_Remix_NSFW_i2v_14b_low_lighting_fp8_e4m3fn_v3.0.safetensors",
           clip="nsfw_wan_umt5-xxl_fp8_scaled.safetensors",
           vae="wan_2.1_vae.safetensors")
FPS = 16
MAX_SECONDS = 5

CHROMA_NEGATIVE = (
    "This greyscale unfinished sketch has bad proportions, is featureless and disfigured. "
    "It is a blurry ugly mess and with excessive gaussian blur. It is riddled with watermarks "
    "and signatures. Everything is smudged with leaking colors and nonsensical orientation of "
    "objects. Messy and abstract image filled with artifacts disrupt the coherency of the overall "
    "composition. The image has extreme chromatic abberations and inconsistent lighting. Dull, "
    "monochrome colors and countless artistic errors.")
# Wan's own standard negative prompt, in the Chinese it was trained with.
WAN_NEGATIVE = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，"
                "JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，"
                "形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")

# About a megapixel at each shape, every side a multiple of 16.
CHROMA_SIZES = {"1:1": (1024, 1024), "16:9": (1344, 768), "9:16": (768, 1344),
                "4:3": (1152, 896), "3:4": (896, 1152), "3:2": (1216, 832),
                "2:3": (832, 1216), "21:9": (1536, 640)}
# Wan 2.2 14B is trained at 480p and 720p.
WAN_SIZES = {
    "draft": {"16:9": (832, 480), "9:16": (480, 832), "1:1": (640, 640),
              "4:3": (736, 544), "3:4": (544, 736)},
    "final": {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (960, 960),
              "4:3": (1088, 832), "3:4": (832, 1088)},
}
CHROMA_LABELS = {"9": "painting", "10": "decoding the picture"}
WAN_LABELS = {"8": "preparing the start frame", "11": "high-noise pass",
              "12": "low-noise pass", "13": "decoding frames", "15": "writing the video"}


def frames(seconds: float) -> int:
    """Wan's frame count for a clip this long: 16 a second plus the start frame, 1 to 5 seconds."""
    s = max(1, min(MAX_SECONDS, round(float(seconds))))
    return FPS * s + 1


def nearest_aspect(width: int, height: int, table: dict) -> str:
    """The key of `table` whose shape is closest to width x height."""
    want = math.log(width / height)
    return min(table, key=lambda k: abs(math.log(table[k][0] / table[k][1]) - want))


def chroma_t2i(prompt: str, width: int, height: int, count: int = 1, seed: int = 0,
               negative: str = "", prefix: str = "studio/pic") -> dict:
    """Text to `count` pictures with Chroma1-HD."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": CHROMA["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CHROMA["clip"], "type": "chroma", "device": "default"}},
        "3": {"class_type": "T5TokenizerOptions", "inputs": {"clip": ["2", 0], "min_padding": 0, "min_length": 0}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": CHROMA["vae"]}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 1.0}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or CHROMA_NEGATIVE, "clip": ["3", 0]}},
        "8": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": count}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["5", 0], "seed": seed, "steps": 26, "cfg": 3.8,
                                                   "sampler_name": "euler", "scheduler": "beta",
                                                   "positive": ["6", 0], "negative": ["7", 0],
                                                   "latent_image": ["8", 0], "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": prefix}},
    }


def wan_i2v(image: str, prompt: str, width: int, height: int, length: int, seed: int = 0,
            negative: str = "", prefix: str = "studio/clip") -> dict:
    """A start frame (a name in ComfyUI's input folder) to `length` frames of video."""
    sampler = {"cfg": 1.0, "steps": 8, "sampler_name": "euler", "scheduler": "simple",
               "noise_seed": seed, "positive": ["8", 0], "negative": ["8", 1]}
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": WAN["high"], "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": WAN["low"], "weight_dtype": "fp8_e4m3fn"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": WAN["clip"], "type": "wan", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": WAN["vae"]}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or WAN_NEGATIVE, "clip": ["3", 0]}},
        "8": {"class_type": "WanImageToVideo", "inputs": {"positive": ["6", 0], "negative": ["7", 0], "vae": ["4", 0],
                                                          "start_image": ["5", 0], "width": width, "height": height,
                                                          "length": length, "batch_size": 1}},
        "9": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 8.0}},
        "11": {"class_type": "KSamplerAdvanced", "inputs": dict(sampler, model=["9", 0], add_noise="enable",
                                                                latent_image=["8", 2], start_at_step=0, end_at_step=4,
                                                                return_with_leftover_noise="enable")},
        "12": {"class_type": "KSamplerAdvanced", "inputs": dict(sampler, model=["10", 0], add_noise="disable",
                                                                latent_image=["11", 0], start_at_step=4,
                                                                end_at_step=10000,
                                                                return_with_leftover_noise="disable")},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": float(FPS), "bit_depth": "auto",
                                                       "color_space": "sRGB", "codec": "none"}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": prefix, "format": "mp4",
                                                     "format.codec": "h264", "format.codec.encoding": "re-encode",
                                                     "format.codec.encoding.crf": 19.0, "codec": "auto"}},
    }
