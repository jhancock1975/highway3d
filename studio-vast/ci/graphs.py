#!/usr/bin/env python3
"""Smoke-test helper, run inside the image: placeholder model files for the studio's two
ComfyUI graphs, and the graphs themselves as /prompt request bodies.

    graphs.py placeholders MODELS_DIR
    graphs.py prompt chroma|wan
"""
import json
import os
import sys

sys.path.insert(0, "/opt/highway3d")
from studio import workflows as W  # noqa: E402

if sys.argv[1] == "placeholders":
    for sub, names in (("diffusion_models", (W.CHROMA["unet"], W.WAN["high"], W.WAN["low"])),
                       ("text_encoders", (W.CHROMA["clip"], W.WAN["clip"])),
                       ("vae", (W.CHROMA["vae"], W.WAN["vae"]))):
        for name in names:
            path = os.path.join(sys.argv[2], sub, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "a").close()
else:
    graph = (W.chroma_t2i("a fox", 512, 512, count=2) if sys.argv[2] == "chroma"
             else W.wan_i2v("start.png", "she turns", 832, 480, 17))
    print(json.dumps({"prompt": graph}))
