"""The two exterior shots: the ship comes down (night) and goes (dawn).

Runs inside Blender on a prepared petersburg set. No characters, so no
Performer: the ship, the camera and the sky-writing are animated here.
"""

from __future__ import annotations

import math
import os

import bpy
import numpy as np
from mathutils import Vector

from cartoon.bl import common as C
from cartoon.sets import petersburg as PB


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _key_path(ob, frames, fn):
    """Key location and rotation. Rotation goes in as quaternions kept on
    one hemisphere: Euler keys wrapped across +-180 degrees and the camera
    spun between them, smearing the whole dawn shot under motion blur."""
    from mathutils import Euler
    ob.rotation_mode = "QUATERNION"
    prev = None
    for f in frames:
        loc, rot = fn(f)
        ob.location = loc
        q = Euler(rot, "XYZ").to_quaternion()
        if prev is not None and q.dot(prev) < 0:
            q.negate()
        prev = q
        ob.rotation_quaternion = q
        ob.keyframe_insert("location", frame=f)
        ob.keyframe_insert("rotation_quaternion", frame=f)


def night(film, shot, f0, f1):
    """Beat 0: snow over the embankment, the camera drifting down from the
    rooftops to the one lit window. Beat 1: a light in the sky becomes a
    pepper mill that sets down in the snow outside."""
    fps = film["fps"]
    marks = bpy.context.scene["petersburg_marks"]
    win = Vector(marks["study_window"])
    ship = bpy.data.objects["ship"]
    b1 = film["beats"][shot["beats"][-1]]
    t_land0 = b1["start"]
    t_land1 = b1["end"] - 0.8
    start = Vector(PB.SHIP_START)
    land = Vector(PB.LANDING)

    def ship_at(f):
        t = f / fps
        s = ease((t - t_land0) / (t_land1 - t_land0))
        # swoop: across, then down, settling with a little bounce
        p = start.lerp(land, s)
        p.z = start.z + (land.z - start.z) * (1 - (1 - s) ** 2.2)
        p.x += 3.0 * math.sin(math.pi * s) * (1 - s)
        bob = 0.08 * math.sin(t * 5.0) * (1 - ease((t - t_land1 + 0.6) / 0.6))
        settle = -0.06 * math.sin(max(0.0, t - t_land1) * 9) * math.exp(-4 * max(0.0, t - t_land1))
        p.z += bob + settle
        spin = t * 1.2
        tilt = 0.25 * (1 - s)
        return p, (tilt, 0.0, spin)
    _key_path(ship, range(f0, f1 + 1, 2), ship_at)

    cd = bpy.data.cameras.new("shot")
    cd.lens = 30
    cam = bpy.data.objects.new("shot", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    n = max(1, f1 - f0)

    def cam_at(f):
        # from the moon over the rooftops down to the one warm window
        k = ease((f - f0) / n)
        loc = Vector((7.0, -16.0, 2.2)).lerp(Vector((6.0, -12.5, 1.9)), k)
        tgt = Vector((10.0, 60.0, 40.0)).lerp(Vector((0.6, -1.0, 4.4)), ease(k * 1.35))
        d = tgt - loc
        return loc, d.to_track_quat("-Z", "Y").to_euler()
    cd.lens = 26
    _key_path(cam, range(f0, f1 + 1, 4), cam_at)
    cd.dof.use_dof = False
    return cam


def dawn(film, shot, f0, f1, identity_png):
    """The ship lifts off and writes the identity across the pink sky in
    steam, the text appearing behind it as it flies."""
    fps = film["fps"]
    ship = bpy.data.objects["ship"]
    land = Vector(PB.LANDING)
    # the writing: a plane in the sky with the typeset identity on it
    w, h = 44.0, 11.0
    me = bpy.data.meshes.new("skywriting")
    me.from_pydata([(-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for li, (u, v) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[li].uv = (u, v)
    sky_text = bpy.data.objects.new("skywriting", me)
    bpy.context.scene.collection.objects.link(sky_text)
    SKY = Vector((-18.0, -110.0, 34.0))
    sky_text.location = SKY
    sky_text.rotation_euler = (math.radians(8), 0, math.radians(180))
    m = bpy.data.materials.new("skywriting")
    m.use_nodes = True
    m.surface_render_method = "BLENDED"
    nt = m.node_tree
    for n_ in list(nt.nodes):
        if n_.type == "BSDF_PRINCIPLED":
            nt.nodes.remove(n_)
    out = nt.nodes["Material Output"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(identity_png)
    tex.extension = "CLIP"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    # puff the letters up: sample the glyphs slightly blurred by noise offset
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18
    off = nt.nodes.new("ShaderNodeVectorMath")
    off.operation = "MULTIPLY_ADD"
    off.inputs[1].default_value = (0.006, 0.02, 0)
    off.inputs[2].default_value = (-0.003, -0.01, 0)
    nt.links.new(noise.outputs["Color"], off.inputs[0])
    add = nt.nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    nt.links.new(tc.outputs["UV"], add.inputs[0])
    nt.links.new(off.outputs["Vector"], add.inputs[1])
    nt.links.new(tc.outputs["UV"], noise.inputs["Vector"])
    # fit the image's aspect in the plane (letterboxed)
    img = tex.image
    aspect = img.size[0] / max(1, img.size[1])
    plane_aspect = w / h
    mp = nt.nodes.new("ShaderNodeMapping")
    if aspect > plane_aspect:
        sy = aspect / plane_aspect
        mp.inputs["Scale"].default_value = (1.0, sy, 1.0)
        mp.inputs["Location"].default_value = (0.0, -(sy - 1) / 2, 0.0)
    nt.links.new(add.outputs["Vector"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    # reveal left to right with a soft, smoky edge
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    rev = nt.nodes.new("ShaderNodeValue")
    rev.name = "reveal"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    nt.links.new(rev.outputs[0], sub.inputs[0])
    nt.links.new(sep.outputs["X"], sub.inputs[1])
    edge = nt.nodes.new("ShaderNodeMapRange")
    edge.inputs["From Min"].default_value = 0.0
    edge.inputs["From Max"].default_value = 0.03
    nt.links.new(sub.outputs[0], edge.inputs["Value"])
    mask = nt.nodes.new("ShaderNodeMath")
    mask.operation = "MULTIPLY"
    nt.links.new(edge.outputs["Result"], mask.inputs[0])
    nt.links.new(tex.outputs["Alpha"], mask.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.93, 0.9, 1)
    em.inputs["Strength"].default_value = 2.2
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mask.outputs[0], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    me.materials.append(m)

    t0, t1 = shot["start"], shot["end"]
    lift = t0 + 0.8
    write0, write1 = t0 + 2.2, t1 - 1.0

    # the plane is turned to face the embankment, so its +u runs toward -x
    left = SKY + Vector((w / 2, 1.0, h / 2 + 1.0))
    right = SKY + Vector((-w / 2, 1.0, h / 2 + 1.0))

    def ship_at(f):
        t = f / fps
        if t < write0:
            s = ease((t - lift) / (write0 - lift))
            p = land.lerp(left, s)
            p.z = land.z + (left.z - land.z) * math.sin(0.5 * math.pi * s)
        else:
            s = min(1.0, (t - write0) / (write1 - write0))
            p = left.lerp(right, s) + Vector((0, 0, 0.5 * math.sin(s * 25)))
            if t > write1:
                p = p + Vector((0, 0, (t - write1) * 6.0))
        return p, (0.3, 0.0, t * 2.0)
    _key_path(ship, range(f0, f1 + 1, 2), ship_at)
    for f in range(f0, f1 + 1, 2):
        t = f / fps
        rev.outputs[0].default_value = max(0.0, min(1.0, (t - write0) / (write1 - write0))) * 1.03
        rev.outputs[0].keyframe_insert("default_value", frame=f)

    cd = bpy.data.cameras.new("shot")
    cd.lens = 24
    cam = bpy.data.objects.new("shot", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    n = max(1, f1 - f0)

    def cam_at(f):
        # from the ship lifting off by the house, round to the river and
        # the spire, where the steam is writing
        k = ease((f - f0) / n)
        loc = Vector((4.5, -9.0, 1.6)).lerp(Vector((2.0, -15.5, 1.5)), k)
        tgt = Vector((1.6, -3.0, 1.8)).lerp(SKY + Vector((0, 0, -4.0)), ease(k * 1.5))
        return loc, (tgt - loc).to_track_quat("-Z", "Y").to_euler()
    _key_path(cam, range(f0, f1 + 1, 4), cam_at)
    return cam
