"""Armatures, skinning, and the handful of rig conventions every character
here follows.

Conventions, so animation code can be written once:

- Every bone's roll is set so its local Z points where the character faces
  (-Y) unless said otherwise. For a bone pointing up the spine, rotating
  about local X nods, about local Y turns, about local Z tilts.
- Pose bones use quaternions, with helpers that take world-space axes, so
  nobody has to know a bone's local frame to turn it.
- Arms are driven by IK targets (empties named `ik.<hand bone>`) with pole
  targets (`pole.<forearm bone>`): "put the hand on the slate here" is a
  position, and that is the only form a hand pose is ever asked for in.
"""

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from cartoon.bl import common as C


def armature(name, bones, coll, forward=(0, -1, 0)):
    """bones: list of dict(name, head, tail, parent=None, deform=True,
    roll_to=None (world vector for local Z), connect=False)."""
    ad = bpy.data.armatures.new(name)
    ad.display_type = "STICK"
    ob = bpy.data.objects.new(name, ad)
    coll.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = ad.edit_bones
    for b in bones:
        e = eb.new(b["name"])
        e.head = Vector(b["head"])
        e.tail = Vector(b["tail"])
        e.use_deform = b.get("deform", True)
        z = Vector(b.get("roll_to") or forward)
        y = (e.tail - e.head).normalized()
        if abs(y.dot(z.normalized())) > 0.98:
            z = Vector((0, 0, 1)) if abs(y.z) < 0.9 else Vector((0, -1, 0))
        e.align_roll(z)
    for b in bones:
        if b.get("parent"):
            eb[b["name"]].parent = eb[b["parent"]]
            eb[b["name"]].use_connect = b.get("connect", False)
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in ob.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return ob


def ik(arm, bone, target, pole=None, chain=2, pole_angle=0.0):
    pb = arm.pose.bones[bone]
    c = pb.constraints.new("IK")
    c.target = target
    c.chain_count = chain
    if pole is not None:
        c.pole_target = pole
        c.pole_angle = pole_angle
    return c


def empty(name, loc, coll, size=0.03, shape="SPHERE", parent=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = shape
    e.empty_display_size = size
    e.location = loc
    coll.objects.link(e)
    if parent is not None:
        e.parent = parent
    return e


def skin_auto(ob, arm, keep=None):
    """Bone-heat weights, then drop the groups of bones not in `keep`."""
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    if keep is not None:
        for vg in list(ob.vertex_groups):
            if vg.name not in keep:
                ob.vertex_groups.remove(vg)
        normalise(ob)
    empty_groups = [vg.name for vg in ob.vertex_groups]
    C.log(f"{ob.name}: skinned to {len(empty_groups)} bones")


def normalise(ob):
    n = len(ob.data.vertices)
    W = np.zeros((n, len(ob.vertex_groups)))
    for vi, v in enumerate(ob.data.vertices):
        for g in v.groups:
            W[vi, g.group] = g.weight
    s = W.sum(1)
    for vi in np.nonzero(s > 0)[0]:
        for g in ob.data.vertices[vi].groups:
            g.weight = g.weight / s[vi]


def skin_groups(ob, arm, weights: dict):
    """Explicit weights: {bone name: per-vertex array}."""
    for name, w in weights.items():
        vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
        idx = np.nonzero(w > 1e-4)[0]
        for i in idx:
            vg.add([int(i)], float(w[i]), "REPLACE")
    mod = ob.modifiers.new("rig", "ARMATURE")
    mod.object = arm
    # armature before subdivision
    while ob.modifiers[0] != mod:
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_move_up(modifier=mod.name)
    ob.parent = arm


def attach(ob, arm, bone):
    """Rigid child of a bone, keeping its current world placement."""
    mw = ob.matrix_world.copy()
    ob.parent = arm
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    bpy.context.view_layer.update()
    ob.matrix_world = mw


def segment_weights(P, pts, bones, before=None, blend=0.3):
    """Weights along a chain of joints `pts` (k+1 points for k bones).

    Each vertex is projected onto the polyline; inside segment i it belongs
    to bones[i], blending into the neighbour over `blend` of a segment at
    each joint. Before the first joint it blends into `before`.
    """
    P = np.asarray(P)
    pts = [np.asarray(p) for p in pts]
    best = np.full(len(P), np.inf)
    s_par = np.zeros(len(P))
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ab = b - a
        t = np.clip(((P - a) @ ab) / (ab @ ab), -0.6 if i == 0 else 0.0, 1.0)
        d = np.linalg.norm(P - (a + np.outer(t, ab)), axis=1)
        m = d < best
        best[m] = d[m]
        s_par[m] = i + t[m]
    W = {b: np.zeros(len(P)) for b in bones}
    if before:
        W[before] = np.zeros(len(P))
    for i, b in enumerate(bones):
        lo = np.clip((s_par - (i - blend)) / (2 * blend), 0, 1)
        hi = np.clip(((i + 1 + blend) - s_par) / (2 * blend), 0, 1)
        if i == len(bones) - 1:
            hi = np.ones(len(P))
        if i == 0 and before is None:
            lo = np.ones(len(P))
        W[b] = np.minimum(lo, hi)
    if before:
        W[before] = np.clip((blend - s_par) / (2 * blend), 0, 1)
    tot = sum(W.values())
    tot[tot == 0] = 1
    return {k: v / tot for k, v in W.items()}


# ------------------------------------------------------------ posing

def world_rot(arm, bone, axis, angle_deg):
    """Quaternion for a pose bone that turns it `angle` about a world axis,
    relative to its rest orientation (ignores what its parents are doing)."""
    b = arm.data.bones[bone]
    R = (arm.matrix_world.to_3x3() @ b.matrix_local.to_3x3()).normalized()
    q = Quaternion(Vector(axis).normalized(), math.radians(angle_deg))
    local = R.inverted() @ q.to_matrix() @ R
    return local.to_quaternion()


def compose(*qs):
    out = Quaternion()
    for q in qs:
        out = out @ q
    return out
