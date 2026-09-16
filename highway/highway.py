#!/usr/bin/env python3
"""highway.py - procedural highway-drive video renderer.

No 3D application required. A small software renderer (perspective projection,
near-plane clipping, painter's-algorithm depth sorting, Newell face normals with
sun + sky + bounce lighting, projected ground shadows) draws each frame with
Pillow and pipes raw RGB frames straight into ffmpeg, so nothing hits the disk
between the renderer and the encoder. Flat-shaded on purpose: believable light
and motion, animated surfaces.

    python3 highway.py describe                           # options, as JSON
    python3 highway.py preview --out look.png --at 2,8,14  # cheap contact sheet
    python3 highway.py render  --out drive.mp4 --duration 20

`render` needs ffmpeg on PATH. Pillow and numpy are installed into a .venv
beside this file on first run, and the process re-execs into it.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, fields
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"


def _ensure_deps() -> None:
    """Import Pillow/numpy, building a private venv and re-execing if needed."""
    try:
        import PIL  # noqa: F401
        import numpy  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get("HIGHWAY_BOOTSTRAPPED") == "1":
        sys.exit("highway: pillow/numpy still missing after bootstrap; "
                 "install them manually: pip install pillow numpy")
    py = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        print(f"highway: creating {VENV} (pillow, numpy)", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
        subprocess.check_call([str(py), "-m", "pip", "install", "-q", "pillow", "numpy"])
    env = dict(os.environ, HIGHWAY_BOOTSTRAPPED="1")
    os.execve(str(py), [str(py), str(Path(__file__).resolve()), *sys.argv[1:]], env)


_ensure_deps()

import numpy as np                                      # noqa: E402
from PIL import Image, ImageChops, ImageDraw, ImageFilter  # noqa: E402


# --------------------------------------------------------------------------- config
@dataclass
class Config:
    out: str = "drive.mp4"
    width: int = 1280
    height: int = 720
    fps: int = 60
    duration: float = 20.0
    seed: int = 7
    look: str = "day"
    camera: str = "driver"
    lane: int = 2
    lanes: int = 3
    speed_kmh: float = 112.0
    traffic: float = 1.0
    trees: float = 1.0
    curve: float = 1.0
    hills: float = 1.0
    fog: float = 0.0           # 0 = use the look's own haze distance
    motion_blur: int = 2       # sub-samples per frame; 1 = off
    detail: float = 1.0        # surface mottling / tar seams / joints
    supersample: int = 2
    quality: int = 18
    threads: int = 0           # 0 = cpu_count - 2


# Single source of truth for the CLI and for `describe`.
SPEC = [
    ("out", "path", None, None, "Output file. .mp4 for render, .png for preview."),
    ("width", "int", (256, 3840), None, "Frame width in pixels."),
    ("height", "int", (144, 2160), None, "Frame height in pixels."),
    ("fps", "int", (12, 120), None, "Frames per second."),
    ("duration", "float", (0.5, 600.0), None, "Clip length in seconds."),
    ("seed", "int", (0, 2**31 - 1), None, "Changes traffic layout and roadside scenery."),
    ("look", "str", None, ["day", "golden", "dusk", "night"],
     "Time of day. Sets sun angle, palette, haze; dusk/night light the lamps."),
    ("camera", "str", None, ["driver", "bumper", "chase"],
     "driver = eye height; bumper = low and fast; chase = behind a lead car."),
    ("lane", "int", (1, 6), None, "Which lane the camera travels in, 1 = leftmost."),
    ("lanes", "int", (1, 5), None, "Lanes per carriageway."),
    ("speed_kmh", "float", (20.0, 250.0), None, "Camera speed; traffic scales with it."),
    ("traffic", "float", (0.0, 3.0), None, "Vehicle density multiplier. 0 = empty road."),
    ("trees", "float", (0.0, 3.0), None, "Roadside planting density."),
    ("curve", "float", (0.0, 3.0), None, "Horizontal curvature. 0 = dead straight."),
    ("hills", "float", (0.0, 3.0), None, "Vertical undulation. 0 = flat."),
    ("fog", "float", (0.0, 2000.0), None, "Haze half-distance in metres. 0 = look default."),
    ("motion_blur", "int", (1, 6), None,
     "Sub-samples averaged per frame. 1 = off (crisp), 2-3 = filmic. Cost scales with it."),
    ("detail", "float", (0.0, 2.0), None,
     "Asphalt mottling, tar seams, expansion joints, grass patchiness. 0 = flat colours."),
    ("supersample", "int", (1, 3), None, "Antialiasing factor. 2 is a good default, 3 is slow."),
    ("quality", "int", (0, 51), None, "x264 CRF. Lower is better quality and bigger."),
    ("threads", "int", (0, 64), None, "Worker processes. 0 = cpu_count - 2."),
]
assert {s[0] for s in SPEC} == {f.name for f in fields(Config)}, "SPEC/Config drift"


@dataclass
class Look:
    sky_top: tuple
    sky_horizon: tuple
    fog_color: tuple
    fog_dist: float
    sun_az: float          # degrees; 0 = straight ahead, negative = to the left
    sun_el: float          # degrees above the horizon; <= 0 disables sun + shadows
    sun_col: tuple
    sun_str: float
    sky_col: tuple
    sky_str: float
    gnd_col: tuple
    gnd_str: float
    exposure: float
    shadow: tuple          # rgba painted into the shadow layer
    cloud: tuple
    lamps: bool
    stars: bool
    beam: float
    sat: float
    contrast: float
    bloom: float
    grain: float


LOOKS = {
    "day": Look(
        sky_top=(44, 96, 178), sky_horizon=(196, 214, 232), fog_color=(186, 205, 226),
        fog_dist=340.0, sun_az=-48.0, sun_el=44.0,
        sun_col=(1.30, 1.22, 1.02), sun_str=0.80,
        sky_col=(0.72, 0.79, 0.98), sky_str=0.68,
        gnd_col=(0.54, 0.52, 0.44), gnd_str=0.26,
        exposure=1.07, shadow=(26, 34, 58, 78), cloud=(255, 255, 255, 30),
        lamps=False, stars=False, beam=0.0, sat=1.12, contrast=1.05, bloom=0.16, grain=1.8),
    "golden": Look(
        sky_top=(40, 96, 180), sky_horizon=(252, 214, 162), fog_color=(240, 204, 158),
        fog_dist=290.0, sun_az=-76.0, sun_el=11.0,
        sun_col=(1.55, 1.16, 0.70), sun_str=0.95,
        sky_col=(0.66, 0.72, 0.96), sky_str=0.54,
        gnd_col=(0.66, 0.54, 0.38), gnd_str=0.26,
        exposure=1.06, shadow=(44, 40, 72, 74), cloud=(255, 226, 190, 44),
        lamps=False, stars=False, beam=0.0, sat=1.08, contrast=1.06, bloom=0.30, grain=2.0),
    "dusk": Look(
        sky_top=(20, 36, 86), sky_horizon=(228, 142, 104), fog_color=(146, 118, 124),
        fog_dist=250.0, sun_az=-88.0, sun_el=2.5,
        sun_col=(1.30, 0.74, 0.46), sun_str=0.42,
        sky_col=(0.46, 0.52, 0.86), sky_str=0.44,
        gnd_col=(0.40, 0.34, 0.38), gnd_str=0.18,
        exposure=1.00, shadow=(30, 28, 54, 44), cloud=(150, 110, 120, 48),
        lamps=True, stars=False, beam=1.1, sat=1.10, contrast=1.04, bloom=0.42, grain=2.6),
    "night": Look(
        sky_top=(4, 7, 18), sky_horizon=(22, 30, 54), fog_color=(15, 21, 38),
        fog_dist=200.0, sun_az=0.0, sun_el=-1.0,
        sun_col=(1.0, 1.0, 1.0), sun_str=0.0,
        sky_col=(0.30, 0.38, 0.62), sky_str=0.26,
        gnd_col=(0.22, 0.22, 0.28), gnd_str=0.09,
        exposure=0.92, shadow=(0, 0, 0, 0), cloud=(30, 38, 62, 40),
        lamps=True, stars=True, beam=3.4, sat=1.02, contrast=1.03, bloom=0.55, grain=3.4),
}

LANE_W = 3.6
NEAR = 0.6
FAR = 420.0
CAR_COLORS = [(178, 32, 38), (24, 52, 122), (206, 208, 212), (18, 20, 24),
              (238, 238, 240), (28, 96, 68), (196, 128, 24), (92, 96, 104),
              (140, 28, 96), (46, 128, 168)]
TRUCK_COLORS = [(228, 230, 232), (36, 62, 128), (168, 40, 40)]


def lerp(a, b, t):
    return a + (b - a) * t


def clamp8(v):
    return 0 if v < 0 else (255 if v > 255 else int(v))


def newell(pts):
    """Face normal of a (possibly non-planar) polygon."""
    nx = ny = nz = 0.0
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    if m < 1e-9:
        return (0.0, 1.0, 0.0)
    return (nx / m, ny / m, nz / m)


def hull2d(points):
    """Andrew monotone chain over (x, z) pairs."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2:
                (ax, ay), (bx, by) = out[-2], out[-1]
                if (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax) > 0:
                    break
                out.pop()
            out.append(p)
        return out[:-1]

    return half(pts) + half(reversed(pts))


