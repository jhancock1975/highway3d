"""Eyes with lids, the way cartoon rigs build them.

The ball is a sphere that turns to look; each lid is a shell of a slightly
larger sphere that turns about the same centre to open and close. The
head's sculpted socket is larger again, so the lid slides in the gap
between ball and skin and its back edge is always hidden inside the head.
A lid that is a separate shell has a real edge with real thickness, and
that edge's shadow on the ball is most of what makes an eye read as alive
rather than painted on.
"""

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from cartoon.bl import common as C


def _shell(name, radius, theta0, theta1, phi_half, n_t=18, n_p=40):
    """A patch of sphere: polar angle theta0..theta1 from +Z, azimuth
    +-phi_half about the -Y (front) direction. Returns a mesh object."""
    ts = np.linspace(math.radians(theta0), math.radians(theta1), n_t)
    ps = np.linspace(-math.radians(phi_half), math.radians(phi_half), n_p)
    V = []
    for t in ts:
        for p in ps:
            V.append((radius * math.sin(t) * math.sin(p),
                      -radius * math.sin(t) * math.cos(p),
                      radius * math.cos(t)))
    F = []
    for i in range(n_t - 1):
        for j in range(n_p - 1):
            a = i * n_p + j
            F.append((a, a + 1, a + n_p + 1, a + n_p))
    # outward normals, whichever way theta runs
    mid = np.array(V[(n_t // 2) * n_p + n_p // 2])
    a, b, c = (np.array(V[k]) for k in (F[0][0], F[0][1], F[0][2]))
    if np.dot(np.cross(b - a, c - b), a) < 0:
        F = [f[::-1] for f in F]
    me = bpy.data.meshes.new(name)
    me.from_pydata(V, [], F)
    me.update()
    me.shade_smooth()
    # rim darkening toward the free edge (theta1 end): lash line
    col = me.color_attributes.new("rim", "FLOAT_COLOR", "POINT")
    vals = []
    for i in range(n_t):
        f = i / (n_t - 1)
        dark = max(0.0, (f - 0.82) / 0.18) ** 1.5
        for _ in range(n_p):
            vals.extend((dark, dark, dark, 1.0))
    col.data.foreach_set("color", vals)
    ob = bpy.data.objects.new(name, me)
    return ob


def lid_material(name, skin_rgb, lash_rgb=(0.05, 0.035, 0.03)):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_name = "rim"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (*skin_rgb, 1)
    mix.inputs["B"].default_value = (*lash_rgb, 1)
    nt.links.new(a.outputs["Fac"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.5
    p.inputs["Subsurface Weight"].default_value = 0.18
    p.inputs["Subsurface Scale"].default_value = 0.0025
    p.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
    return m


def build_eye(prefix, center, radius, eye_mat, lid_mat, coll, gap=0.0014,
              thickness=0.0022, tilt=0.0):
    """Ball + upper lid + lower lid, all pivoting on `center` (world).

    Every piece is parented to an empty at the centre, which is what the
    head carries; the ball turns to look (rotation on the empty's children),
    the lids turn about local X. `tilt` rolls the whole eye about the view
    axis (degrees) so the lid line can slope like a real eye's.
    """
    root = bpy.data.objects.new(prefix + ".eye_root", None)
    root.empty_display_size = radius * 1.5
    root.location = center
    root.rotation_euler = (0, math.radians(tilt), 0)
    coll.objects.link(root)

    me = bpy.data.meshes.new(prefix + ".ball")
    ball = bpy.data.objects.new(prefix + ".ball", me)
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=radius)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.materials.append(eye_mat)
    coll.objects.link(ball)
    ball.parent = root

    r_lid = radius + gap
    up = _shell(prefix + ".lid_up", r_lid, 0, 92, 118)
    # a hair inside the upper, so where they meet the upper lid is in front
    lo = _shell(prefix + ".lid_lo", r_lid - 0.35 * gap, 180, 95, 112)
    for lid in (up, lo):
        lid.data.materials.append(lid_mat)
        coll.objects.link(lid)
        lid.parent = root
        s = lid.modifiers.new("solid", "SOLIDIFY")
        s.thickness = thickness
        s.offset = 1.0
        s.use_rim = True
        s.use_rim_only = False
        C.subsurf(lid, 1, 2)
    return dict(root=root, ball=ball, lid_up=up, lid_lo=lo, radius=radius)


def set_lids(eye, upper_open: float, lower_open: float = 1.0, look_pitch: float = 0.0):
    """Upper 1 = wide open, 0 = shut; lower likewise. `look_pitch` is the
    ball's pitch in radians (+ is looking up); lids follow part of it, as
    real lids do.

    Angles: the upper shell's free edge sits at 92 deg from the top pole,
    i.e. just below the equator. Rotating it about X by -a lifts the edge by
    a. Wide open lifts it 50 deg; shut brings it down 8 deg past centre to
    meet the lower lid.
    """
    up = -math.radians(-8 + 58 * upper_open) - 0.6 * look_pitch
    lo = math.radians(3 + 17 * lower_open) - 0.3 * look_pitch
    eye["lid_up"].rotation_euler = (up, 0, 0)
    eye["lid_lo"].rotation_euler = (lo, 0, 0)


def set_look(eye, yaw: float, pitch: float):
    """Turn the ball: yaw + toward +x (the character's left), pitch + up."""
    eye["ball"].rotation_euler = (-pitch, 0, yaw)
