"""Staged demonstrations: the physical situations he walks over to and works.

Runs inside Blender. One module per demonstration, and one entry in
`REGISTRY`, which is also what `lecture_describe` publishes -- so adding a
demonstration is adding a file and a line, and the catalogue a caller reads
updates itself. Nothing has to be kept in sync by hand.

Each demonstration exposes:

    NAME, SUMMARY, build(origin, n_frames, fps) -> dict

`build` creates its objects near `origin`, keyframes them across the whole
shot, and says where the camera and his eyes should look. It is given the
real number of frames because timing is speech-driven: a demonstration is
stretched or compressed to fit the sentence that introduces it, never the
other way round.
"""

from __future__ import annotations

import importlib
import math
import os

import bpy
from mathutils import Vector

_loaded: dict = {}


def modules() -> tuple:
    """The demonstration modules on disk.

    Discovered, never listed. A hardcoded list here disagreed with the one in
    `script.py`, so validation passed a lecture that the renderer then could
    not stage -- and the job died thirty shots in. The files are the only
    truth either side should consult.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return tuple(sorted(f[:-3] for f in os.listdir(here)
                        if f.endswith(".py") and not f.startswith("_")))


def registry() -> dict:
    """Every demonstration this renderer knows how to stage."""
    if not _loaded:
        for name in modules():
            _loaded[name] = importlib.import_module(f"{__name__}.{name}")
    return _loaded


def names() -> list[str]:
    return sorted(registry())


def build(name: str, origin=(0.55, 0.30, 0.02), n_frames: int = 48,
          fps: int = 24) -> dict:
    mods = registry()
    if name not in mods:
        raise KeyError(
            f"no demonstration called '{name}'; known: {', '.join(names())}")
    return mods[name].build(Vector(origin), n_frames, fps)


# ------------------------------------------------------------------ material

def matte(name: str, rgba, rough=0.65):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgba
    b.inputs["Roughness"].default_value = rough
    return m


def glow(name: str, rgb, strength=14.0):
    """An emission shader -- light that reads as light, not as a pale object."""
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1.0)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


# ---------------------------------------------------------------- primitives

def cube(name, loc, dims, material=None):
    """A box of the given full extents, in metres.

    Takes real dimensions rather than a size and a scale: a unit cube scaled
    by `w / 2` is `w / 2` across, not `w`, and that off-by-two put a table top
    at half the width of its own legs.
    """
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = dims
    if material:
        o.data.materials.append(material)
    return o


def ball(name, r, loc, material=None, segments=24):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc,
                                         segments=segments, ring_count=14)
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    if material:
        o.data.materials.append(material)
    return o


def rod(name, r, length, loc, material=None, axis="Z"):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=length, location=loc,
                                        vertices=20)
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    if axis == "X":
        o.rotation_euler = (0, math.pi / 2, 0)
    elif axis == "Y":
        o.rotation_euler = (math.pi / 2, 0, 0)
    if material:
        o.data.materials.append(material)
    return o


def key(obj, frame: int, location=None, scale=None, rotation=None):
    if location is not None:
        obj.location = location
        obj.keyframe_insert("location", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert("scale", frame=frame)
    if rotation is not None:
        obj.rotation_euler = rotation
        obj.keyframe_insert("rotation_euler", frame=frame)


def label(text: str, loc, size=0.055, colour=(0.88, 0.92, 1.0, 1.0),
          align="CENTER"):
    """A word in the scene, as real geometry.

    Anything that carries text in life gets text here: a plate, a sign, the
    side of a train. A blank one reads as an unfinished model.
    """
    bpy.ops.object.text_add(location=loc)
    o = bpy.context.object
    o.data.body = text
    o.data.size = size
    o.data.align_x = align
    o.data.extrude = 0.002
    o.rotation_euler = (math.pi / 2, 0, 0)
    o.data.materials.append(matte(f"label.{text[:12]}", colour, 0.5))
    return o


FLOOR_Z = -0.98


def plinth(origin, base: float, width=1.15, depth=0.46, caption=""):
    """A table under the demonstration, built to what it actually occupies.

    Takes `base` -- how far below `origin` the lowest part of the
    demonstration reaches -- so the top meets it rather than being guessed at,
    and the legs run to the actual floor. Anything staged in mid-air with its
    furniture floating somewhere else reads as a diagram pasted over a
    photograph.
    """
    wood = matte("demo.wood", (0.22, 0.17, 0.13, 1.0), 0.76)
    top_z = origin.z - base - 0.012
    made = [cube("plinth.top", (origin.x, origin.y, top_z),
                 (width, depth, 0.032), wood)]
    height = top_z - 0.016 - FLOOR_Z
    for sx in (-1, 1):
        for sy in (-1, 1):
            made.append(cube(f"plinth.leg.{sx}{sy}",
                             (origin.x + sx * (width / 2 - 0.07),
                              origin.y + sy * (depth / 2 - 0.07),
                              FLOOR_Z + height / 2),
                             (0.042, 0.042, height), wood))
    if caption:
        made.append(label(caption,
                          (origin.x, origin.y - depth / 2 - 0.004,
                           top_z - 0.052),
                          0.046, (0.72, 0.76, 0.84, 1.0)))
    return made


def demo_light(origin, energy=90.0):
    """A soft light over the demonstration, so it is not lit by spill alone."""
    d = bpy.data.lights.new("demo_key", "AREA")
    d.color = (1.0, 0.96, 0.90)
    d.energy = energy
    d.size = 1.1
    o = bpy.data.objects.new("demo_key", d)
    o.location = (origin.x + 0.15, origin.y - 0.95, origin.z + 1.15)
    o.rotation_euler = (math.radians(38), 0, math.radians(14))
    bpy.context.scene.collection.objects.link(o)
    return o


def plot_axes(origin, w, h, xlabel, ylabel, ticks=()):
    """Axes for a staged graph, with the tick values written on them.

    A curve rising off an unlabelled corner says "it goes up". The whole
    interest is in where it goes up, so the numbers are part of the object.
    """
    axis_mat = matte("demo.slate", PALETTE["slate"], 0.78)
    made = [cube("plot.x", origin + Vector((w / 2, 0, 0)), (w, 0.007, 0.007),
                 axis_mat),
            cube("plot.y", origin + Vector((0, 0, h / 2)), (0.007, 0.007, h),
                 axis_mat)]
    made.append(label(xlabel, origin + Vector((w * 0.55, -0.01, -0.058)), 0.030,
                      (0.72, 0.76, 0.84, 1.0)))
    made.append(label(ylabel, origin + Vector((-0.075, -0.01, h * 0.92)), 0.030,
                      (0.72, 0.76, 0.84, 1.0)))
    for frac, text in ticks:
        made.append(cube(f"plot.tick.{text}",
                         origin + Vector((w * frac, 0, 0)),
                         (0.005, 0.005, 0.022), axis_mat))
        made.append(label(text, origin + Vector((w * frac, -0.01, -0.046)),
                          0.024, (0.66, 0.70, 0.78, 1.0)))
    return made


def plot_curve(name, origin, w, h, fn, n_frames, mat, points=34, ymax=1.0,
               grow=True):
    """A curve drawn as it is traced, left to right.

    Drawn rather than revealed: the eye follows a line being made, and on a
    curve that runs away to infinity the rate it steepens is the point.
    """
    made = []
    for i in range(points):
        u = (i + 0.5) / points
        y = min(fn(u), ymax) / ymax
        d = ball(f"{name}.{i:02d}", 0.0105,
                 (origin.x + w * u, origin.y - 0.012, origin.z + h * y),
                 mat, segments=10)
        made.append(d)
        if grow:
            appear = max(1, int(u * n_frames * 0.9))
            key(d, 1, scale=(0.001, 0.001, 0.001))
            key(d, max(1, appear - 1), scale=(0.001, 0.001, 0.001))
            key(d, min(n_frames, appear + 2), scale=(1.0, 1.0, 1.0))
    return made


PALETTE = dict(
    steel=(0.42, 0.46, 0.54, 1.0),
    brass=(0.66, 0.52, 0.26, 1.0),
    slate=(0.16, 0.18, 0.22, 1.0),
    warm=(0.78, 0.36, 0.28, 1.0),
    cool=(0.32, 0.58, 0.86, 1.0),
    pale=(0.80, 0.84, 0.90, 1.0),
)