# --------------------------------------------------------------------------- camera
class Camera:
    __slots__ = ("px", "py", "pz", "cy", "sy", "cp", "sp", "cr", "sr", "f", "hw", "hh")

    def __init__(self, px, py, pz, yaw, pitch, roll, f, hw, hh):
        self.px, self.py, self.pz = px, py, pz
        self.cy, self.sy = math.cos(-yaw), math.sin(-yaw)
        self.cp, self.sp = math.cos(-pitch), math.sin(-pitch)
        self.cr, self.sr = math.cos(roll), math.sin(roll)
        self.f, self.hw, self.hh = f, hw, hh

    def to_cam(self, p):
        dx = p[0] - self.px
        dy = p[1] - self.py
        dz = p[2] - self.pz
        x1 = dx * self.cy - dz * self.sy
        z1 = dx * self.sy + dz * self.cy
        y2 = dy * self.cp - z1 * self.sp
        z2 = dy * self.sp + z1 * self.cp
        return (x1 * self.cr - y2 * self.sr, x1 * self.sr + y2 * self.cr, z2)


def clip_near(pts):
    """Sutherland-Hodgman against z >= NEAR, in camera space."""
    out = []
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        a_in = a[2] >= NEAR
        b_in = b[2] >= NEAR
        if a_in:
            out.append(a)
        if a_in != b_in:
            t = (NEAR - a[2]) / (b[2] - a[2])
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, NEAR))
    return out


# --------------------------------------------------------------------------- traffic
class Vehicle:
    def __init__(self, rng, lane_x, direction, kind, base_speed, cam_lane_x):
        self.lane_x = lane_x
        self.dir = direction
        self.kind = kind
        self.z0 = rng.uniform(0, 460)
        self.lat = rng.uniform(-0.35, 0.35)
        if kind == "truck":
            self.w, self.h, self.l = 2.5, 3.6, 15.5
            self.color = rng.choice(TRUCK_COLORS)
            spd = base_speed * rng.uniform(0.74, 0.86)
        elif kind == "van":
            self.w, self.h, self.l = 2.0, 2.5, 5.8
            self.color = rng.choice(CAR_COLORS)
            spd = base_speed * rng.uniform(0.84, 1.00)
        else:
            self.w, self.h, self.l = 1.86, 1.46, 4.6
            self.color = rng.choice(CAR_COLORS)
            spd = base_speed * rng.uniform(0.87, 1.26)
        self.rel = (spd - base_speed) if direction > 0 else (-spd - base_speed)
        # anything sharing our lane must never wrap through the camera, so it
        # holds station ahead of us and only breathes a little
        self.cruise = direction > 0 and abs(lane_x - cam_lane_x) < 0.01
        if self.cruise:
            self.base = rng.uniform(55.0, 300.0)
            self.amp = rng.uniform(4.0, 14.0)
            self.rate = rng.uniform(0.10, 0.30)
            self.phase = rng.uniform(0, 2 * math.pi)

    def z_at(self, t, cam_z):
        if self.cruise:
            return cam_z + self.base + self.amp * math.sin(self.rate * t + self.phase)
        return cam_z - 55.0 + ((self.z0 + self.rel * t) % 460.0)


