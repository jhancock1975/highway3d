"""The xAI client against a fake server: requests, replies and every failure.

    studio/.venv/bin/python studio/test_xai.py

No credit is spent here. Task 10 makes one real picture once a key exists.
"""

import base64
import io
import json
import os
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import xai as X  # noqa: E402

KEY = "xai-secret-never-shown"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake(status=200, body=None, sent=None):
    def opener(req, timeout=0):
        if sent is not None:
            sent.append((req.full_url, json.loads(req.data), dict(req.header_items())))
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "no", {},
                                         io.BytesIO(json.dumps(body).encode()))
        return Reply(json.dumps(body).encode())
    return opener


OK = {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}


def test_no_key_is_a_sentence():
    try:
        X.image("a fox", key="")
    except X.Refused as e:
        assert str(e) == "No xAI key is set; put XAI_API_KEY in the environment the studio server runs in."
    else:
        raise AssertionError("no key, and yet a picture")


def test_generation_request_shape():
    sent = []
    data = X.image("a fox", "9:16", "1k", key=KEY, opener=fake(body=OK, sent=sent))
    assert data == PNG
    url, body, headers = sent[0]
    assert url.endswith("/images/generations"), url
    assert body == dict(model=X.MODEL, prompt="a fox", n=1, aspect_ratio="9:16",
                        resolution="1k", response_format="b64_json"), body
    assert headers["Authorization"] == f"Bearer {KEY}"


def test_references_use_the_edits_endpoint():
    ref = os.path.join(tempfile.mkdtemp(), "layout.png")
    with open(ref, "wb") as fh:
        fh.write(PNG)
    sent = []
    X.image("repaint this", references=[ref], key=KEY, opener=fake(body=OK, sent=sent))
    url, body, _ = sent[0]
    assert url.endswith("/images/edits"), url
    assert body["images"][0]["type"] == "image_url"
    assert body["images"][0]["url"].startswith("data:image/png;base64,")


def test_failures_say_which_kind():
    cases = [
        (402, {"error": "Payment required"}, "The xAI credits are used up; add more at console.x.ai."),
        (403, {"error": "Your team has run out of credits"}, "The xAI credits are used up; add more at console.x.ai."),
        (401, {"error": "Incorrect API key provided"}, "xAI refused the key (HTTP 401): Incorrect API key provided"),
        (400, {"error": "Generated image rejected by content moderation"},
         "xAI refused the prompt: Generated image rejected by content moderation"),
        (500, {"error": "boom"}, "xAI answered HTTP 500: boom"),
    ]
    for status, body, want in cases:
        try:
            X.image("a fox", key=KEY, opener=fake(status, body))
        except X.Refused as e:
            assert str(e) == want, (status, str(e))
            assert KEY not in str(e)
        else:
            raise AssertionError(f"HTTP {status} made a picture")


def test_reply_without_a_picture():
    try:
        X.image("a fox", key=KEY, opener=fake(body={"data": []}))
    except X.Refused as e:
        assert str(e) == "xAI answered without a picture in the reply."
    else:
        raise AssertionError("an empty reply made a picture")


def test_extension_from_bytes():
    assert X.extension(PNG) == ".png"
    assert X.extension(b"\xff\xd8\xff\xe0") == ".jpg"
    assert X.extension(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ".webp"


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
