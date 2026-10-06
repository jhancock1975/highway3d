"""
title: Studio
author: jhancock1975
description: Follows studio jobs with live progress, and shows pictures, clips, sound and finished films in the chat.
version: 1.0.0
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
import subprocess
import time
import urllib.parse

from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ID = re.compile(r"^[a-z]+-[0-9a-z]{4}$")
VIDEO = (".mp4", ".webm", ".mov", ".mkv")
IMAGE = (".png", ".jpg", ".jpeg", ".webp")
STYLE = (
    "<style>body{margin:0;background:#151515;color:#ddd;font:14px system-ui,sans-serif}"
    ".grid{display:flex;flex-wrap:wrap;gap:10px;padding:8px}figure{margin:0}"
    "figure img,figure video{max-width:min(100%,640px);max-height:480px;border-radius:6px;display:block}"
    "figcaption{padding:4px 2px;color:#aaa}figcaption b{color:#fff}"
    "</style>"
)
GRACE = 10  # seconds a job's process gets to appear after its log is written


def _alive(job: str) -> bool:
    """Whether a studio job's process is still running on this machine."""
    r = subprocess.run(["ps", "-A", "-ww", "-o", "args="], capture_output=True, text=True)
    return f"--job {job}" in r.stdout


def _read(log: str):
    with open(log) as fh:
        lines = [x.strip() for x in fh if x.strip()]
    head = {}
    if lines and lines[0].startswith("JOB "):
        try:
            head = json.loads(lines[0][4:])
        except ValueError:
            pass
    tail = next((x for x in reversed(lines) if x.startswith(("PROGRESS", "DONE", "FAILED"))), "")
    return head, tail


def _kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return "video" if ext in VIDEO else "image" if ext in IMAGE else "audio"


def _describe(n: dict) -> str:
    kind = n.get("kind") or _kind(n["path"])
    if kind == "image" and n.get("width"):
        return f"picture, {n['width']}x{n['height']}"
    if kind == "video" and n.get("seconds"):
        return f"clip, {n['seconds']:.1f} s" + (f", {n['width']}x{n['height']}" if n.get("width") else "")
    if kind == "audio" and n.get("seconds"):
        return f"sound, {n['seconds']:.1f} s"
    return kind


async def _noop(event):
    return None


