"""The room the lecture happens in, and the light in it.

Runs inside Blender. A set rather than a backdrop: there is a floor, a wall
behind him and a chalkboard he can turn to, all lit by one warm key with a
cool rim, because a character who casts no shadow onto anything reads as a
sticker on a gradient -- which is exactly what the first version of this
lecture was.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

LOOKS = {
    "study": dict(
        key=(1.0, 0.90, 0.78), key_energy=205.0,
        fill=(0.50, 0.62, 0.86), fill_energy=26.0,
        rim=(0.70, 0.82, 1.0), rim_energy=150.0,
        wall=(0.082, 0.074, 0.090), floor=(0.052, 0.048, 0.058),
        world=(0.018, 0.019, 0.026),
    ),
    "void": dict(
        key=(0.92, 0.95, 1.0), key_energy=120.0,
        fill=(0.40, 0.48, 0.70), fill_energy=22.0,
        rim=(0.70, 0.84, 1.0), rim_energy=130.0,
        wall=(0.045, 0.050, 0.065), floor=(0.035, 0.038, 0.050),
        world=(0.012, 0.014, 0.020),
    ),
}

BOARD = (0.105, 0.135, 0.125, 1.0)


def _mat(name, rgba, rough=0.8):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgba
    b.inputs["Roughness"].default_value = rough
    return m


def _area(name, loc, rot, colour, energy, size):
    d = bpy.data.lights.new(name, "AREA")
    d.color = colour
    d.energy = energy
    d.size = size
    o = bpy.data.objects.new(name, d)
    o.location = loc
    o.rotation_euler = rot
    bpy.context.scene.collection.objects.link(o)
    return o


def build(look: str = "study") -> dict:
    spec = LOOKS[look]
    scene = bpy.context.scene

    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (*spec["world"], 1.0)
    scene.world = world

    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, -0.98))
    floor = bpy.context.object
    floor.name = "floor"
    floor.data.materials.append(_mat("floor", (*spec["floor"], 1.0), 0.92))

    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 1.45, 2.0),
                                     rotation=(math.pi / 2, 0, 0))
    wall = bpy.context.object
    wall.name = "wall"
    wall.data.materials.append(_mat("wall", (*spec["wall"], 1.0), 0.95))

    # the chalkboard: where notation lands, and something for him to turn to
    bpy.ops.mesh.primitive_plane_add(size=1, location=(-0.62, 1.41, 0.26),
                                     rotation=(math.pi / 2, 0, 0))
    board = bpy.context.object
    board.name = "chalkboard"
    board.scale = (1.62, 1.0, 0.96)
    board.data.materials.append(_mat("board", BOARD, 0.96))

    key = _area("key", (-1.5, -1.9, 1.9), (math.radians(58), 0, math.radians(-38)),
                spec["key"], spec["key_energy"], 2.4)
    fill = _area("fill", (2.1, -1.7, 0.7), (math.radians(76), 0, math.radians(52)),
                 spec["fill"], spec["fill_energy"], 3.0)
    rim = _area("rim", (1.1, 1.2, 2.3), (math.radians(-42), 0, math.radians(20)),
                spec["rim"], spec["rim_energy"], 1.6)

    return dict(floor=floor, wall=wall, board=board, key=key, fill=fill, rim=rim)


def chalk(board, frames_dir: str, count: int) -> None:
    """Put a rendered notation sequence onto the board as chalk.

    An image sequence rather than a still, and mixed into the board's own
    material rather than composited over the frame afterwards -- so the
    writing takes the room's key light, dims where the board is in shadow,
    and sits behind him when he crosses in front of it.
    """
    import os

    first = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))[0]
    img = bpy.data.images.load(os.path.join(frames_dir, first))
    img.source = "SEQUENCE"

    mat = board.data.materials[0]
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Smart"
    tex.extension = "CLIP"
    tex.image_user.frame_duration = count
    tex.image_user.frame_start = 1
    tex.image_user.frame_offset = 0
    tex.image_user.use_auto_refresh = True

    # chalk over slate: the alpha decides where the board stops being board
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = BOARD
    nt.links.new(tex.outputs["Color"], mix.inputs["B"])
    nt.links.new(tex.outputs["Alpha"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])

    # a little glow, so chalk stays legible in a room lit for a face
    if "Emission Color" in bsdf.inputs:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        strength = nt.nodes.new("ShaderNodeMath")
        strength.operation = "MULTIPLY"
        strength.inputs[1].default_value = 0.55
        nt.links.new(tex.outputs["Alpha"], strength.inputs[0])
        nt.links.new(strength.outputs[0], bsdf.inputs["Emission Strength"])


def camera_at(location, lens, target):
    """A camera placed exactly where a caller asks.

    Cutaway scenes bring their own framing: they are not the lecture room
    and the named framings in `camera` mean nothing in them.
    """
    cam_data = bpy.data.cameras.new("camera")
    cam_data.lens = lens
    cam = bpy.data.objects.new("camera", cam_data)
    cam.location = location
    bpy.context.scene.collection.objects.link(cam)
    empty = bpy.data.objects.new("look_at", None)
    empty.location = target
    bpy.context.scene.collection.objects.link(empty)
    t = cam.constraints.new("TRACK_TO")
    t.target = empty
    t.track_axis = "TRACK_NEGATIVE_Z"
    t.up_axis = "UP_Y"
    bpy.context.scene.camera = cam
    return cam


def camera(shot: str = "mid", target=(0, 0, 0),
           fit: float = 0.0) -> bpy.types.Object:
    """One of a few framings. The planner picks; the caller never does.

    `fit` is the half-width, in metres, that must end up inside the frame.
    Demonstrations are not all the same size -- they report their own width,
    and the widest is nearly twice the narrowest -- so a fixed camera
    distance either clips the big ones or leaves the small ones swimming.
    Given `fit` the camera backs off along its own axis until the content
    fits, and otherwise stays exactly where the table puts it.
    """
    frames = {
        # Measured against the figure rather than guessed. He is 1.18 m from
        # the soles of his shoes to the top of his hair -- he used to be a
        # bust that stopped at the chest, and every framing here was set to
        # crop where he ran out. At 34 mm on a 36 mm sensor a 16:9 frame is
        # 0.596 m tall per metre of distance, so holding a 1.18 m figure with
        # air above and below wants about 2.9 m, not 1.95 m.
        "wide":  ((0.16, -3.40, -0.02), 42),
        "mid":   ((-0.10, -2.30, -0.06), 50),
        "close": ((-0.08, -1.40, 0.04), 58),
        "board": ((0.54, -2.20, 0.02), 48),
        # Wide enough to hold him on the left and the demonstration on the
        # right without either becoming a detail.
        "demo":  ((0.18, -2.85, -0.04), 38),
        # Him on the right, the board he is writing on to the left.
        "note":  ((0.02, -2.48, -0.08), 34),
    }
    loc, lens = frames[shot]
    cam_data = bpy.data.cameras.new("camera")
    cam_data.lens = lens
    cam = bpy.data.objects.new("camera", cam_data)
    cam.location = loc
    bpy.context.scene.collection.objects.link(cam)

    empty = bpy.data.objects.new("look_at", None)
    empty.location = target
    bpy.context.scene.collection.objects.link(empty)
    t = cam.constraints.new("TRACK_TO")
    t.target = empty
    t.track_axis = "TRACK_NEGATIVE_Z"
    t.up_axis = "UP_Y"

    if fit > 0.0:
        # A 36 mm sensor is 18 mm from centre to edge, so a lens of f mm
        # sees `18 / f` metres of half-width per metre of distance. Invert
        # that for the distance a given half-width needs, and leave 6 per
        # cent of air so nothing sits exactly on the frame edge.
        t = Vector(target)
        v = Vector(loc) - t
        need = fit * lens / 18.0 * 1.06
        if v.length < need:
            cam.location = t + v.normalized() * need

    bpy.context.scene.camera = cam
    return cam
