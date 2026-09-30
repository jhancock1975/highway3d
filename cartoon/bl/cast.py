"""Bring built characters into a scene and put them on their marks."""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

from cartoon.bl import common as C

ASSETS = os.path.join(C.ROOT, ".work", "cartoon", "assets")


def load(name, blend=None):
    """Append a character's collection; return its armature."""
    blend = blend or os.path.join(ASSETS, f"{name}.blend")
    with bpy.data.libraries.load(blend, link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c == name]
    coll = dst.collections[0]
    bpy.context.scene.collection.children.link(coll)
    arm = next(o for o in coll.objects if o.type == "ARMATURE")
    return arm


def place(arm, loc, yaw_deg=0.0):
    arm.location = Vector(loc)
    arm.rotation_euler = (0, 0, math.radians(yaw_deg))
