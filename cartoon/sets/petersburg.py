"""St. Petersburg, 1773, outside Euler's house on the Neva embankment.

Runs inside Blender. `build(time)` for "night" (the ship comes down through
the snow) or "dawn" (the ship leaves, writing in the sky).

A row of baroque houses in the city's pastels -- ochre, green, pink -- with
white pilasters and snow on every ledge; the frozen river; the gilded
needle of the Peter and Paul Cathedral across it; oil lamps on posts (the
city had them from the 1720s); and a bakery's hanging sign, because a street
without a single word on it looks like a set.

The ship is a pepper mill -- copper crown, walnut body, glowing portholes,
a knob that puffs coloured steam -- because it belongs to someone who
thinks with their tongue.
"""

from __future__ import annotations

import math
import random

import bpy
import numpy as np
from mathutils import Vector

from cartoon import sculpt as S
from cartoon.bl import common as C
from cartoon.sets.study import _box, _cyl, _text, _textured, _sky_material, FONT_BOOK

FONT_SIGN = "/System/Library/Fonts/Supplemental/Baskerville.ttc"

# Euler's house: its study window is the lit one on the first floor
HOUSE_X = 0.0
STREET_Y = 0.0          # facades stand along y = 0, facing -y (the river)
LANDING = (1.6, -3.2, 0.0)
SHIP_START = (-6.0, -14.0, 22.0)


def mats(time):
    M = {}
    M["snow"] = C.mat_plain("pb.snow", (0.82, 0.86, 0.95), rough=0.55, sss=0.25)
    M["ice"] = C.mat_plain("pb.ice", (0.5, 0.6, 0.72), rough=0.15, coat=0.6)
    M["trim"] = C.mat_plain("pb.trim", (0.8, 0.78, 0.72), rough=0.6)
    M["roof"] = C.mat_plain("pb.roof", (0.12, 0.2, 0.18), rough=0.5, metal=0.3)
    M["gold"] = C.mat_plain("pb.gold", (0.95, 0.7, 0.3), rough=0.2, metal=1.0)
    M["iron"] = C.mat_plain("pb.iron", (0.03, 0.03, 0.035), rough=0.45, metal=0.8)
    M["wood"] = C.mat_plain("pb.wood", (0.2, 0.1, 0.05), rough=0.6)
    lit = 3.0 if time == "night" else 0.4
    M["window_lit"] = C.mat_plain("pb.window_lit", (1, 0.7, 0.35), emit=(1.0, 0.62, 0.28), emit_strength=lit)
    M["window_dark"] = C.mat_plain("pb.window_dark", (0.05, 0.06, 0.09), rough=0.08, coat=1.0)
    M["lamp"] = C.mat_plain("pb.lamp", (1, 0.75, 0.4), emit=(1.0, 0.66, 0.3),
                            emit_strength=12.0 if time == "night" else 0.0)
    for name, rgb in (("ochre", (0.72, 0.48, 0.16)), ("green", (0.28, 0.48, 0.34)),
                      ("pink", (0.72, 0.42, 0.38)), ("blue", (0.34, 0.46, 0.62)),
                      ("white", (0.78, 0.76, 0.7))):
        M[name] = C.mat_plain("pb." + name, rgb, rough=0.85)
    M["sky"] = _sky(time)
    M["sign"] = C.mat_plain("pb.sign", (0.08, 0.22, 0.14), rough=0.5)
    M["signtext"] = C.mat_plain("pb.signtext", (0.9, 0.7, 0.3), rough=0.3, metal=1.0)
    return M