# --------------------------------------------------------------------------- scene
class Scene:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.look = LOOKS[cfg.look]
        self.fog_dist = cfg.fog if cfg.fog > 0 else self.look.fog_dist
        self.W, self.H = cfg.width, cfg.height
        self.ss = cfg.supersample
        self.RW, self.RH = self.W * self.ss, self.H * self.ss
        self.f = (self.RW / 2) / math.tan(math.radians(62) / 2)
        self.hw, self.hh = self.RW / 2, self.RH / 2
        self.speed = cfg.speed_kmh / 3.6

        az = math.radians(self.look.sun_az)
        el = math.radians(max(self.look.sun_el, 0.01))
        self.sun = (math.cos(el) * math.sin(az), math.sin(el), math.cos(el) * math.cos(az))
        self.shadows = self.look.sun_el > 3.0 and self.look.shadow[3] > 0
        # where the shadow of a point one metre up lands
        self.sh_off = (-self.sun[0] / math.tan(el), -self.sun[2] / math.tan(el))

        n = cfg.lanes
        self.our_edge_l = -1.4
        self.our_edge_r = -0.4 + n * LANE_W + 1.4
        self.our_lanes = [1.4 + i * LANE_W for i in range(n)]
        self.our_dashes = [-0.4 + i * LANE_W for i in range(1, n)]
        self.onc_edge_r = -3.4
        self.onc_edge_l = -4.4 - n * LANE_W - 1.0
        self.onc_lanes = [-6.2 - i * LANE_W for i in range(n)]
        self.onc_dashes = [-4.4 - i * LANE_W for i in range(1, n)]
        self.barrier_x = -2.4
        self.rail_x = self.our_edge_r + 1.6

        self.cam_lane_x = self.our_lanes[min(cfg.lane, n) - 1]
        if cfg.camera == "bumper":
            self.cam_h, self.cam_pitch = 0.55, math.radians(-1.6)
        elif cfg.camera == "chase":
            self.cam_h, self.cam_pitch = 2.15, math.radians(-5.0)
        else:
            self.cam_h, self.cam_pitch = 1.45, math.radians(-3.4)

        self._build_traffic()
        self._build_sky()
        self._build_vignette()
        self._glow_base = None
        self._glow_cache = {}

    # -- world shape ------------------------------------------------------
    def road_x(self, z):
        c = self.cfg.curve
        return c * (11.0 * math.sin(z / 300.0) + 5.0 * math.sin(z / 107.0 + 1.3))

    def road_y(self, z):
        h = self.cfg.hills
        return h * (2.6 * math.sin(z / 210.0 + 0.6) + 1.1 * math.sin(z / 83.0))

    def heading(self, z):
        return math.atan2(self.road_x(z + 0.5) - self.road_x(z - 0.5), 1.0)

    def hsh(self, n, k):
        return (math.sin(n * 12.9898 + k * 78.233 + self.cfg.seed * 0.618) * 43758.5453) % 1.0

    # -- shading ----------------------------------------------------------
    def light(self, c, n):
        """Flat-shade one face: sun + hemisphere sky + ground bounce."""
        L = self.look
        d = n[0] * self.sun[0] + n[1] * self.sun[1] + n[2] * self.sun[2]
        d = (d if d > 0.0 else 0.0) * L.sun_str
        sky = (0.5 + 0.5 * n[1]) * L.sky_str
        gnd = (0.5 - 0.5 * n[1]) * L.gnd_str
        e = L.exposure
        return (c[0] * (L.sun_col[0] * d + L.sky_col[0] * sky + L.gnd_col[0] * gnd) * e,
                c[1] * (L.sun_col[1] * d + L.sky_col[1] * sky + L.gnd_col[1] * gnd) * e,
                c[2] * (L.sun_col[2] * d + L.sky_col[2] * sky + L.gnd_col[2] * gnd) * e)

    def hl(self, x_off, z, cam_z):
        """Our own headlights: 1.0 plus a smooth cone falling off with distance
        and lateral angle. Replaces any hard-edged light pool geometry."""
        b = self.look.beam
        if b <= 0:
            return 1.0
        dz = z - cam_z
        if dz < -3.0 or dz > 140.0:
            return 1.0
        lat = x_off - self.cam_lane_x
        return 1.0 + b * math.exp(-max(dz, 0.0) / 26.0) * math.exp(-(lat / 5.5) ** 2)

    def fogged(self, c, depth, emissive=False):
        t = 1.0 - math.exp(-max(depth, 0.0) / self.fog_dist)
        t = min(t, 0.90) * (0.45 if emissive else 1.0)
        F = self.look.fog_color
        return (clamp8(lerp(c[0], F[0], t)),
                clamp8(lerp(c[1], F[1], t)),
                clamp8(lerp(c[2], F[2], t)))

    def poly(self, cam, world_pts, color, k=1.0, emissive=False, far=FAR, normal=None):
        """world polygon -> (depth, screen_pts, final_colour) or None."""
        cpts = [cam.to_cam(p) for p in world_pts]
        if max(c[2] for c in cpts) < NEAR:
            return None
        if min(c[2] for c in cpts) < NEAR:
            cpts = clip_near(cpts)
            if len(cpts) < 3:
                return None
        depth = sum(c[2] for c in cpts) / len(cpts)
        if depth > far:
            return None
        scr = [(self.hw + cam.f * x / z, self.hh - cam.f * y / z) for x, y, z in cpts]
        if emissive:
            base = color
        else:
            nrm = normal if normal is not None else newell(world_pts)
            p0 = world_pts[0]
            if ((cam.px - p0[0]) * nrm[0] + (cam.py - p0[1]) * nrm[1]
                    + (cam.pz - p0[2]) * nrm[2]) < 0:
                nrm = (-nrm[0], -nrm[1], -nrm[2])
            lit = self.light(color, nrm)
            base = (lit[0] * k, lit[1] * k, lit[2] * k)
        return (depth, scr, self.fogged(base, depth, emissive))

    # -- shadows ----------------------------------------------------------
    def drop(self, pts):
        """Project world points onto the road surface along the sun direction."""
        out = []
        ox, oz = self.sh_off
        for x, y, z in pts:
            h = y - self.road_y(z)
            out.append((x + h * ox, z + h * oz))
        return out

    def shadow_poly(self, cam, pts, lift=0.02):
        if not self.shadows:
            return None
        hull = hull2d([(round(x, 2), round(z, 2)) for x, z in self.drop(pts)])
        if len(hull) < 3:
            return None
        world = [(x, self.road_y(z) + lift, z) for x, z in hull]
        cpts = [cam.to_cam(p) for p in world]
        if max(c[2] for c in cpts) < NEAR:
            return None
        if min(c[2] for c in cpts) < NEAR:
            cpts = clip_near(cpts)
            if len(cpts) < 3:
                return None
        if sum(c[2] for c in cpts) / len(cpts) > FAR * 0.75:
            return None
        return [(self.hw + cam.f * x / z, self.hh - cam.f * y / z) for x, y, z in cpts]

    # -- traffic ----------------------------------------------------------
    def _build_traffic(self):
        import random
        rng = random.Random(self.cfg.seed)
        self.vehicles = []
        per_lane = self.cfg.traffic * 4.0
        for lane in self.our_lanes:
            for _ in range(int(round(per_lane))):
                kind = rng.choices(["car", "van", "truck"], [0.72, 0.16, 0.12])[0]
                self.vehicles.append(Vehicle(rng, lane, +1, kind, self.speed, self.cam_lane_x))
        for lane in self.onc_lanes:
            for _ in range(int(round(per_lane * 1.25))):
                kind = rng.choices(["car", "van", "truck"], [0.70, 0.16, 0.14])[0]
                self.vehicles.append(Vehicle(rng, lane, -1, kind, self.speed, self.cam_lane_x))
        if self.cfg.camera == "chase":
            hero = Vehicle(rng, self.cam_lane_x, +1, "car", self.speed, self.cam_lane_x)
            hero.color = (182, 34, 36)
            hero.cruise = True
            hero.base, hero.amp, hero.rate, hero.phase = 8.0, 0.25, 0.22, 0.0
            hero.lat = 0.0
            self.vehicles.append(hero)

    # -- static images ----------------------------------------------------
    def _build_sky(self):
        import random
        L = self.look
        img = Image.new("RGB", (self.RW, self.RH), L.sky_top)
        d = ImageDraw.Draw(img)
        horizon = self.RH * 0.5
        for y in range(int(horizon) + 2):
            t = (y / horizon) ** 1.5
            d.line([(0, y), (self.RW, y)],
                   fill=(int(lerp(L.sky_top[0], L.sky_horizon[0], t)),
                         int(lerp(L.sky_top[1], L.sky_horizon[1], t)),
                         int(lerp(L.sky_top[2], L.sky_horizon[2], t))))
        d.rectangle([0, int(horizon), self.RW, self.RH], fill=L.sky_horizon)

        rng = random.Random(self.cfg.seed * 31 + 5)
        if L.stars:
            for _ in range(420):
                x = rng.uniform(0, self.RW)
                y = rng.uniform(0, self.RH * 0.46)
                r = rng.uniform(0.6, 1.9) * self.ss
                v = int(rng.uniform(120, 255) * (1.0 - y / (self.RH * 0.5)) ** 0.4)
                d.ellipse([x - r, y - r, x + r, y + r], fill=(v, v, min(255, v + 12)))

        layer = Image.new("RGBA", (self.RW, self.RH), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for _ in range(26):
            cx = rng.uniform(0, self.RW)
            cy = rng.uniform(self.RH * 0.03, self.RH * 0.34)
            rx = rng.uniform(90, 300) * self.ss / 2
            ry = rx * rng.uniform(0.16, 0.30)
            for k in range(5):
                sc = 1 - k * 0.17
                jx = rng.uniform(-rx * 0.25, rx * 0.25)
                ld.ellipse([cx + jx - rx * sc, cy - ry * sc, cx + jx + rx * sc, cy + ry * sc],
                           fill=L.cloud)
        layer = layer.filter(ImageFilter.GaussianBlur(radius=18 * self.ss))
        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
        self.sky = img

    def _build_vignette(self):
        yy, xx = np.mgrid[0:self.H, 0:self.W].astype(np.float32)
        nx = (xx / self.W - 0.5) * 2.0
        ny = (yy / self.H - 0.5) * 2.0
        r = np.sqrt(nx * nx + ny * ny * 0.78)
        self.vignette = (1.0 - 0.18 * np.clip(r - 0.58, 0, None) ** 1.6)[:, :, None]

    # -- glows ------------------------------------------------------------
    def _sprite(self, size, color):
        key = (size, color)
        sp = self._glow_cache.get(key)
        if sp is None:
            if self._glow_base is None:
                n = 128
                g = np.mgrid[0:n, 0:n].astype(np.float32)
                r = np.sqrt(((g[1] / (n - 1) - 0.5) * 2) ** 2 + ((g[0] / (n - 1) - 0.5) * 2) ** 2)
                v = np.clip(1.0 - r, 0, 1) ** 2.4 * 255.0
                self._glow_base = Image.fromarray(v.astype(np.uint8), "L")
            base = self._glow_base.resize((size, size), Image.BILINEAR)
            tint = Image.new("RGB", (size, size), color)
            sp = ImageChops.multiply(tint, Image.merge("RGB", (base, base, base)))
            self._glow_cache[key] = sp
        return sp

    def add_glow(self, img, cx, cy, size, color):
        size = int(round(max(8, min(size, 460)) / 8.0)) * 8
        if cx < -size or cy < -size or cx > img.width + size or cy > img.height + size:
            return
        sp = self._sprite(size, color)
        x0, y0 = int(cx - size / 2), int(cy - size / 2)
        box = (x0, y0, x0 + size, y0 + size)
        img.paste(ImageChops.add(img.crop(box), sp), box)

    # -- geometry helpers -------------------------------------------------
    @staticmethod
    def box_faces(cx, cy, cz, w, h, l, theta, tw=None, tl=None, toff=0.0):
        """Named faces of a box (optionally tapered toward the top), rotated
        about Y. cy is the bottom of the box, h its height."""
        tw = w if tw is None else tw
        tl = l if tl is None else tl
        ct, st = math.cos(theta), math.sin(theta)

        def pt(u, v, d):          # u lateral, v vertical, d longitudinal
            return (cx + u * ct + d * st, cy + v, cz - u * st + d * ct)

        hw, hl, tw2, tl2 = w / 2, l / 2, tw / 2, tl / 2
        flb, frb = pt(-hw, 0, hl), pt(hw, 0, hl)
        blb, brb = pt(-hw, 0, -hl), pt(hw, 0, -hl)
        flt, frt = pt(-tw2, h, tl2 + toff), pt(tw2, h, tl2 + toff)
        blt, brt = pt(-tw2, h, -tl2 + toff), pt(tw2, h, -tl2 + toff)
        return {"top": [flt, frt, brt, blt], "back": [blb, brb, brt, blt],
                "front": [flb, frb, frt, flt], "left": [flb, blb, blt, flt],
                "right": [frb, brb, brt, frt], "_corners": [flb, frb, blb, brb,
                                                            flt, frt, blt, brt]}

    def emit_box(self, cam, grp, col, faces, overrides=None, k=1.0):
        for name, poly in faces.items():
            if name.startswith("_"):
                continue
            c = (overrides or {}).get(name, col)
            pp = self.poly(cam, poly, c, k)
            if pp:
                grp.append(pp)

    # -- per-frame --------------------------------------------------------
    def camera_at(self, t):
        cam_z = self.speed * t
        sway = 0.30 * math.sin(t * 0.55) + 0.10 * math.sin(t * 1.9)
        if self.cfg.camera == "chase":
            sway *= 0.35
        cam_x = self.road_x(cam_z) + self.cam_lane_x + sway
        cam_y = self.road_y(cam_z) + self.cam_h + 0.02 * math.sin(t * 6.1)
        ahead = 70.0
        yaw = math.atan2(self.road_x(cam_z + ahead) + self.cam_lane_x - cam_x, ahead)
        pitch = (self.cam_pitch
                 + math.atan2(self.road_y(cam_z + ahead) - (cam_y - 0.6), ahead) * 0.55)
        # bank into the corner, plus a little idle hand-held drift
        roll = ((self.heading(cam_z + 45) - self.heading(cam_z)) * 1.15
                + 0.004 * math.sin(t * 0.9) + 0.002 * math.sin(t * 2.7))
        roll = max(-0.05, min(0.05, roll))
        return Camera(cam_x, cam_y, cam_z, yaw, pitch, roll, self.f, self.hw, self.hh), cam_z

    def sample(self, t):
        """One render sample at time t -> float32 HxWx3 array, pre-grade."""
        cam, cam_z = self.camera_at(t)
        img = self.sky.copy()
        d = ImageDraw.Draw(img)
        glows = []
        shadows = []

        self._draw_hills(d, cam, cam_z)
        self._draw_surface(d, cam, cam_z)
        self._draw_markings(d, cam, cam_z)

        objs = []
        self._barrier(cam, cam_z, objs, shadows)
        self._guardrail(cam, cam_z, objs)
        self._masts(cam, cam_z, objs, glows, shadows)
        self._planting(cam, cam_z, objs, shadows)
        for veh in self.vehicles:
            self._vehicle(cam, veh, t, cam_z, objs, glows, shadows)

        if shadows:
            layer = Image.new("RGBA", (self.RW, self.RH), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            for pts in shadows:
                ld.polygon(pts, fill=self.look.shadow)
            img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
            d = ImageDraw.Draw(img)

        objs.sort(key=lambda o: -o[0])
        for _, grp in objs:
            for _, pts, col in grp:
                d.polygon(pts, fill=col)

        img = img.resize((self.W, self.H), Image.LANCZOS)
        if glows:
            glows.sort(key=lambda g: -g[2])
            for gx, gy, gs, gc in glows[:70]:
                self.add_glow(img, gx / self.ss, gy / self.ss, gs / self.ss, gc)
        return np.asarray(img, dtype=np.float32)

    def frame(self, idx):
        cfg = self.cfg
        n = max(1, cfg.motion_blur)
        if n == 1:
            arr = self.sample(idx / cfg.fps)
        else:
            shutter = 0.62 / cfg.fps       # ~180-degree shutter
            arr = self.sample(idx / cfg.fps)
            for s in range(1, n):
                arr += self.sample(idx / cfg.fps + shutter * s / n)
            arr /= n
        return self._grade(arr, idx)

    def _grade(self, arr, idx):
        L = self.look
        lum = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        arr = lum[:, :, None] + (arr - lum[:, :, None]) * L.sat
        arr = (arr - 118.0) * L.contrast + 118.0
        arr *= self.vignette
        arr = np.clip(arr, 0, 255)
        if L.bloom > 0:
            img8 = Image.fromarray(arr.astype(np.uint8))
            small = img8.resize((max(1, self.W // 4), max(1, self.H // 4)), Image.BILINEAR)
            small = small.point(lambda v: int(max(0, v - 172) * 2.6))
            small = small.filter(ImageFilter.GaussianBlur(radius=5))
            arr = arr + np.asarray(small.resize((self.W, self.H), Image.BILINEAR),
                                   dtype=np.float32) * L.bloom
        if L.grain > 0:
            rng = np.random.default_rng(idx * 7919 + self.cfg.seed)
            arr = arr + rng.normal(0.0, L.grain, arr.shape).astype(np.float32)
        return np.clip(arr, 0, 255).astype(np.uint8)

    # -- frame pieces -----------------------------------------------------
    def _draw_hills(self, d, cam, cam_z):
        hz = cam_z + 900
        cx = cam.px
        ridge = []
        for i in range(41):
            hx = cx - 900 + i * 45
            hh = (48 + 30 * math.sin(hx / 260.0) + 18 * math.sin(hx / 91.0 + 2.1)
                  + 10 * math.sin(hx / 37.0))
            ridge.append((hx, self.road_y(hz) + hh, hz))
        base = [(ridge[-1][0], self.road_y(hz) - 60, hz), (ridge[0][0], self.road_y(hz) - 60, hz)]
        p = self.poly(cam, ridge + base, (118, 142, 156), far=4000,
                      normal=(0.0, 0.25, -0.97))
        if p:
            d.polygon(p[1], fill=self.fogged(self.light((118, 142, 156), (0.0, 0.3, -0.95)), 520))

    def _strips(self, cam_z):
        """Depth slices: short near the camera, longer far away."""
        zs = []
        z = math.floor((cam_z - 30) / 3.0) * 3.0
        while z < cam_z + FAR + 40:
            zs.append(z)
            z += 3.0 + max(0.0, (z - cam_z)) * 0.045
        return zs

    def _draw_surface(self, d, cam, cam_z):
        """Ground, median, tarmac and wear are near-coplanar, so each is its own
        sorted pass; one shared sort would interleave them into stripes."""
        ground, median, road, wear = [], [], [], []
        up = (0.0, 1.0, 0.0)
        det = self.cfg.detail

        def quad(bucket, x0, x1, za, zb, color, lift=0.0, k=1.0):
            k *= self.hl((x0 + x1) * 0.5, (za + zb) * 0.5, cam_z)
            pts = [(self.road_x(za) + x0, self.road_y(za) + lift, za),
                   (self.road_x(za) + x1, self.road_y(za) + lift, za),
                   (self.road_x(zb) + x1, self.road_y(zb) + lift, zb),
                   (self.road_x(zb) + x0, self.road_y(zb) + lift, zb)]
            pp = self.poly(cam, pts, color, k, normal=up)
            if pp:
                bucket.append(pp)

        gcols = [(-260, -90), (-90, -55), (-55, -30), (-30, -12), (-12, 12),
                 (12, 30), (30, 55), (55, 90), (90, 260)]
        zs = self._strips(cam_z)
        for i in range(len(zs) - 1):
            za, zb = zs[i], zs[i + 1]
            n = int(za // 3)
            for ci, (gx0, gx1) in enumerate(gcols):
                tone = 1.0 + (self.hsh(n, 60 + ci) - 0.5) * 0.22 * det
                quad(ground, gx0, gx1, za, zb, (94, 116, 62), -0.28, tone)
            quad(median, -3.4, -1.4, za, zb, (82, 102, 56), -0.02,
                 1.0 + (self.hsh(n, 71) - 0.5) * 0.2 * det)
            # gravel verge either side of the tarmac
            quad(ground, self.our_edge_r, self.our_edge_r + 1.2, za, zb, (128, 122, 104), -0.10)
            quad(ground, self.onc_edge_l - 1.2, self.onc_edge_l, za, zb, (128, 122, 104), -0.10)
            for lo, hi, base in ((self.our_edge_l, self.our_edge_r, (66, 66, 71)),
                                 (self.onc_edge_l, self.onc_edge_r, (63, 63, 68))):
                for c in range(3):
                    x0 = lerp(lo, hi, c / 3.0)
                    x1 = lerp(lo, hi, (c + 1) / 3.0)
                    tone = 1.0 + (self.hsh(n, 80 + c + (0 if base[0] == 66 else 8)) - 0.5) * 0.10 * det
                    if det > 0 and self.hsh(n, 90 + c) < 0.045 * det:
                        tone *= 0.86          # patched repair
                    quad(road, x0, x1, za, zb, base, 0.0, tone)
            for lx in self.our_lanes:
                quad(wear, lx - 1.05, lx - 0.35, za, zb, (74, 74, 79), 0.002)
                quad(wear, lx + 0.35, lx + 1.05, za, zb, (74, 74, 79), 0.002)
            if det > 0:
                for lx in self.our_dashes + self.onc_dashes:
                    quad(wear, lx - 0.05, lx + 0.05, za, zb, (48, 48, 52), 0.003)

        if det > 0:
            for n in range(int((cam_z - 30) // 24), int((cam_z + FAR) // 24) + 1):
                za = n * 24.0
                quad(wear, self.our_edge_l, self.our_edge_r, za, za + 0.14, (52, 52, 56), 0.003)
                quad(wear, self.onc_edge_l, self.onc_edge_r, za, za + 0.14, (52, 52, 56), 0.003)

        for bucket in (ground, median, road, wear):
            bucket.sort(key=lambda s: -s[0])
            for _, pts, col in bucket:
                d.polygon(pts, fill=col)

    def _draw_markings(self, d, cam, cam_z):
        marks = []
        up = (0.0, 1.0, 0.0)

        def mquad(x0, x1, za, zb, color, k=1.0):
            k *= self.hl((x0 + x1) * 0.5, (za + zb) * 0.5, cam_z) ** 1.2
            pts = [(self.road_x(za) + x0, self.road_y(za) + 0.012, za),
                   (self.road_x(za) + x1, self.road_y(za) + 0.012, za),
                   (self.road_x(zb) + x1, self.road_y(zb) + 0.012, zb),
                   (self.road_x(zb) + x0, self.road_y(zb) + 0.012, zb)]
            pp = self.poly(cam, pts, color, k, normal=up)
            if pp:
                marks.append(pp)

        zs = self._strips(cam_z)
        for i in range(len(zs) - 1):
            za, zb = zs[i], zs[i + 1]
            n = int(za // 3)
            wearing = 1.0 - 0.12 * self.hsh(n, 55) * self.cfg.detail
            for edge in (self.our_edge_l + 0.25, self.our_edge_r - 0.40,
                         self.onc_edge_l + 0.25, self.onc_edge_r - 0.40):
                mquad(edge, edge + 0.15, za, zb, (228, 226, 214), wearing)

        period, length = 12.0, 3.0
        n0 = int((cam_z - 30) / period)
        for n in range(n0, n0 + int((FAR + 40) / period)):
            za = n * period
            wearing = 1.0 - 0.14 * self.hsh(n, 57) * self.cfg.detail
            for lx in self.our_dashes + self.onc_dashes:
                mquad(lx - 0.075, lx + 0.075, za, za + length, (232, 230, 216), wearing)

        marks.sort(key=lambda s: -s[0])
        for _, pts, col in marks:
            d.polygon(pts, fill=col)

    def _barrier(self, cam, cam_z, objs, shadows):
        step = 6.0
        b0 = math.floor((cam_z - 20) / step) * step
        bx, top, wid = self.barrier_x, 0.92, 0.24
        for i in range(int((FAR + 30) / step)):
            za = b0 + i * step
            zb = za + step - 0.12
            if zb - cam_z > FAR:
                break
            ya, yb = self.road_y(za), self.road_y(zb)
            xa, xb = self.road_x(za), self.road_x(zb)
            faces = (
                [(xa + bx - wid, ya, za), (xb + bx - wid, yb, zb),
                 (xb + bx - wid * 0.55, yb + top, zb), (xa + bx - wid * 0.55, ya + top, za)],
                [(xa + bx + wid, ya, za), (xb + bx + wid, yb, zb),
                 (xb + bx + wid * 0.55, yb + top, zb), (xa + bx + wid * 0.55, ya + top, za)],
                [(xa + bx - wid * 0.55, ya + top, za), (xb + bx - wid * 0.55, yb + top, zb),
                 (xb + bx + wid * 0.55, yb + top, zb), (xa + bx + wid * 0.55, ya + top, za)],
            )
            bk = self.hl(bx, za, cam_z)
            grp = [p for p in (self.poly(cam, f, (172, 170, 162), bk) for f in faces) if p]
            if grp:
                grp.sort(key=lambda g: -g[0])
                objs.append((za - cam_z, grp))
                sh = self.shadow_poly(cam, [(xa + bx, ya, za), (xb + bx, yb, zb),
                                            (xa + bx, ya + top, za), (xb + bx, yb + top, zb)])
                if sh:
                    shadows.append(sh)

    def _guardrail(self, cam, cam_z, objs):
        step = 4.0
        p0 = math.floor((cam_z - 20) / step) * step
        rx = self.rail_x
        for i in range(int((FAR + 30) / step)):
            za = p0 + i * step
            zb = za + step
            if zb - cam_z > FAR:
                break
            ya, yb = self.road_y(za), self.road_y(zb)
            xa, xb = self.road_x(za), self.road_x(zb)
            grp = []
            post = [(xa + rx - 0.06, ya, za), (xa + rx + 0.06, ya, za),
                    (xa + rx + 0.06, ya + 0.78, za), (xa + rx - 0.06, ya + 0.78, za)]
            beam = [(xa + rx, ya + 0.46, za), (xb + rx, yb + 0.46, zb),
                    (xb + rx, yb + 0.78, zb), (xa + rx, ya + 0.78, za)]
            rk = self.hl(rx, za, cam_z)
            for f, c in ((post, (104, 106, 110)), (beam, (178, 180, 184))):
                pp = self.poly(cam, f, c, rk)
                if pp:
                    grp.append(pp)
            if self.hsh(int(za), 66) < 0.5:      # reflector
                rf = [(xa + rx - 0.02, ya + 0.60, za - 0.06), (xa + rx - 0.02, ya + 0.60, za + 0.06),
                      (xa + rx - 0.02, ya + 0.72, za + 0.06), (xa + rx - 0.02, ya + 0.72, za - 0.06)]
                pp = self.poly(cam, rf, (255, 176, 40), emissive=self.look.lamps)
                if pp:
                    grp.append((pp[0] - 0.2, pp[1], pp[2]))
            if grp:
                grp.sort(key=lambda g: -g[0])
                objs.append((za - cam_z + 0.5, grp))

    def _masts(self, cam, cam_z, objs, glows, shadows):
        step = 60.0
        l0 = math.floor((cam_z - 20) / step) * step
        for i in range(int((FAR + 60) / step)):
            za = l0 + i * step
            bx = self.road_x(za) + self.rail_x + 1.6
            by = self.road_y(za)
            grp = []
            for f in ([(bx - 0.14, by, za), (bx + 0.14, by, za),
                       (bx + 0.10, by + 11.0, za), (bx - 0.10, by + 11.0, za)],
                      [(bx - 0.10, by + 10.6, za), (bx - 2.6, by + 11.3, za),
                       (bx - 2.6, by + 11.05, za), (bx - 0.10, by + 10.35, za)]):
                pp = self.poly(cam, f, (146, 148, 152))
                if pp:
                    grp.append(pp)
            head = [(bx - 3.2, by + 11.0, za), (bx - 2.3, by + 11.25, za),
                    (bx - 2.3, by + 10.85, za), (bx - 3.2, by + 10.7, za)]
            lit = self.look.lamps
            pp = self.poly(cam, head, (255, 232, 180) if lit else (196, 198, 200), emissive=lit)
            if pp:
                grp.append(pp)
                if lit:
                    xs = [q[0] for q in pp[1]]
                    ys = [q[1] for q in pp[1]]
                    glows.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                                  max(4.0, max(xs) - min(xs)) * 7.0, (150, 128, 80)))
            sh = self.shadow_poly(cam, [(bx - 0.14, by, za), (bx + 0.14, by, za),
                                        (bx - 0.14, by + 11.0, za), (bx + 0.14, by + 11.0, za)])
            if sh:
                shadows.append(sh)
            if grp:
                grp.sort(key=lambda g: -g[0])
                objs.append((za - cam_z + 1.0, grp))

    def _planting(self, cam, cam_z, objs, shadows):
        if self.cfg.trees <= 0:
            return
        step = 15.0 / max(self.cfg.trees, 0.05)
        n0 = int((cam_z - 20) / step)
        keep = 0.62 * min(self.cfg.trees, 1.0)
        for n in range(n0, n0 + int((FAR + 40) / step)):
            z = n * step + self.hsh(n, 3) * 9.0
            gy = self.road_y(z) - 0.28
            cx = self.road_x(z)
            for side in (-1, 1):
                k = 1 if side > 0 else 2
                if self.hsh(n, k) > keep:
                    continue
                off = 19.0 + self.hsh(n, k + 10) * 58.0
                tx = cx + (off if side > 0 else -off - 6.0)
                ht = 4.2 + self.hsh(n, k + 20) * 5.6
                tone = 0.86 + self.hsh(n, k + 30) * 0.30
                grp = []
                tw = ht * 0.035
                trunk = [(tx - tw, gy, z), (tx + tw, gy, z),
                         (tx + tw * 0.7, gy + ht * 0.45, z), (tx - tw * 0.7, gy + ht * 0.45, z)]
                pp = self.poly(cam, trunk, (74, 58, 44))
                if pp:
                    grp.append(pp)
                # canopy blobs: normals fanned outward so each lobe catches the sun
                for j, (dy, rs, nx_, ny_) in enumerate(((0.34, 0.62, -0.5, 0.3),
                                                        (0.55, 0.78, 0.1, 0.7),
                                                        (0.76, 0.58, 0.4, 0.6))):
                    cy = gy + ht * (0.38 + dy * 0.42)
                    rx, ry = ht * 0.30 * rs, ht * 0.22 * rs
                    a0 = self.hsh(n, k + j)
                    pts = [(tx + rx * math.cos(a * 2 * math.pi / 7 + a0),
                            cy + ry * math.sin(a * 2 * math.pi / 7 + a0), z) for a in range(7)]
                    m = math.sqrt(nx_ * nx_ + ny_ * ny_ + 0.36)
                    pp = self.poly(cam, pts, (54, 88, 46), tone,
                                   normal=(nx_ / m, ny_ / m, -0.6 / m))
                    if pp:
                        grp.append(pp)
                if grp:
                    grp.sort(key=lambda g: -g[0])
                    objs.append((z - cam_z + 0.2, grp))
                    r = ht * 0.30
                    sh = self.shadow_poly(cam, [(tx - r, gy + ht * 0.55, z - r),
                                                (tx + r, gy + ht * 0.55, z - r),
                                                (tx + r, gy + ht * 0.55, z + r),
                                                (tx - r, gy + ht * 0.55, z + r),
                                                (tx, gy, z)])
                    if sh:
                        shadows.append(sh)
            if self.hsh(n, 44) < 0.5:
                bx = cx + self.rail_x + 2.2 + self.hsh(n, 45) * 4.0
                bh = 0.7 + self.hsh(n, 46) * 0.8
                pts = [(bx + bh * 0.9 * math.cos(a * 2 * math.pi / 7),
                        gy + bh * 0.55 + bh * 0.5 * math.sin(a * 2 * math.pi / 7), z)
                       for a in range(7)]
                pp = self.poly(cam, pts, (72, 98, 52), 0.9 + self.hsh(n, 47) * 0.3)
                if pp:
                    objs.append((z - cam_z + 0.2, [pp]))

    def _vehicle(self, cam, veh, t, cam_z, objs, glows, shadows):
        z = veh.z_at(t, cam_z)
        if z < cam_z - 22 or z > cam_z + FAR:
            return
        xc = self.road_x(z) + veh.lane_x + veh.lat
        yb = self.road_y(z)
        th = self.heading(z) + (math.pi if veh.dir < 0 else 0.0)
        ct, st = math.cos(th), math.sin(th)
        col = veh.color
        grp = []
        vk = self.hl(veh.lane_x, z, cam_z)

        def along(dist):
            return (xc + dist * st, z + dist * ct)

        if veh.kind == "truck":
            self.emit_box(cam, grp, (42, 42, 46),
                          self.box_faces(xc, yb + 0.05, z, veh.w * 0.95, 0.5, veh.l * 0.92, th), k=vk)
            tx, tz = along(-2.0)
            self.emit_box(cam, grp, (226, 227, 231),
                          self.box_faces(tx, yb + 1.05, tz, veh.w, 2.8, 11.5, th), k=vk)
            hx, hz = along(veh.l / 2 - 1.25)
            self.emit_box(cam, grp, col,
                          self.box_faces(hx, yb + 0.55, hz, veh.w, 2.35, 2.6, th,
                                         tw=veh.w * 0.94, tl=2.3),
                          {"front": (46, 56, 70)}, k=vk)
            silhouette = [(xc - veh.w / 2, yb, z - veh.l / 2), (xc + veh.w / 2, yb, z - veh.l / 2),
                          (xc - veh.w / 2, yb, z + veh.l / 2), (xc + veh.w / 2, yb, z + veh.l / 2),
                          (xc - veh.w / 2, yb + 3.85, z - veh.l / 2),
                          (xc + veh.w / 2, yb + 3.85, z + veh.l / 2)]
        else:
            bh = 0.72 if veh.kind == "car" else 1.35
            # wheels, then body, then glasshouse
            for dz in (veh.l * 0.30, -veh.l * 0.30):
                for side in (-1, 1):
                    wx = xc + side * (veh.w * 0.5 - 0.06) * ct + dz * st
                    wz = z - side * (veh.w * 0.5 - 0.06) * st + dz * ct
                    r = 0.32
                    pts = [(wx + r * math.cos(a * math.pi / 3) * ct,
                            yb + 0.33 + r * math.sin(a * math.pi / 3),
                            wz - r * math.cos(a * math.pi / 3) * st) for a in range(6)]
                    pp = self.poly(cam, pts, (26, 26, 30), normal=(side * ct, 0.0, -side * st))
                    if pp:
                        grp.append((pp[0] - 0.1, pp[1], pp[2]))
            self.emit_box(cam, grp, (34, 34, 38),
                          self.box_faces(xc, yb + 0.10, z, veh.w * 1.01, 0.26, veh.l * 0.94, th), k=vk)
            self.emit_box(cam, grp, col,
                          self.box_faces(xc, yb + 0.34, z, veh.w, bh, veh.l, th,
                                         tw=veh.w * 0.96, tl=veh.l * 0.97), k=vk)
            chh = 0.50 if veh.kind == "car" else 0.88
            cl = veh.l * (0.50 if veh.kind == "car" else 0.78)
            gx, gz = along(-0.10 * veh.l)
            # roof is shorter than the cabin base and sits slightly forward of it:
            # raked windscreen at the front, rear glass falling away behind
            self.emit_box(cam, grp, (40, 50, 62),
                          self.box_faces(gx, yb + 0.34 + bh, gz, veh.w * 0.92, chh, cl, th,
                                         tw=veh.w * 0.80, tl=cl * 0.66, toff=0.06 * cl),
                          {"top": col}, k=vk)
            # bumper band and plate on the face we can see
            sgn = -1 if veh.dir > 0 else 1
            bd = sgn * (veh.l / 2 + 0.015)
            bump = [(xc + u * ct + bd * st, yb + 0.34 + dy, z - u * st + bd * ct)
                    for u, dy in ((-veh.w * 0.48, 0.02), (veh.w * 0.48, 0.02),
                                  (veh.w * 0.48, 0.20), (-veh.w * 0.48, 0.20))]
            pp = self.poly(cam, bump, (52, 52, 58), vk)
            if pp:
                grp.append((pp[0] - 0.3, pp[1], pp[2]))
            plate = [(xc + u * ct + bd * st, yb + 0.42 + dy, z - u * st + bd * ct)
                     for u, dy in ((-0.24, 0.0), (0.24, 0.0), (0.24, 0.12), (-0.24, 0.12))]
            pp = self.poly(cam, plate, (214, 212, 198), vk * 1.2)
            if pp:
                grp.append((pp[0] - 0.32, pp[1], pp[2]))
            top = yb + 0.34 + bh + chh
            silhouette = [(xc - veh.w / 2, yb, z - veh.l / 2), (xc + veh.w / 2, yb, z - veh.l / 2),
                          (xc - veh.w / 2, yb, z + veh.l / 2), (xc + veh.w / 2, yb, z + veh.l / 2),
                          (xc - veh.w * 0.4, top, z - veh.l * 0.2),
                          (xc + veh.w * 0.4, top, z + veh.l * 0.2)]

        lit = self.look.lamps
        if veh.dir > 0:                       # we see the rear
            lc = (255, 70, 58) if lit else (206, 32, 28)
            ly, sgn, glow_c = yb + 0.62, -1, (120, 24, 20)
        else:                                 # oncoming, we see the front
            lc = (255, 250, 228) if lit else (255, 246, 212)
            ly, sgn, glow_c = yb + 0.58, 1, (140, 132, 104)
        lamp_d = veh.l / 2 + 0.03
        if veh.kind == "truck":
            ly = yb + 0.85
        for side in (-1, 1):
            u0 = side * (veh.w * 0.5 - 0.14)
            u1 = side * (veh.w * 0.5 - 0.50)
            quad = [(xc + u * ct + sgn * lamp_d * st, ly + dy, z - u * st + sgn * lamp_d * ct)
                    for u, dy in ((u0, 0), (u1, 0), (u1, 0.15), (u0, 0.15))]
            pp = self.poly(cam, quad, lc, emissive=lit)
            if pp:
                grp.append((pp[0] - 0.4, pp[1], pp[2]))
                if lit:
                    xs = [q[0] for q in pp[1]]
                    ys = [q[1] for q in pp[1]]
                    glows.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                                  max(3.0, max(xs) - min(xs)) * 6.0, glow_c))
        if grp:
            grp.sort(key=lambda g: -g[0])
            objs.append((z - cam_z, grp))
            sh = self.shadow_poly(cam, silhouette)
            if sh:
                shadows.append(sh)


# --------------------------------------------------------------------------- workers
_SCENE = None


def _init_worker(cfg: Config):
    global _SCENE
    _SCENE = Scene(cfg)


def _render_frame(idx: int) -> bytes:
    return _SCENE.frame(idx).tobytes()


# --------------------------------------------------------------------------- commands
def _validate(cfg: Config) -> None:
    for name, kind, rng, choices, _ in SPEC:
        v = getattr(cfg, name)
        if choices and v not in choices:
            raise SystemExit(f"highway: --{name.replace('_', '-')} must be one of {choices}")
        if rng and not (rng[0] <= v <= rng[1]):
            raise SystemExit(f"highway: --{name.replace('_', '-')} must be in [{rng[0]}, {rng[1]}]")
    if cfg.lane > cfg.lanes:
        raise SystemExit(f"highway: --lane {cfg.lane} exceeds --lanes {cfg.lanes}")


def cmd_preview(cfg: Config, at: str) -> dict:
    _validate(cfg)
    times = [float(x) for x in str(at).split(",") if x.strip() != ""]
    if not times:
        raise SystemExit("highway: --at needs at least one timestamp")
    scene = Scene(cfg)
    tiles = [Image.fromarray(scene.frame(int(round(s * cfg.fps)))) for s in times]
    if len(tiles) == 1:
        sheet = tiles[0]
    else:
        cols = min(3, len(tiles))
        rows = (len(tiles) + cols - 1) // cols
        tw, th = cfg.width // 2, cfg.height // 2
        sheet = Image.new("RGB", (cols * tw, rows * th))
        for i, tile in enumerate(tiles):
            sheet.paste(tile.resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
    out = Path(cfg.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return {"ok": True, "command": "preview", "out": str(out),
            "at": times, "width": sheet.width, "height": sheet.height}


def cmd_render(cfg: Config) -> dict:
    _validate(cfg)
    if shutil.which("ffmpeg") is None:
        raise SystemExit("highway: ffmpeg not found on PATH (brew install ffmpeg)")
    import multiprocessing as mp

    out = Path(cfg.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    nframes = max(1, int(round(cfg.fps * cfg.duration)))
    workers = cfg.threads or max(2, (os.cpu_count() or 4) - 2)
    t0 = time.time()

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{cfg.width}x{cfg.height}", "-r", str(cfg.fps), "-i", "-", "-an",
         "-c:v", "libx264", "-preset", "slow", "-crf", str(cfg.quality),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    try:
        with mp.Pool(workers, initializer=_init_worker, initargs=(cfg,)) as pool:
            for i, buf in enumerate(pool.imap(_render_frame, range(nframes), chunksize=4)):
                ff.stdin.write(buf)
                if i and i % 240 == 0:
                    print(f"highway: {i}/{nframes}", file=sys.stderr, flush=True)
        ff.stdin.close()
    except BrokenPipeError:
        ff.wait()
        raise SystemExit("highway: ffmpeg exited early; check the output path and codec support")
    rc = ff.wait()
    if rc != 0:
        raise SystemExit(f"highway: ffmpeg failed with exit code {rc}")
    return {"ok": True, "command": "render", "out": str(out), "frames": nframes,
            "fps": cfg.fps, "duration": round(nframes / cfg.fps, 3),
            "width": cfg.width, "height": cfg.height,
            "bytes": out.stat().st_size, "render_seconds": round(time.time() - t0, 2)}


def cmd_describe() -> dict:
    defaults = asdict(Config())
    opts = []
    for name, kind, rng, choices, help_ in SPEC:
        o = {"name": name, "flag": "--" + name.replace("_", "-"), "type": kind,
             "default": defaults[name], "help": help_}
        if rng:
            o["min"], o["max"] = rng[0], rng[1]
        if choices:
            o["choices"] = choices
        opts.append(o)
    return {
        "name": "highway",
        "summary": "Render a procedural highway-drive video (or a still preview) "
                   "without any 3D application installed.",
        "commands": {
            "describe": "Print this document as JSON.",
            "preview": "Render one frame, or a contact sheet, to a PNG. "
                       "Cheap - use it to check settings before rendering.",
            "render": "Render the clip to an H.264 .mp4. Requires ffmpeg on PATH.",
        },
        "extra_args": {"--at": "preview only: comma-separated timestamps in seconds, e.g. 2,8,14"},
        "options": opts,
        "requires": {"ffmpeg": "render only", "python": ">=3.9",
                     "pip": ["pillow", "numpy"], "bootstrap": "automatic, into ./.venv"},
        "output": "Every command prints a single JSON object on stdout. "
                  "Exit code 0 on success, non-zero with a message on stderr otherwise.",
        "notes": [
            "Cost scales with width*height*supersample^2*fps*duration*motion_blur.",
            "Same seed plus same options reproduces the same clip exactly.",
            "Traffic in the camera's own lane holds station ahead and never passes "
            "through the viewpoint.",
            "Preview first: it renders single frames in-process and takes a fraction "
            "of a second each.",
        ],
        "examples": [
            "python3 highway.py preview --out /tmp/check.png --at 1,6,12 --look golden",
            "python3 highway.py render --out drive.mp4 --duration 20",
            "python3 highway.py render --out night.mp4 --look night --camera chase --traffic 1.4",
            "python3 highway.py render --out crisp.mp4 --motion-blur 1 --detail 0",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="highway.py", description=__doc__.split("\n")[0],
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("describe", help="print options and usage as JSON")
    defaults = asdict(Config())
    for cmd, helptext in (("render", "render an mp4"), ("preview", "render a still png")):
        sp = sub.add_parser(cmd, help=helptext,
                            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        if cmd == "preview":
            sp.add_argument("--at", default="8", metavar="SECS",
                            help="comma-separated timestamps, e.g. 2,8,14")
        for name, kind, rng, choices, help_ in SPEC:
            cast = {"int": int, "float": float}.get(kind, str)
            sp.add_argument("--" + name.replace("_", "-"), dest=name, type=cast,
                            default=defaults[name], choices=choices, help=help_)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "describe":
        print(json.dumps(cmd_describe(), indent=2))
        return 0
    cfg = Config(**{f.name: getattr(args, f.name) for f in fields(Config)})
    if args.command == "preview":
        if Path(cfg.out).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            raise SystemExit("highway: preview --out needs an image extension (.png)")
        result = cmd_preview(cfg, args.at)
    else:
        result = cmd_render(cfg)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
