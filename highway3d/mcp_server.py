"""MCP server in front of the highway renderer.

Exposes describe / preview / render over streamable HTTP so other agents can
drive the renderer without shelling out to Python themselves.

    .mcpvenv/bin/python mcp_server.py --port 8766

Everything goes through toon.py rather than importing scene.py, so the CLI
stays the single source of truth for the option contract: change an option
there and it shows up here without edits.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Annotated, Literal

from pydantic import Field

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))

from forgiving import ForgivingServer  # noqa: E402

TOON = os.path.join(HERE, "toon.py")
OUT_DIR = os.environ.get("HIGHWAY_OUT_DIR", os.path.join(HERE, "..", "renders"))
OUT_DIR = os.path.abspath(OUT_DIR)

LOOKS = ("day", "golden", "dusk", "night")
CAMERAS = ("driver", "bumper", "chase")
STYLES = ("soft", "toon")

mcp = ForgivingServer(
    name="highway3d",
    title="Highway drive renderer",
    version="1.0.0",
    instructions=(
        "Renders cartoonish-realistic highway driving footage: a curving dual "
        "carriageway with simulated traffic, at day, golden hour, dusk or "
        "night. Call highway_describe first if you need the full option list. "
        "Use highway_preview to check a look cheaply before committing to "
        "highway_render, which takes minutes."
    ),
)


def _run(args: list[str], timeout: float) -> dict:
    """Invoke toon.py and parse its single JSON object."""
    cmd = [sys.executable if os.path.basename(sys.executable).startswith("python")
           else "python3", TOON] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"render exceeded {timeout / 60:.0f} minutes and was stopped; "
            "ask for a shorter duration, fewer samples or a smaller frame")
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        raise RuntimeError("renderer failed: " + (msg[-1] if msg else "unknown"))
    text = r.stdout.strip()
    # describe pretty-prints over many lines; preview and render emit one line
    for candidate in (text, text.splitlines()[-1] if text else ""):
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    raise RuntimeError("renderer produced no JSON result")


def _estimate_seconds(width: int, height: int, duration: float, fps: int,
                      samples: int) -> float:
    """Rough wall-clock estimate. Calibrated on an M-series GPU at 1080p."""
    px = (width * height) / (1920 * 1080)
    return 30.0 + duration * fps * 1.55 * px * (samples / 96.0)


def _stamp(prefix: str, ext: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    return os.path.join(OUT_DIR, f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}{ext}")


@mcp.tool()
def highway_describe() -> str:
    """Full option contract for the highway renderer, as JSON.

    Lists every option with its type, default, allowed range or enumerated
    choices, plus worked examples. Call this when you need an option that
    highway_render and highway_preview do not expose directly.
    """
    out = _run(["describe"], timeout=60)
    return json.dumps(out, indent=2)


@mcp.tool()
def highway_preview(
    look: Annotated[Literal[LOOKS], Field(
        description="Time of day. Sets sun angle, sky, haze; dusk and night "
                    "light the lamps, headlights and stars.")] = "day",
    camera: Annotated[Literal[CAMERAS], Field(
        description="driver = eye height; bumper = low and fast; chase = "
                    "behind a lead car.")] = "driver",
    at: Annotated[str, Field(
        description="Comma-separated timestamps in seconds to sample, e.g. "
                    "'2,8,14'. Each becomes one frame in a side-by-side "
                    "contact sheet.")] = "2,8,14",
    style: Annotated[Literal[STYLES], Field(
        description="soft = physically lit, rounded forms, filmic tonemapping "
                    "(feature-animation look). toon = hard cel bands over the "
                    "same geometry.")] = "soft",
    traffic: Annotated[float, Field(
        ge=0.0, le=3.0,
        description="Vehicle density multiplier. 0 is an empty road.")] = 1.0,
    width: Annotated[int, Field(ge=256, le=3840)] = 1280,
    height: Annotated[int, Field(ge=144, le=2160)] = 720,
) -> str:
    """Render a cheap still contact sheet to check a look before committing.

    look is day (the default), golden, dusk or night; camera is driver (the
    default), bumper or chase; style is soft (the default) or toon; traffic
    is 0 (an empty road) to 3, 1 by default. Takes a few
    seconds, against minutes for highway_render. Use this to confirm time of
    day, camera and traffic density are what the user wants. Returns the
    absolute path of a PNG.
    """
    out = _stamp(f"preview-{look}-{camera}", ".png")
    res = _run(["preview", "--out", out, "--at", at, "--look", look,
                "--camera", camera, "--style", style,
                "--traffic", str(traffic),
                "--width", str(width), "--height", str(height)], timeout=900)
    n = len([x for x in at.split(",") if x.strip()])
    return (f"Wrote a {n}-frame contact sheet to {res['out']}\n"
            f"{look} light, {camera} camera, {style} style, traffic {traffic}, "
            f"{width}x{height}, {res.get('seconds', '?')}s to render.")


@mcp.tool()
def highway_render(
    look: Annotated[Literal[LOOKS], Field(
        description="Time of day. Sets sun angle, sky, haze; dusk and night "
                    "light the lamps, headlights and stars.")] = "day",
    camera: Annotated[Literal[CAMERAS], Field(
        description="driver = eye height; bumper = low and fast; chase = "
                    "behind a lead car.")] = "driver",
    duration: Annotated[float, Field(
        ge=1.0, le=60.0,
        description="Clip length in seconds. Render time scales with this; "
                    "8 seconds at the defaults takes roughly 4 minutes.")] = 8.0,
    style: Annotated[Literal[STYLES], Field(
        description="soft = physically lit, rounded forms, filmic tonemapping "
                    "(feature-animation look). toon = hard cel bands over the "
                    "same geometry.")] = "soft",
    traffic: Annotated[float, Field(
        ge=0.0, le=3.0,
        description="Vehicle density multiplier. 0 is an empty road.")] = 1.0,
    speed: Annotated[float, Field(
        ge=5.0, le=70.0,
        description="Camera speed in m/s. 31 is about 112 km/h.")] = 31.0,
    width: Annotated[int, Field(ge=256, le=3840)] = 1920,
    height: Annotated[int, Field(ge=144, le=2160)] = 1080,
    fps: Annotated[int, Field(ge=12, le=120)] = 60,
    samples: Annotated[int, Field(
        ge=8, le=256,
        description="Render samples per frame. 64 is converged for this "
                    "scene; more mainly costs time.")] = 64,
    seed: Annotated[int, Field(
        ge=0, le=2 ** 31 - 1,
        description="Changes traffic layout, roadside planting and road "
                    "shape. Same seed and options reproduce a clip exactly."
    )] = 7,
) -> str:
    """Render a highway driving clip to an H.264 mp4.

    look is day (the default), golden, dusk or night; camera is driver (eye
    height, the default), bumper (low and fast) or chase (behind a lead car);
    style is soft (the default) or toon; duration is seconds, 1 to 60, 8 by
    default; traffic is 0 (an empty road) to 3, 1 by default.

    This takes minutes, not seconds: about 4 minutes for 8 seconds of 1080p60
    at the defaults, scaling with duration, frame size and samples. Preview
    first with highway_preview if the look is not already settled.

    Traffic is simulated, so vehicles keep a real following distance and never
    pass through one another. Returns the absolute path of the finished mp4.
    """
    est = _estimate_seconds(width, height, duration, fps, samples)
    if est > 18 * 60:
        return (f"Refusing to start: this would take roughly {est / 60:.0f} "
                f"minutes, beyond a typical call timeout. Reduce duration "
                f"({duration}s), frame size ({width}x{height}) or samples "
                f"({samples}) and try again.")
    out = _stamp(f"highway-{look}-{camera}", ".mp4")
    res = _run(["render", "--out", out, "--look", look, "--camera", camera,
                "--duration", str(duration), "--style", style,
                "--traffic", str(traffic), "--speed", str(speed),
                "--width", str(width), "--height", str(height),
                "--fps", str(fps), "--samples", str(samples),
                "--seed", str(seed)], timeout=19 * 60)
    mb = res.get("bytes", 0) / 1e6
    return (f"Rendered {res['out']}\n"
            f"{duration:g}s of {look} driving from the {camera} camera, "
            f"{style} style, {res['width']}x{res['height']} at {res['fps']}fps, "
            f"{res['frames']} frames, {mb:.1f} MB. "
            f"Took {res.get('render_seconds', '?')}s.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--path", default="/mcp")
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"highway3d MCP on http://{a.host}:{a.port}{a.path} "
          f"-> {OUT_DIR}", flush=True)
    import anyio
    anyio.run(lambda: mcp.run_streamable_http_async(
        host=a.host, port=a.port, streamable_http_path=a.path))


if __name__ == "__main__":
    main()
