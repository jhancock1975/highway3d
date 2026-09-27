"""Pictures from xAI's image model, paid for from prepaid credit.

Reads XAI_API_KEY from the environment and nowhere else, and never writes
it anywhere: not to a log, a note or a result. Every failure is a sentence
that says which kind it is, because "the credits are used up" and "that
prompt was refused" call for different things from whoever asked.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("STUDIO_XAI_URL", "https://api.x.ai/v1")
MODEL = "grok-imagine-image-2.0"
ASPECTS = ("16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9", "auto")
RESOLUTIONS = ("1k", "1.5k", "2k")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp"}


class Refused(Exception):
    """xAI did not make the picture; the message says why, in a sentence."""


def extension(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def _data_uri(path: str) -> str:
    with open(path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode()
    mime = MIME.get(os.path.splitext(path)[1].lower(), "image/png")
    return f"data:{mime};base64,{encoded}"


def _why(code: int, text: str) -> str:
    try:
        message = json.loads(text).get("error", text)
    except (ValueError, AttributeError):
        message = text
    if isinstance(message, dict):
        message = message.get("message", json.dumps(message))
    message = " ".join(str(message).split())[:300]
    low = message.lower()
    if code == 402 or any(w in low for w in ("credit", "balance",
                                             "spending limit", "insufficient")):
        return "The xAI credits are used up; add more at console.x.ai."
    if code == 401 or (code == 403 and ("key" in low or "auth" in low)):
        return f"xAI refused the key (HTTP {code}): {message}"
    if code == 400 and any(w in low for w in ("policy", "moderation", "safety",
                                              "not allowed")):
        return f"xAI refused the prompt: {message}"
    return f"xAI answered HTTP {code}: {message}"


def image(prompt: str, aspect: str = "16:9", resolution: str = "2k",
          references=(), key: str | None = None,
          opener=urllib.request.urlopen) -> bytes:
    """One picture's bytes, or Refused with a sentence saying why not."""
    key = os.environ.get("XAI_API_KEY", "") if key is None else key
    if not key:
        raise Refused("No xAI key is set; put XAI_API_KEY in the environment "
                      "the studio server runs in.")
    body = dict(model=MODEL, prompt=prompt, n=1, aspect_ratio=aspect,
                resolution=resolution, response_format="b64_json")
    path = "/images/generations"
    if references:
        body["images"] = [dict(type="image_url", url=_data_uri(p))
                          for p in references]
        path = "/images/edits"
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with opener(req, timeout=300) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as e:
        raise Refused(_why(e.code, e.read().decode(errors="replace"))) from None
    except (urllib.error.URLError, OSError) as e:
        raise Refused(f"Could not reach xAI: {getattr(e, 'reason', e)}.") from None
    try:
        return base64.b64decode(reply["data"][0]["b64_json"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise Refused("xAI answered without a picture in the reply.") from None
