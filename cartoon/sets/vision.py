"""The void the taste visions happen in: deep violet dark, Cinnamon in the
middle, coloured rim lights, and bloom so that light reads as flavour."""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from cartoon.bl import cast, common as C

CENTER = Vector((0.0, 0.0, 1.2))


def bloom(strength=0.6, threshold=1.2, size=6):
    """Glare (bloom) in the compositor. Blender 5 keeps the compositor in a
    node group on the scene rather than in scene.node_tree."""
    sc = bpy.context.scene
    ng = bpy.data.node_groups.new("bloom", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    gl = ng.nodes.new("CompositorNodeGlare")
    gl.inputs["Type"].default_value = "Bloom"
    gl.inputs["Threshold"].default_value = threshold
    gl.inputs["Strength"].default_value = strength
    gl.inputs["Size"].default_value = size
    out = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
    ng.links.new(gl.outputs["Image"], out.inputs[0])
    sc.compositing_node_group = ng
    sc.render.use_compositing = True
    return ng


def build(coll=None):
    coll = coll or C.collection("vision")
    ci = cast.load("cinnamon")
    cast.place(ci, CENTER, 0)
    w = bpy.context.scene.world or bpy.data.worlds.new("w")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.004, 0.002, 0.012, 1)
    ramp.color_ramp.elements[1].color = (0.05, 0.02, 0.09, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.4, 0.4, 0.4)
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], grad.inputs["Vector"])
    nt.links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0

    def area(name, off, energy, color, size):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.color = color
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        coll.objects.link(lo)
        lo.location = CENTER + Vector(off)
        C.aim(lo, CENTER)
        ld.use_shadow = False
        return lo
    area("vision.key", (0.8, -1.4, 0.9), 20, (1.0, 0.82, 0.62), 1.0)
    area("vision.rim_l", (-1.2, 0.8, 0.6), 30, (0.5, 0.35, 1.0), 0.5)
    area("vision.rim_r", (1.2, 0.9, 0.3), 25, (1.0, 0.45, 0.3), 0.5)
    area("vision.under", (0, -0.6, -1.0), 8, (0.9, 0.5, 1.0), 1.0)
    bloom()
    return dict(coll=coll)
