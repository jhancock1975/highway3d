"""A lecture document from a topic, written by whatever model is to hand.

So a caller can ask for a video in one sentence. A small model driving
lectern from a phone gets one tool call per turn and a few hundred tokens to
make it in; eighty `lecture_add` calls is not something it can do, and a
whole YAML document is not something it can write in that room. So the
writing happens here instead, against a model this machine runs.

Any OpenAI-compatible chat endpoint works -- Ollama, LM Studio, llama.cpp,
an MLX server, or a hosted one:

    LECTERN_LLM_URL     default http://127.0.0.1:11434/v1  (Ollama)
    LECTERN_LLM_MODEL   default qwen3:8b
    LECTERN_LLM_KEY     sent as a bearer token if set

Ollama is the one exception to not caring which. It is asked through its own
API, because that is the only place it takes a context size and an unload,
and on a Mac that also holds the calling model and a render, both matter.

What comes back is checked by the same validator the renderer uses, and a
draft with problems goes back to the model with the problems attached. A
document that still fails after that is refused rather than rendered.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from lectern import script as S
from lectern.delivery import BEAT_NAMES

URL = os.environ.get("LECTERN_LLM_URL", "http://127.0.0.1:11434/v1")
MODEL = os.environ.get("LECTERN_LLM_MODEL", "qwen3:8b")
KEY = os.environ.get("LECTERN_LLM_KEY", "")

# Spoken rate the estimate in script.py uses, so the length asked for is the
# length that comes out.
WPM = 138.0


def brief(topic: str, minutes: float) -> str:
    words = int(minutes * WPM)
    segments = max(3, round(words / 45))
    demos = ", ".join(S.KNOWN_DEMOS)
    beats = ", ".join(BEAT_NAMES)
    return f"""Write a short lecture for an animated professor to deliver on camera.

Topic: {topic}
Length: {segments} segments, each 35 to 55 spoken words -- about {words} words in all.

Each segment is two to four sentences he says, plus ONE thing shown while he
says it. The things that can be shown:
  card:  {{"title": "...", "subtitle": "..."}}   a title card; use it for the first segment
  board: {{"heading": "...", "items": ["...", "..."]}}   two to four short written points
  note:  {{"heading": "...", "lines": ["..."]}}   a real formula from the subject, LaTeX in $...$
  demo:  "name"   a staged demonstration of special relativity: {demos}

Use a note only for an actual equation someone in the field would write
down; if the idea has no equation, use a board. Use a demo only when the
lecture is about relativity and that demonstration shows what is being said;
for any other subject, never use one.

Optional per segment: "beat", what his hands do as it opens, one of: {beats}.

Write it the way a warm, witty professor talks: plain words, short sentences,
one idea per segment, and a clear ending. Say the numbers and symbols out loud
in words -- the board shows them, the voice says them.