def _sky(time):
    if time == "night":
        return _sky_material("night")
    m = bpy.data.materials.new("pb.sky_dawn")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type == "BSDF_PRINCIPLED":
            nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nrm = nt.nodes.new("ShaderNodeVectorMath")
    nrm.operation = "NORMALIZE"
    nt.links.new(tc.outputs["Object"], nrm.inputs[0])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(nrm.outputs["Vector"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = (1.0, 0.55, 0.35, 1)
    e = cr.elements.new(0.12)
    e.color = (0.95, 0.5, 0.55, 1)
    cr.elements[1].position = 0.55
    cr.elements[1].color = (0.25, 0.3, 0.6, 1)
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.6
    nt.links.new(em.outputs["Emission"], nt.nodes["Material Output"].inputs["Surface"])
    return m


def house(name, x0, width, floors, colour, M, coll, lit_windows=(), rng=None, study=False):
    """A baroque house: stuccoed box, white pilasters and cornices, tall
    windows with snow on the sills, a green roof under snow."""
    rng = rng or random.Random(0)
    fh = 3.4
    h = floors * fh + 0.6
    depth = 12.0
    xc = x0 + width / 2
    _box(name, (width, depth, h), (xc, STREET_Y + depth / 2, h / 2), M[colour], coll)
    _box(name + ".plinth", (width + 0.1, 0.25, 0.9), (xc, STREET_Y - 0.1, 0.45), M["white"], coll, 0.02)
    for k in range(floors + 1):
        z = 0.9 + k * fh
        _box(f"{name}.cornice{k}", (width + 0.2, 0.3, 0.18), (xc, STREET_Y - 0.1, z), M["trim"], coll, 0.03)
        _box(f"{name}.cornice_snow{k}", (width + 0.2, 0.28, 0.06), (xc, STREET_Y - 0.12, z + 0.12), M["snow"], coll, 0.02)
    # pilasters between window bays
    bays = max(3, int(width / 2.1))
    bw = width / bays
    for i in range(bays + 1):
        _box(f"{name}.pilaster{i}", (0.28, 0.12, h - 1.2), (x0 + i * bw, STREET_Y - 0.06, 0.9 + (h - 1.2) / 2),
             M["white"], coll)
    wins = []
    for f in range(floors):
        for i in range(bays):
            wx = x0 + (i + 0.5) * bw
            wz = 0.9 + f * fh + 1.55
            is_lit = (f, i) in lit_windows
            m = M["window_lit"] if is_lit else M["window_dark"]
            _box(f"{name}.win{f}_{i}", (1.0, 0.1, 1.8), (wx, STREET_Y - 0.02, wz), m, coll)
            _box(f"{name}.winframe{f}_{i}", (1.2, 0.14, 0.14), (wx, STREET_Y - 0.05, wz + 0.97), M["white"], coll, 0.02)
            _box(f"{name}.winsill{f}_{i}", (1.25, 0.25, 0.08), (wx, STREET_Y - 0.1, wz - 0.95), M["white"], coll)
            _box(f"{name}.winsnow{f}_{i}", (1.2, 0.24, 0.07), (wx, STREET_Y - 0.12, wz - 0.88), M["snow"], coll, 0.02)
            # mullions
            for dx in (-0.25, 0.25):
                _box(f"{name}.mul{f}_{i}_{dx}", (0.04, 0.12, 1.8), (wx + dx, STREET_Y - 0.03, wz), M["white"], coll)
            for dz in (-0.45, 0.15, 0.6):
                _box(f"{name}.mulh{f}_{i}_{dz}", (1.0, 0.12, 0.04), (wx, STREET_Y - 0.03, wz + dz), M["white"], coll)
            wins.append(((wx, STREET_Y - 0.1, wz), is_lit))
    # roof and its snow
    roof = _box(name + ".roof", (width + 0.3, depth * 0.55, 2.2), (xc, STREET_Y + depth * 0.25, h + 0.9), M["roof"], coll)
    roof.rotation_euler = (math.radians(-28), 0, 0)
    snowr = _box(name + ".roof_snow", (width + 0.35, depth * 0.52, 0.3), (xc, STREET_Y + depth * 0.22, h + 1.9), M["snow"], coll, 0.08)
    snowr.rotation_euler = (math.radians(-28), 0, 0)
    # chimneys with snow caps
    for i in range(rng.randint(1, 2)):
        cx = x0 + rng.uniform(1.0, width - 1.0)
        _box(f"{name}.chimney{i}", (0.6, 0.6, 1.8), (cx, STREET_Y + 3.0, h + 2.4), M["white"], coll)
        _box(f"{name}.chimney_snow{i}", (0.7, 0.7, 0.14), (cx, STREET_Y + 3.0, h + 3.35), M["snow"], coll, 0.04)
    return wins


def spire(coll, M, loc=(-30.0, -150.0, 0.0)):
    """The Peter and Paul Cathedral's bell tower across the river: stacked
    tiers and the long gilded needle, the city's landmark."""
    x, y, z = loc
    _box("spire.base", (9, 9, 18), (x, y, z + 9), M["ochre"], coll)
    _box("spire.tier1", (7, 7, 8), (x, y, z + 22), M["ochre"], coll)
    _box("spire.tier2", (5, 5, 7), (x, y, z + 29.5), M["white"], coll)
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=2.6, radius2=0.05, depth=48, location=(x, y, z + 57))
    cone = bpy.context.active_object
    cone.name = "spire.needle"
    for c in cone.users_collection:
        c.objects.unlink(cone)
    coll.objects.link(cone)
    cone.data.materials.append(M["gold"])
    _cyl("spire.drum", 2.8, 4, (x, y, z + 35), M["gold"], coll, 8)
    # the rest of the fortress as a long low wall
    _box("fortress", (120, 12, 8), (x + 10, y + 8, z + 4), M["pink"], coll)
    _box("fortress_snow", (120, 12.2, 0.5), (x + 10, y + 8, z + 8.2), M["snow"], coll)


def street_lamp(name, loc, coll, M, time):
    x, y, z = loc
    _cyl(name + ".post", 0.07, 3.2, (x, y, 1.6), M["iron"], coll, 12)
    _box(name + ".lantern", (0.35, 0.35, 0.5), (x, y, 3.45), M["lamp"], coll, 0.02)
    _box(name + ".cap", (0.45, 0.45, 0.1), (x, y, 3.75), M["iron"], coll, 0.02)
    _box(name + ".snowcap", (0.46, 0.46, 0.06), (x, y, 3.83), M["snow"], coll, 0.02)
    if time == "night":
        ld = bpy.data.lights.new(name + ".light", "POINT")
        ld.energy = 120
        ld.color = (1.0, 0.65, 0.32)
        ld.shadow_soft_size = 0.15
        lo = bpy.data.objects.new(name + ".light", ld)
        lo.location = (x, y, 3.45)
        coll.objects.link(lo)


def bakery_sign(coll, M, loc):
    """A painted board hanging from an iron bracket: БУЛОЧНАЯ, 'bakery', with
    a gilded pretzel. (Cinnamon would approve.)"""
    x, y, z = loc
    _box("sign.bracket", (0.05, 1.1, 0.05), (x, y - 0.55, z + 0.5), M["iron"], coll)
    _box("sign.board", (1.4, 0.06, 0.6), (x, y - 0.9, z), M["sign"], coll, 0.01)
    _box("sign.snow", (1.42, 0.07, 0.05), (x, y - 0.9, z + 0.32), M["snow"], coll, 0.01)
    t = _text("sign.text", "БУЛОЧНАЯ", (x, y - 0.94, z - 0.05), (math.radians(90), 0, 0), 0.2, M["signtext"], coll,
              font=FONT_SIGN, extrude=0.004)
    t2 = _text("sign.text2", "Anno 1760", (x, y - 0.94, z + 0.18), (math.radians(90), 0, 0), 0.09, M["signtext"], coll,
               font=FONT_SIGN, extrude=0.003)
    for sx in (-1, 1):
        _box(f"sign.chain{sx}", (0.015, 0.015, 0.2), (x + sx * 0.6, y - 0.9, z + 0.4), M["iron"], coll)
    return t


def house_plaque(coll, M, loc):
    x, y, z = loc
    _box("plaque", (0.7, 0.05, 0.4), (x, y - 0.03, z), M["white"], coll, 0.01)
    _text("plaque.text", "№ 15", (x, y - 0.065, z), (math.radians(90), 0, 0), 0.16, M["iron"], coll,
          font=FONT_SIGN, extrude=0.003)


# ------------------------------------------------------------------ ship

COPPER = (0.8, 0.38, 0.2)
WALNUT = (0.22, 0.1, 0.04)
BRASS = (0.8, 0.62, 0.3)


def ship_field():
    """The pepper mill, sculpted: a walnut body waisted in the middle, a
    copper crown, a brass knob on top, three stubby legs."""
    body = S.Union([
        S.Capsule((0, 0, 0.35), (0, 0, 1.25), 0.62, 0.52, color=WALNUT, label="body"),
        S.blend(S.Torus((0, 0, 0.8), 0.6, 0.06, color=BRASS, label="band"), 0.02),
        S.blend(S.Ellipsoid((0, 0, 1.45), (0.72, 0.72, 0.42), color=COPPER, label="crown"), 0.05),
        S.blend(S.Capsule((0, 0, 1.8), (0, 0, 2.05), 0.09, 0.07, color=BRASS, label="knob"), 0.05),
        S.blend(S.Sphere((0, 0, 2.12), 0.16, color=BRASS, label="knob"), 0.04),
    ], k=0.12)
    # fluting on the walnut, like a turned mill
    body = S.Displace(body, lambda P: 0.012 * np.abs(np.sin(np.arctan2(P[:, 1], P[:, 0]) * 12))
                      * (P[:, 2] < 1.25) * (P[:, 2] > 0.2))
    legs = []
    for i in range(3):
        a = i * 2 * math.pi / 3
        legs.append(S.Capsule((0.4 * math.cos(a), 0.4 * math.sin(a), 0.4),
                              (0.62 * math.cos(a), 0.62 * math.sin(a), 0.02), 0.07, 0.05, color=BRASS, label="leg"))
        legs.append(S.Sphere((0.62 * math.cos(a), 0.62 * math.sin(a), 0.04), 0.1, color=BRASS, label="leg"))
    return S.Union([body] + legs, k=0.04)


def build_ship(coll):
    root = bpy.data.objects.new("ship", None)
    coll.objects.link(root)
    f = ship_field()
    ob = C.mesh_from_field("ship.body", f, (-0.9, -0.9, -0.1), (0.9, 0.9, 2.4), 0.012, coll)
    ob.data.materials.append(C.mat_attr("ship.mat", rough=0.35, coat=0.4))
    brass = C.mat_plain("ship.brass", BRASS, rough=0.25, metal=1.0)
    copper = C.mat_plain("ship.copper", COPPER, rough=0.3, metal=1.0)
    ob.data.materials.append(brass)
    ob.data.materials.append(copper)
    C.assign_by_label(ob, {"band": 1, "knob": 1, "leg": 1, "crown": 2})
    ob.parent = root
    # portholes: glowing discs around the waist
    glow = C.mat_plain("ship.porthole", (1, 0.8, 0.5), emit=(1.0, 0.72, 0.4), emit_strength=8.0)
    for i in range(6):
        a = i * math.pi / 3
        p = _cyl(f"ship.port{i}", 0.13, 0.05, (0.555 * math.cos(a), 0.555 * math.sin(a), 1.05), glow, coll, 24,
                 rot=(0, math.pi / 2, a))
        p.parent = root
        r = bpy.ops.mesh.primitive_torus_add(major_radius=0.14, minor_radius=0.025,
                                             location=(0.575 * math.cos(a), 0.575 * math.sin(a), 1.05),
                                             rotation=(0, math.pi / 2, a))
        ring = bpy.context.active_object
        for c in ring.users_collection:
            c.objects.unlink(ring)
        coll.objects.link(ring)
        ring.data.materials.append(brass)
        ring.parent = root
    # a soft light under it, and its glow on the snow
    ld = bpy.data.lights.new("ship.underglow", "POINT")
    ld.energy = 400
    ld.color = (0.6, 0.5, 1.0)
    ld.shadow_soft_size = 0.5
    lo = bpy.data.objects.new("ship.underglow", ld)
    lo.location = (0, 0, -0.3)
    coll.objects.link(lo)
    lo.parent = root
    return root


# ------------------------------------------------------------------ build

def build(time="night", coll=None):
    coll = coll or C.collection("petersburg")
    M = mats(time)
    rng = random.Random(11)
    # the embankment street and the frozen river
    _box("street", (120, 18, 0.2), (0, -8, -0.1), M["snow"], coll)
    _box("parapet", (120, 0.5, 0.9), (0, -17, 0.45), M["white"], coll, 0.05)
    _box("parapet_snow", (120, 0.55, 0.12), (0, -17, 0.95), M["snow"], coll, 0.04)
    _box("river", (400, 140, 0.2), (0, -88, -1.5), M["ice"], coll)
    # snow drifts along the house fronts
    for i in range(30):
        x = rng.uniform(-40, 40)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=rng.uniform(0.5, 1.4), location=(x, rng.uniform(-1.6, -0.6), -0.3))
        d = bpy.context.active_object
        d.scale = (2.0, 0.8, 0.45)
        for c in d.users_collection:
            c.objects.unlink(d)
        coll.objects.link(d)
        d.data.materials.append(M["snow"])
        bpy.ops.object.shade_smooth()
    # the houses: Euler's in the middle
    x = -34.0
    colours = ["green", "pink", "blue", "ochre", "white", "green", "pink"]
    i = 0
    lit_positions = []
    while x < 34:
        w = rng.uniform(9, 13)
        floors = rng.choice([2, 3, 3])
        study = x <= HOUSE_X < x + w
        lit = set()
        bays = max(3, int(w / 2.1))
        for f in range(floors):
            for b in range(bays):
                if rng.random() < (0.13 if time == "night" else 0.0):
                    lit.add((f, b))
        if study:
            lit.add((1, bays // 2))
            w_study = w
            x_study = x
        col = "ochre" if study else colours[i % len(colours)]
        wins = house(f"house{i}", x, w, floors, col, M, coll, lit, rng, study)
        lit_positions += [p for p, l in wins if l]
        if study:
            study_win = [p for p, l in wins if l and abs(p[2] - (0.9 + 3.4 + 1.55)) < 0.1][0]
            house_plaque(coll, M, (x + 1.4, STREET_Y, 2.4))
        x += w
        i += 1
    bakery_sign(coll, M, (x_study + w_study + 2.5, STREET_Y, 3.3))
    for lx in (-14, -2.5, 9, 21):
        street_lamp(f"lamp{lx}", (lx, -2.2, 0), coll, M, time)
    spire(coll, M)
    # sky dome
    bpy.ops.mesh.primitive_uv_sphere_add(radius=400, segments=64, ring_count=32)
    sky = bpy.context.active_object
    sky.name = "sky"
    for c in sky.users_collection:
        c.objects.unlink(sky)
    coll.objects.link(sky)
    sky.data.materials.append(M["sky"])
    sky.visible_shadow = False
    # the moon, or the sun's first light
    if time == "night":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=7, location=(40, 260, 120))
        moon = bpy.context.active_object
        moon.name = "moon"
        for c in moon.users_collection:
            c.objects.unlink(moon)
        coll.objects.link(moon)
        moon.data.materials.append(C.mat_plain("pb.moon", (1, 1, 0.95), emit=(0.9, 0.95, 1.0), emit_strength=6.0))
        ld = bpy.data.lights.new("moonlight", "SUN")
        ld.energy = 0.25
        ld.color = (0.6, 0.72, 1.0)
        ld.angle = math.radians(2)
        lo = bpy.data.objects.new("moonlight", ld)
        lo.rotation_euler = (math.radians(55), 0, math.radians(200))
        coll.objects.link(lo)
    else:
        ld = bpy.data.lights.new("sun", "SUN")
        ld.energy = 2.2
        ld.color = (1.0, 0.72, 0.55)
        ld.angle = math.radians(3)
        lo = bpy.data.objects.new("sun", ld)
        lo.rotation_euler = (math.radians(80), 0, math.radians(215))
        coll.objects.link(lo)
    ship = build_ship(coll)
    ship.location = SHIP_START
    snow(coll, M, time)
    marks = dict(study_window=study_win, landing=LANDING, ship=ship.name)
    bpy.context.scene["petersburg_marks"] = {k: list(v) if not isinstance(v, str) else v for k, v in marks.items()}
    return dict(marks=marks, coll=coll)


def snow(coll, M, time, count=6000):
    """Falling snow: a cloud of flakes in a box round the camera's view,
    each drifting down on its own sine. Geometry nodes would be tidier;
    this is a particle system, which renders headless without fuss."""
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -8, 14))
    em = bpy.context.active_object
    em.name = "snow_emitter"
    em.scale = (40, 20, 1)
    for c in em.users_collection:
        c.objects.unlink(em)
    coll.objects.link(em)
    em.hide_render = False
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.025)
    flake = bpy.context.active_object
    flake.name = "snow_flake"
    for c in flake.users_collection:
        c.objects.unlink(flake)
    coll.objects.link(flake)
    flake.data.materials.append(C.mat_plain("pb.flake", (1, 1, 1), rough=0.5, emit=(0.8, 0.85, 1.0),
                                            emit_strength=0.6 if time == "night" else 0.2))
    flake.hide_render = True
    flake.location = (0, 0, -50)
    ps = em.modifiers.new("snow", "PARTICLE_SYSTEM").particle_system
    st = ps.settings
    st.count = count
    st.frame_start = -300
    st.frame_end = 9000
    st.lifetime = 400
    st.emit_from = "FACE"
    st.normal_factor = 0.0
    st.effector_weights.gravity = 0.03
    st.brownian_factor = 0.15
    st.render_type = "OBJECT"
    st.instance_object = flake
    st.particle_size = 1.0
    st.size_random = 0.6
    st.use_rotations = True
    em.show_instancer_for_render = False
    return em