class Tools:
    class Valves(BaseModel):
        work_dir: str = Field(default=os.environ.get("STUDIO_WORK", "/workspace/studio/work"),
                              description="Where studio jobs write their logs.")
        static_dir: str = Field(default=os.environ.get("STATIC_DIR", "/workspace/studio-webui/static"),
                                description="Open WebUI's static folder; the library and renders are in studio/.")
        poll_seconds: float = Field(default=2.0, description="How often a watched job is checked.")
        max_minutes: int = Field(default=60, description="How long watch_job follows one job.")

    def __init__(self):
        self.valves = self.Valves()

    # ----------------------------------------------------------- helpers

    def _media(self) -> str:
        return os.path.join(self.valves.static_dir, "studio", "media")

    def _renders(self) -> str:
        return os.path.join(self.valves.static_dir, "studio", "renders")

    def _url(self, path: str):
        """The /static URL of a file under the static folder; None for anything outside it."""
        root = os.path.realpath(self.valves.static_dir)
        real = os.path.realpath(path)
        if not real.startswith(root + os.sep) or not os.path.isfile(real):
            return None
        rel = os.path.relpath(real, root)
        return "/static/" + "/".join(urllib.parse.quote(p) for p in rel.split(os.sep))

    def _find(self, ref: str):
        ref = ref.strip().strip(",;")
        if ID.match(ref):
            p = os.path.join(self._media(), ref + ".json")
            if os.path.exists(p):
                with open(p) as fh:
                    return json.load(fh)
            return None
        name = os.path.basename(ref)
        for folder in (self._renders(), self._media()):
            p = os.path.join(folder, name)
            if os.path.isfile(p):
                return {"id": name, "path": p, "kind": _kind(p)}
        return None

    def _figure(self, n: dict) -> str:
        url = html.escape(self._url(n["path"]) or "")
        kind = n.get("kind") or _kind(n["path"])
        if kind == "image":
            media = f'<img src="{url}" alt="{html.escape(n["id"])}">'
        elif kind == "video":
            media = f'<video src="{url}" controls loop playsinline preload="metadata"></video>'
        else:
            media = f'<audio src="{url}" controls preload="metadata"></audio>'
        return (f"<figure>{media}<figcaption><b>{html.escape(n['id'])}</b> "
                f"{html.escape(_describe(n))}</figcaption></figure>")

    @staticmethod
    def _page(body: str) -> HTMLResponse:
        return HTMLResponse(content=f"<!doctype html><html><head><meta charset='utf-8'>{STYLE}</head>"
                                    f"<body>{body}</body></html>",
                            headers={"Content-Disposition": "inline"})

    @staticmethod
    def _meter(percent) -> str:
        """A text progress bar for the status line, such as '▰▰▰▰▰▱▱▱▱▱ 50%'."""
        if percent is None:
            return ""
        filled = max(0, min(10, round(percent / 10)))
        return " " + "\u25b0" * filled + "\u25b1" * (10 - filled) + f" {percent:.0f}%"

    # ------------------------------------------------------------- tools

    async def show(self, items: str, __event_emitter__=None):
        """
        Show pictures, clips, sounds or finished films in the chat, side by side with their ids, so they can be looked at and chosen from.
        :param items: Asset ids such as pic-3f2a, clip-9c01, voice-1a2b or music-77e1, or the file names of finished films, separated by commas or spaces.
        """
        found, missing = [], []
        for ref in [r for r in re.split(r"[,\s]+", items or "") if r]:
            n = self._find(ref)
            if n and self._url(n["path"]):
                found.append(n)
            else:
                missing.append(ref)
        if not found:
            names = ", ".join(missing) or "nothing was named"
            return f"Nothing to show: {names} {'is' if len(missing) == 1 else 'are'} not in the library or the finished films."
        body = "<div class='grid'>" + "".join(self._figure(n) for n in found) + "</div>"
        text = "Shown in the chat: " + "; ".join(f"{n['id']} ({_describe(n)})" for n in found)
        if missing:
            text += f". Not found: {', '.join(missing)}."
        return (self._page(body), text)

    async def watch_job(self, job: str, __event_emitter__=None):
        """
        Follow a studio job (an animation, extension, composed music or assembly) and show its progress live in the chat until it finishes, then show what it made. Call it right after a studio tool says it started a job.
        :param job: The job id the studio tool gave, such as 1a2b3c.
        """
        emit = _noop if __event_emitter__ is None else __event_emitter__
        job = (job or "").strip()
        log = os.path.join(self.valves.work_dir, f"job-{job}.log")
        if not re.fullmatch(r"\w+", job) or not os.path.exists(log):
            return f"There is no studio job {job}; studio_status lists the recent ones."
        began, last = time.time(), None
        name = f"Job {job}"
        while time.time() - began < self.valves.max_minutes * 60:
            head, tail = _read(log)
            name = head.get("name") or name
            if tail.startswith("DONE"):
                d = json.loads(tail[4:])
                await emit({"type": "status", "data": {"description": f"{name}: finished", "done": True}})
                n = self._find(d["asset"]) if d.get("asset") else self._find(d.get("out", ""))
                if n and self._url(n["path"]):
                    return (self._page("<div class='grid'>" + self._figure(n) + "</div>"),
                            f"Job {job} finished: {n['id']} ({_describe(n)}), shown in the chat.")
                return f"Job {job} finished: {d.get('out')}."
            if tail.startswith("FAILED"):
                await emit({"type": "status", "data": {"description": f"{name}: failed", "done": True}})
                return f"Job {job} failed: {tail[6:].strip()}"
            if not _alive(job) and time.time() - os.path.getmtime(log) > GRACE:
                await emit({"type": "status", "data": {"description": f"{name}: stopped", "done": True}})
                return (f"Job {job} stopped before it finished: its process is gone, most likely "
                        f"because the machine restarted. Starting the same work again starts it over.")
            stage, percent = "started", None
            if tail.startswith("PROGRESS"):
                d = json.loads(tail[8:])
                stage, percent = d.get("stage", stage), d.get("percent")
            # Progress lives in the status line only. An embedded frame redrawn on every update
            # collapses and regrows, and the chat jumps while the person is scrolling.
            if (stage, percent) != last:
                last = (stage, percent)
                await emit({"type": "status",
                            "data": {"description": f"{name}: {stage}{self._meter(percent)}", "done": False}})
            await asyncio.sleep(self.valves.poll_seconds)
        return (f"Job {job} is still running after {self.valves.max_minutes} minutes; "
                f"call watch_job again to keep following it.")