Reply with ONLY a JSON object, no commentary:
{{"title": "...",
  "chapters": [
    {{"title": "...",
      "segments": [
        {{"say": "Here is a question that sounds childish and is not. Why is the sky blue, and not white, or violet? The answer takes us from sunlight to the size of a molecule, and it is prettier than you expect.", "stage": {{"card": {{"title": "...", "subtitle": "..."}}}}}},
        {{"say": "...", "beat": "point", "stage": {{"board": {{"heading": "...", "items": ["...", "..."]}}}}}}
      ]}}
  ]}}"""


def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    if KEY:
        req.add_header("Authorization", f"Bearer {KEY}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _ollama() -> str:
    """Ollama's API root if URL is an Ollama, otherwise ''.

    Its /v1 layer answers the chat but ignores `keep_alive` and `options`, so
    it loads qwen3:8b at a 32k context and keeps it five minutes past the
    last request: 8 GB or more sitting through the render that follows.
    """
    base = re.sub(r"/v1/?$", "", URL.rstrip("/"))
    try:
        with urllib.request.urlopen(f"{base}/api/version", timeout=5) as r:
            return base if "version" in json.load(r) else ""
    except Exception:
        return ""


def _budget(prompt: str, minutes: float) -> tuple[int, int]:
    """The longest reply allowed, and a context that holds a retry of one.

    A retry carries the brief, the draft that failed and its problems, and
    still has to leave room for a new draft. qwen3:8b's replies ran 3.6
    tokens per spoken word once the JSON around them is counted, so four,
    and the thousand on top is for a model that overshoots.
    """
    reply = max(3000, int(minutes * WPM * 4) + 1000)
    need = len(prompt) // 3 + 2 * reply + 512
    return reply, -(-need // 1024) * 1024


def _ask(messages: list[dict], ollama: str, reply: int, ctx: int,
         timeout: float = 300) -> str:
    # No reasoning pass, and a ceiling on the reply: a thinking model left to
    # deliberate over a whole script ran past ten minutes and never answered,
    # and a tool call has to come back.
    if ollama:
        # keep_alive here is a backstop for a caller killed mid-write. The
        # unload that normally happens is _release, once the writing is done.
        r = _post(f"{ollama}/api/chat",
                  {"model": MODEL, "messages": messages, "stream": False,
                   "think": False, "format": "json", "keep_alive": "1m",
                   "options": {"temperature": 0.7, "num_predict": reply,
                               "num_ctx": ctx}}, timeout)
        return r["message"]["content"] or ""
    r = _post(f"{URL.rstrip('/')}/chat/completions",
              {"model": MODEL, "messages": messages,
               "temperature": 0.7, "stream": False,
               "reasoning_effort": "none", "max_tokens": reply,
               "response_format": {"type": "json_object"}}, timeout)
    return r["choices"][0]["message"]["content"] or ""


def _release(ollama: str) -> None:
    """Unload the model now, rather than when Ollama's keep_alive runs out.

    Left resident, qwen3:8b sat on 10-18 GB through the render that
    followed, and alongside Cider's 27B and Blender that ran a 36 GB Mac out
    of memory and into a watchdog panic.
    """
    if not ollama:
        return
    try:
        _post(f"{ollama}/api/generate", {"model": MODEL, "keep_alive": 0}, 10)
    except Exception:
        pass


def _json_in(text: str) -> dict:
    """The JSON object in a reply, past any reasoning a model printed first."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("the reply held no JSON object")
    body = text[start:end + 1]
    # LaTeX in the notation: `\gamma` is not an escape JSON knows, and a
    # model writing math inside a JSON string gets that wrong more often than
    # not. `\frac`, `\nu` and `\tau` even begin with letters JSON does treat
    # as escapes, and would quietly become control characters. So a backslash
    # stays an escape only when it is one on its own -- `\n` then a space, a
    # quote, `\u` and four hex digits -- and a backslash starting a word is
    # LaTeX and is doubled.
    # Pairs are consumed first, so LaTeX a model did escape is left alone.
    body = re.sub(r'\\\\|\\(?!["/]|u[0-9a-fA-F]{4}|[bfnrt](?![a-z]))',
                  lambda m: m.group(0) if len(m.group(0)) == 2 else "\\\\",
                  body)
    return json.loads(body)


def write(topic: str, minutes: float = 2.0, attempts: int = 4,
          presenter: str = "einstein", look: str = "study") -> dict:
    """A validated lecture document, or ValueError saying why there is none."""
    # Loaded once for every attempt, unloaded as soon as there is an answer.
    ollama = _ollama()
    try:
        return _write(topic, minutes, attempts, presenter, look, ollama)
    finally:
        _release(ollama)


def _write(topic: str, minutes: float, attempts: int,
           presenter: str, look: str, ollama: str) -> dict:
    prompt = brief(topic, minutes)
    reply_limit, ctx = _budget(prompt, minutes)
    messages = [{"role": "user", "content": prompt}]
    problems: list[str] = []
    for _ in range(attempts):
        try:
            reply = _ask(messages, ollama, reply_limit, ctx)
        except (urllib.error.URLError, OSError) as e:
            raise ValueError(
                f"the model at {URL} ({MODEL}) could not be reached: {e}. "
                f"Start one (for example `ollama serve`) or point "
                f"LECTERN_LLM_URL at another OpenAI-compatible endpoint.")
        try:
            raw = _json_in(reply)
            raw.update(presenter=presenter, look=look)
            doc = S.normalise(raw)
            problems = S.validate(doc)
            if not S.segments(doc):
                problems = ["it has no segments"]
            # Small models write about a third of the length asked for, and
            # a two-minute request that comes back as forty seconds is not
            # what was asked for.
            want, got = int(minutes * WPM), S.word_count(doc)
            if got < 0.75 * want:
                problems.append(
                    f"it is {got} spoken words and it needs about {want}: "
                    f"add segments and say more in each one, keeping every "
                    f"segment one to three sentences")
        except Exception as e:
            problems = [f"it could not be read: {e}"]
        if not problems:
            return doc
        # Only the latest draft goes back. The earlier ones are superseded,
        # and carrying them all grows the context, and its memory, every try.
        messages = messages[:1] + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content":
             "That has problems:\n- " + "\n- ".join(problems[:10])
             + "\nFix them and reply with the whole JSON object again."}]
    raise ValueError("the model could not write a valid lecture: "
                     + "; ".join(problems[:5]))
