"""Highway drive scene builder for Blender 5.x / EEVEE.

Builds a curving dual carriageway, populates it with CC0 Kenney vehicles,
lights it from a Poly Haven HDRI and shades everything with a toon ramp laid
over real lighting -- cartoonish forms, believable light.

Run headless:
    blender -b -P scene.py -- --look day --out /tmp/f.png --still 8
"""

import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Vector, Quaternion, Matrix

ASSETS = "/Users/john/git/adult/assets"
GLB = os.path.join(ASSETS, "cars/kenney/Models/GLB format")
HDRI = os.path.join(ASSETS, "hdri")

# ---------------------------------------------------------------- look presets

LOOKS = {
    "day": dict(
        sun_elev=52.0, sun_rot=38.0, sky_strength=0.11, dust=1.0, ozone=1.6,
        sun_energy=1.70, soft_sun=6.2, soft_sky=0.20, sun_color=(1.0, 0.97, 0.90), horizon=(0.52, 0.66, 0.85),
        bands=[(0.34, 0.62), (0.52, 0.86), (0.78, 1.0)],
        fog=(0.66, 0.76, 0.90), fog_density=0.00070, fog_start=70.0,
        fog_max=0.80, headlights=False, stars=False,
        cloud_top=(1.0, 0.99, 0.97), cloud_base=(0.72, 0.77, 0.86),
        cloud_strength=2.6,
    ),
    "golden": dict(
        sun_elev=5.5, sun_rot=-118.0, sky_strength=0.10, dust=3.4, ozone=2.4,
        sun_energy=1.62, soft_sun=5.8, soft_sky=0.20, sun_color=(1.0, 0.68, 0.36), horizon=(0.95, 0.66, 0.38),
        bands=[(0.30, 0.55), (0.50, 0.84), (0.76, 1.0)],
        fog=(0.88, 0.68, 0.48), fog_density=0.00105, fog_start=80.0,
        fog_max=0.72, headlights=False, stars=False,
        cloud_top=(1.0, 0.86, 0.66), cloud_base=(0.52, 0.44, 0.52),
        cloud_strength=2.2,
    ),
    "dusk": dict(
        sun_elev=-2.4, sun_rot=-118.0, sky_strength=0.16, dust=4.2, ozone=3.2,
        sun_energy=0.42, soft_sun=1.95, soft_sky=0.62, sun_color=(1.0, 0.55, 0.30), horizon=(0.82, 0.48, 0.38),
        bands=[(0.26, 0.46), (0.46, 0.74), (0.72, 1.0)],
        fog=(0.68, 0.45, 0.42), fog_density=0.00150, fog_start=60.0,
        fog_max=0.78, headlights=True, stars=True,
        cloud_top=(0.85, 0.60, 0.52), cloud_base=(0.26, 0.24, 0.34),
        cloud_strength=0.8,
    ),
    "night": dict(
        sun_elev=-14.0, sun_rot=150.0, sky_strength=2.60, dust=0.9, ozone=1.0,
        sun_energy=0.05, soft_sun=0.26, soft_sky=2.60, sun_color=(0.52, 0.64, 1.0), horizon=(0.06, 0.08, 0.15),
        bands=[(0.18, 0.30), (0.40, 0.62), (0.70, 1.0)],
        fog=(0.05, 0.07, 0.14), fog_density=0.00320, fog_start=45.0,
        fog_max=0.88, headlights=True, stars=True,
        cloud_top=(0.16, 0.19, 0.28), cloud_base=(0.05, 0.06, 0.11),
        cloud_strength=0.55,
    ),
}

STYLE = "soft"

LANE_W = 3.65
LANES = 3
MEDIAN = 2.2          # half-width of the central reservation
SHOULDER = 2.6
CARRIAGE = LANES * LANE_W


# ------------------------------------------------------------ road centreline

class Road:
    """Centreline as functions of distance s (metres)."""

    def __init__(self, curve=1.0, hills=1.0, seed=7):
        r = random.Random(seed)
        self.curve = curve
        self.hills = hills
        self.p = [r.uniform(0, math.tau) for _ in range(6)]

    def x(self, s):
        p = self.p
        return self.curve * (
            26.0 * math.sin(s / 420.0 + p[0])
            + 13.0 * math.sin(s / 170.0 + p[1])
            + 5.0 * math.sin(s / 79.0 + p[2])
        )

    def z(self, s):
        p = self.p
        return self.hills * (
            7.0 * math.sin(s / 560.0 + p[3])
            + 3.0 * math.sin(s / 230.0 + p[4])
            + 1.1 * math.sin(s / 96.0 + p[5])
        )

    def point(self, s, u=0.0, lift=0.0):
        """World position at distance s, lateral offset u, vertical lift."""
        d = 0.5
        tx = (self.x(s + d) - self.x(s - d)) / (2 * d)
        tz = (self.z(s + d) - self.z(s - d)) / (2 * d)
        # tangent in XY plane is (tx, 1); left normal is (1, -tx) normalised
        n = math.hypot(tx, 1.0)
        nx, ny = 1.0 / n, -tx / n
        return Vector((self.x(s) + nx * u, s + ny * u, self.z(s) + lift + tz * 0.0))

    def heading(self, s):
        d = 0.5
        tx = (self.x(s + d) - self.x(s - d)) / (2 * d)
        return math.atan2(-tx, 1.0)

    def pitch(self, s):
        d = 2.0
        tz = (self.z(s + d) - self.z(s - d)) / (2 * d)
        return math.atan2(tz, 1.0)


# ------------------------------------------------------------------- materials

def _ramp(nt, bands, name="ramp"):
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.name = name
    ramp = cr.color_ramp
    ramp.interpolation = "B_SPLINE"
    while len(ramp.elements) > 1:
        ramp.elements.remove(ramp.elements[-1])
    ramp.elements[0].position = 0.0
    ramp.elements[0].color = (bands[0][1] * 0.55, bands[0][1] * 0.55, bands[0][1] * 0.60, 1)
    for pos, val in bands:
        e = ramp.elements.new(pos)
        e.color = (val, val, val, 1)
    return cr



def _fog(nt, color_out, look):
    """Mix a colour toward the horizon by camera distance: 1 - exp(-d/D)."""
    D = 1.0 / max(1e-5, look["fog_density"])
    cam = nt.nodes.new("ShaderNodeCameraData")
    near = nt.nodes.new("ShaderNodeMath")
    near.operation = "SUBTRACT"
    near.inputs[1].default_value = look.get("fog_start", 0.0)
    near.use_clamp = False
    clamp0 = nt.nodes.new("ShaderNodeMath")
    clamp0.operation = "MAXIMUM"
    clamp0.inputs[1].default_value = 0.0
    div = nt.nodes.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = D
    neg = nt.nodes.new("ShaderNodeMath")
    neg.operation = "MULTIPLY"
    neg.inputs[1].default_value = -1.0
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[0].default_value = 1.0
    nt.links.new(cam.outputs["View Distance"], near.inputs[0])
    nt.links.new(near.outputs[0], clamp0.inputs[0])
    nt.links.new(clamp0.outputs[0], div.inputs[0])
    nt.links.new(div.outputs[0], neg.inputs[0])
    nt.links.new(neg.outputs[0], ex.inputs[0])
    nt.links.new(ex.outputs[0], sub.inputs[1])
    cap = nt.nodes.new("ShaderNodeMath")
    cap.operation = "MULTIPLY"
    cap.inputs[1].default_value = look.get("fog_max", 0.82)
    nt.links.new(sub.outputs[0], cap.inputs[0])
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MIX"
    mix.inputs["Color2"].default_value = (*look["fog"], 1)
    nt.links.new(cap.outputs[0], mix.inputs["Factor"])
    nt.links.new(color_out, mix.inputs["Color1"])
    return mix.outputs["Color"]



def _base_colour(nt, base_color, texture, hue, noise, noise_scale):
    """Shared colour source: palette atlas or flat colour, plus mottling."""
    if texture is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = texture
        tex.interpolation = "Closest"
        uv = nt.nodes.new("ShaderNodeUVMap")
        nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
        out = tex.outputs["Color"]
        if hue or STYLE == "soft":
            hs = nt.nodes.new("ShaderNodeHueSaturation")
            hs.inputs["Hue"].default_value = 0.5 + (0.0 if STYLE == "soft" else hue)
            hs.inputs["Saturation"].default_value = (
                1.12 if STYLE == "soft" else 1.02)
            nt.links.new(out, hs.inputs["Color"])
            out = hs.outputs["Color"]
        return out
    rgb = nt.nodes.new("ShaderNodeRGB")
    rgb.outputs[0].default_value = (*base_color, 1)
    out = rgb.outputs["Color"]
    if STYLE == "soft":
        sat = nt.nodes.new("ShaderNodeHueSaturation")
        sat.inputs["Saturation"].default_value = 1.10
        nt.links.new(out, sat.inputs["Color"])
        out = sat.outputs["Color"]
    if noise > 0:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise_scale
        tex.inputs["Detail"].default_value = 8.0
        tex.inputs["Roughness"].default_value = 0.62
        cramp = nt.nodes.new("ShaderNodeValToRGB")
        cr = cramp.color_ramp
        cr.elements[0].position = 0.34
        cr.elements[0].color = (1 - noise, 1 - noise, 1 - noise, 1)
        cr.elements[1].position = 0.70
        v = 1 + noise * 0.75
        cr.elements[1].color = (v, v, v, 1)
        nt.links.new(tex.outputs["Fac"], cramp.inputs["Factor"])
        mul = nt.nodes.new("ShaderNodeMixRGB")
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        nt.links.new(out, mul.inputs["Color1"])
        nt.links.new(cramp.outputs["Color"], mul.inputs["Color2"])
        out = mul.outputs["Color"]
    return out


def _soft_material(mat, nt, out, name, base_color, look, rough, texture, hue,
                   noise, noise_scale, emission, bump=0.0, bump_scale=40.0):
    """Physically-lit shading: rounded forms and real light, no cel bands.

    Banded ramps read as anime; the reference here is soft key light, real
    specular falloff and coloured bounce, with the stylisation carried by the
    shapes instead.
    """
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = 0.0
    col = _base_colour(nt, base_color, texture, hue, noise, noise_scale)
    nt.links.new(col, bsdf.inputs["Base Color"])
    if bump > 0:
        # breaks a smooth canopy into lit and shaded clumps without geometry
        bn = nt.nodes.new("ShaderNodeTexNoise")
        bn.inputs["Scale"].default_value = bump_scale
        bn.inputs["Detail"].default_value = 9.0
        bn.inputs["Roughness"].default_value = 0.70
        bmp = nt.nodes.new("ShaderNodeBump")
        bmp.inputs["Strength"].default_value = bump
        bmp.inputs["Distance"].default_value = 0.25
        nt.links.new(bn.outputs["Fac"], bmp.inputs["Height"])
        nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    if "paint" in name:
        for sock, val in (("Coat Weight", 0.85), ("Coat Roughness", 0.08)):
            if sock in bsdf.inputs:
                bsdf.inputs[sock].default_value = val
    if emission:
        nt.links.new(col, bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission

    # haze: blend the whole shaded result toward the horizon, not just albedo
    fogsh = nt.nodes.new("ShaderNodeEmission")
    fogsh.inputs["Color"].default_value = (*look["fog"], 1)
    fogsh.inputs["Strength"].default_value = look.get("soft_sky", 1.0)
    fac = _fog_factor(nt, look)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fac, mix.inputs["Fac"])
    nt.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    nt.links.new(fogsh.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def _fog_factor(nt, look):
    """0..1 haze weight from camera distance, shared by both styles."""
    D = 1.0 / max(1e-5, look["fog_density"])
    cam = nt.nodes.new("ShaderNodeCameraData")
    near = nt.nodes.new("ShaderNodeMath")
    near.operation = "SUBTRACT"
    near.inputs[1].default_value = look.get("fog_start", 0.0)
    clamp0 = nt.nodes.new("ShaderNodeMath")
    clamp0.operation = "MAXIMUM"
    clamp0.inputs[1].default_value = 0.0
    div = nt.nodes.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = D
    neg = nt.nodes.new("ShaderNodeMath")
    neg.operation = "MULTIPLY"
    neg.inputs[1].default_value = -1.0
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[0].default_value = 1.0
    cap = nt.nodes.new("ShaderNodeMath")
    cap.operation = "MULTIPLY"
    cap.inputs[1].default_value = look.get("fog_max", 0.82)
    nt.links.new(cam.outputs["View Distance"], near.inputs[0])
    nt.links.new(near.outputs[0], clamp0.inputs[0])
    nt.links.new(clamp0.outputs[0], div.inputs[0])
    nt.links.new(div.outputs[0], neg.inputs[0])
    nt.links.new(neg.outputs[0], ex.inputs[0])
    nt.links.new(ex.outputs[0], sub.inputs[1])
    nt.links.new(sub.outputs[0], cap.inputs[0])
    return cap.outputs[0]


def toon_material(name, base_color, look, rough=0.45, spec=0.35,
                  texture=None, rim=0.25, emission=None, hue=0.0, noise=0.0,
                  noise_scale=38.0, bump=0.0, bump_scale=40.0):
    """Diffuse -> ShaderToRGB -> banded ramp -> tinted, plus sharp spec + rim."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")

    if STYLE == "soft":
        return _soft_material(mat, nt, out, name, base_color, look, rough,
                              texture, hue, noise, noise_scale, emission,
                              bump, bump_scale)

    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1, 1, 1, 1)
    s2rgb = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(diff.outputs["BSDF"], s2rgb.inputs["Shader"])

    cr = _ramp(nt, look["bands"])
    nt.links.new(s2rgb.outputs["Color"], cr.inputs["Factor"])

    # base colour, either flat or from the Kenney palette atlas
    if texture is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = texture
        tex.interpolation = "Closest"
        uv = nt.nodes.new("ShaderNodeUVMap")
        nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
        base_out = tex.outputs["Color"]
        if hue:
            hs = nt.nodes.new("ShaderNodeHueSaturation")
            hs.inputs["Hue"].default_value = 0.5 + hue
            hs.inputs["Saturation"].default_value = 1.02
            nt.links.new(base_out, hs.inputs["Color"])
            base_out = hs.outputs["Color"]
    else:
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = (*base_color, 1)
        base_out = rgb.outputs["Color"]
        if noise > 0:
            # aggregate mottling and tar seams so tarmac is not a flat slab
            tex = nt.nodes.new("ShaderNodeTexNoise")
            tex.inputs["Scale"].default_value = noise_scale
            tex.inputs["Detail"].default_value = 6.0
            tex.inputs["Roughness"].default_value = 0.62
            cramp = nt.nodes.new("ShaderNodeValToRGB")
            cr2 = cramp.color_ramp
            cr2.elements[0].position = 0.34
            cr2.elements[0].color = (1 - noise, 1 - noise, 1 - noise, 1)
            cr2.elements[1].position = 0.70
            cr2.elements[1].color = (1 + noise * 0.75, 1 + noise * 0.75,
                                     1 + noise * 0.75, 1)
            nt.links.new(tex.outputs["Fac"], cramp.inputs["Factor"])
            nmul = nt.nodes.new("ShaderNodeMixRGB")
            nmul.blend_type = "MULTIPLY"
            nmul.inputs["Factor"].default_value = 1.0
            nt.links.new(base_out, nmul.inputs["Color1"])
            nt.links.new(cramp.outputs["Color"], nmul.inputs["Color2"])
            base_out = nmul.outputs["Color"]

    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(cr.outputs["Color"], mul.inputs["Color1"])
    nt.links.new(base_out, mul.inputs["Color2"])

    # sharp stylised specular
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Roughness"].default_value = rough
    g2rgb = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(gloss.outputs["BSDF"], g2rgb.inputs["Shader"])
    gramp = nt.nodes.new("ShaderNodeValToRGB")
    gr = gramp.color_ramp
    gr.interpolation = "CONSTANT"
    gr.elements[0].position = 0.0
    gr.elements[0].color = (0, 0, 0, 1)
    gr.elements[1].position = max(0.02, 1.0 - spec)
    gr.elements[1].color = (spec * 0.45, spec * 0.45, spec * 0.45, 1)
    nt.links.new(g2rgb.outputs["Color"], gramp.inputs["Factor"])

    add = nt.nodes.new("ShaderNodeMixRGB")
    add.blend_type = "ADD"
    add.inputs["Factor"].default_value = 1.0
    nt.links.new(mul.outputs["Color"], add.inputs["Color1"])
    nt.links.new(gramp.outputs["Color"], add.inputs["Color2"])

    # fresnel rim so silhouettes separate from the background
    last = add
    if rim > 0:
        fres = nt.nodes.new("ShaderNodeFresnel")
        fres.inputs["IOR"].default_value = 1.32
        frim = nt.nodes.new("ShaderNodeValToRGB")
        fr = frim.color_ramp
        fr.interpolation = "EASE"
        fr.elements[0].position = 0.55
        fr.elements[0].color = (0, 0, 0, 1)
        fr.elements[1].position = 0.95
        c = look["horizon"]
        fr.elements[1].color = (c[0] * rim, c[1] * rim, c[2] * rim, 1)
        nt.links.new(fres.outputs["Factor"], frim.inputs["Factor"])
        add2 = nt.nodes.new("ShaderNodeMixRGB")
        add2.blend_type = "ADD"
        add2.inputs["Factor"].default_value = 1.0
        nt.links.new(add.outputs["Color"], add2.inputs["Color1"])
        nt.links.new(frim.outputs["Color"], add2.inputs["Color2"])
        last = add2

    fogged = _fog(nt, last.outputs["Color"], look)
    emit = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(fogged, emit.inputs["Color"])
    if emission:
        emit.inputs["Strength"].default_value = emission
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def glow_material(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*color, 1)
    emit.inputs["Strength"].default_value = strength
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


# ------------------------------------------------------------------- geometry

def mesh_from(name, verts, faces, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    bpy.context.collection.objects.link(ob)
    return ob


def strip(road, s0, s1, step, u_left, u_right, lift, name, mat):
    """A flat ribbon following the road between two lateral offsets."""
    verts, faces = [], []
    n = 0
    s = s0
    while s <= s1:
        verts.append(road.point(s, u_left, lift))
        verts.append(road.point(s, u_right, lift))
        if n > 0:
            b = (n - 1) * 2
            faces.append((b, b + 1, b + 3, b + 2))
        n += 1
        s += step
    return mesh_from(name, verts, faces, mat)


def dashes(road, s0, s1, u, lift, name, mat, dash=3.0, gap=9.0, width=0.14):
    verts, faces = [], []
    s = s0
    i = 0
    while s < s1:
        a, b = s, min(s + dash, s1)
        for ss in (a, b):
            verts.append(road.point(ss, u - width, lift))
            verts.append(road.point(ss, u + width, lift))
        faces.append((i, i + 1, i + 3, i + 2))
        i += 4
        s += dash + gap
    if not faces:
        return None
    return mesh_from(name, verts, faces, mat)


def barrier(road, s0, s1, step, u, height, halfw, name, mat):
    """Extruded upright slab along the road (jersey barrier / guardrail)."""
    verts, faces = [], []
    n = 0
    s = s0
    while s <= s1:
        verts.append(road.point(s, u - halfw, 0.02))
        verts.append(road.point(s, u + halfw, 0.02))
        verts.append(road.point(s, u + halfw * 0.55, height))
        verts.append(road.point(s, u - halfw * 0.55, height))
        if n > 0:
            b = (n - 1) * 4
            faces.append((b + 3, b + 2, b + 6, b + 7))   # top
            faces.append((b + 0, b + 3, b + 7, b + 4))   # left face
            faces.append((b + 2, b + 1, b + 5, b + 6))   # right face
        n += 1
        s += step
    return mesh_from(name, verts, faces, mat)


def terrain(road, s0, s1, mat, half=260.0, step=24.0):
    """Rolling ground either side of the carriageway."""
    verts, faces = [], []
    us = [u for u in range(int(-half), int(half) + 1, int(step))]
    rows = 0
    s = s0
    rng = random.Random(3)
    while s <= s1:
        for u in us:
            lift = -0.35
            d = abs(u)
            if d > 30:
                far = min(1.0, (d - 30.0) / 150.0)
                lift += far * (16.0 * math.sin(u * 0.0075 + s * 0.0021)
                               + 7.0 * math.sin(s * 0.0053 + u * 0.004)
                               + 3.0 * math.sin(u * 0.02))
                lift += rng.uniform(-0.35, 0.35)
            verts.append(road.point(s, float(u), lift))
        if rows > 0:
            b0 = (rows - 1) * len(us)
            b1 = rows * len(us)
            for i in range(len(us) - 1):
                faces.append((b0 + i, b0 + i + 1, b1 + i + 1, b1 + i))
        rows += 1
        s += step
    return mesh_from("terrain", verts, faces, mat)


# ------------------------------------------------------------------- vehicles

CAR_KINDS = [
    ("sedan", 1.00), ("sedan-sports", 1.00), ("suv", 1.06), ("suv-luxury", 1.06),
    ("hatchback-sports", 0.96), ("taxi", 1.00), ("van", 1.10), ("delivery", 1.14),
    ("truck", 1.20), ("truck-flat", 1.22), ("police", 1.00), ("ambulance", 1.16),
    ("garbage-truck", 1.26), ("firetruck", 1.30),
]

# Kenney bodies are ~2.55 long and deliberately chunky. The stretch to a real
# footprint (about 1.8 x 4.4 x 1.7 m) is baked into the body meshes and the
# wheel positions, NOT put on the car root: a non-uniform parent scale is
# applied after the child's own rotation, which shears a spinning wheel into a
# wobbling ellipse.
CAR_SCALE = 1.55
STRETCH_X = 1.20 / 1.55
STRETCH_Y = 1.72 / 1.55

# The models face -Y: front wheels sit at negative Y, rear wheels at positive.
# Everything downstream drives along +Y, so each car is turned to match.
MODEL_FLIP = math.pi
WHEEL_RADIUS = 0.30 * CAR_SCALE


def import_prototypes(look, kinds):
    """Import each GLB once, re-shade it toon, and hide the originals."""
    hidden = bpy.data.collections.new("prototypes")
    bpy.context.scene.collection.children.link(hidden)
    hidden.hide_render = True
    hidden.hide_viewport = True

    protos = {}
    colormap = None
    for kind, _ in kinds:
        path = os.path.join(GLB, kind + ".glb")
        if not os.path.exists(path):
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new = [o for o in bpy.data.objects if o not in before]
        parts = [o for o in new if o.type == "MESH"]
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            hidden.objects.link(o)
        # grab the palette atlas from the imported material
        for o in parts:
            for slot in o.material_slots:
                if slot.material and slot.material.use_nodes:
                    for n in slot.material.node_tree.nodes:
                        if n.type == "TEX_IMAGE" and n.image:
                            colormap = n.image
        protos[kind] = parts
    return protos, colormap, hidden




def proportion_prototypes(protos):
    """Stretch bodies to a real footprint; move wheels, never stretch them."""
    seen = set()
    for parts in protos.values():
        for ob in parts:
            is_wheel = "wheel" in ob.name.lower()
            loc = ob.location.copy()
            ob.location = Vector((loc.x * STRETCH_X, loc.y * STRETCH_Y, loc.z))
            if is_wheel or ob.data.name in seen:
                continue
            seen.add(ob.data.name)
            me = ob.data
            for v in me.vertices:
                v.co.x *= STRETCH_X
                v.co.y *= STRETCH_Y


def round_prototypes(protos, amount, crease=0.75):
    """Round the shared meshes without dissolving the car.

    Plain Catmull-Clark on a low-poly body shrinks it and thins the window
    frames. Creasing the defining edges first holds those in place, so the
    gentle surfaces round while the silhouette survives. Baked into the
    prototype mesh data before instancing, so 14 models pay for it, not 120
    vehicles.
    """
    if amount <= 0:
        return
    levels = 2 if amount >= 0.75 else 1
    sharp = math.radians(48.0)
    seen = set()
    for parts in protos.values():
        for ob in parts:
            if ob.data.name in seen:
                continue
            seen.add(ob.data.name)
            me = ob.data

            bm = bmesh.new()
            bm.from_mesh(me)
            bm.edges.ensure_lookup_table()
            angles = []
            for e in bm.edges:
                try:
                    angles.append(e.calc_face_angle(0.0))
                except Exception:
                    angles.append(0.0)
            bm.free()

            attr = me.attributes.get("crease_edge")
            if attr is None:
                attr = me.attributes.new("crease_edge", "FLOAT", "EDGE")
            for i, ang in enumerate(angles):
                attr.data[i].value = crease if ang > sharp else 0.0

            s = ob.modifiers.new("smooth", "SUBSURF")
            s.levels = s.render_levels = levels
            s.use_creases = True
            s.use_limit_surface = True
            b = ob.modifiers.new("round", "BEVEL")
            b.width = 0.012 * min(amount, 1.5)
            b.segments = 2
            b.limit_method = "ANGLE"
            b.angle_limit = math.radians(38.0)

            dg = bpy.context.evaluated_depsgraph_get()
            baked = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
            ob.modifiers.clear()
            old_me = ob.data
            ob.data = baked
            if old_me.users == 0:
                bpy.data.meshes.remove(old_me)
            for poly in baked.polygons:
                poly.use_smooth = True


def make_car(protos, kind, name, body_mat, wheel_mat, glass_mat):
    """Linked duplicate of a prototype: shares mesh data, own transform.

    Each part keeps the world transform it had in the GLB, expressed relative
    to the car root -- so wheels stay in their arches instead of collapsing
    onto the origin.
    """
    root = bpy.data.objects.new(name, None)
    root.empty_display_size = 0.4
    bpy.context.collection.objects.link(root)
    wheels = []
    for part in protos[kind]:
        ob = bpy.data.objects.new(name + "_" + part.name, part.data)
        bpy.context.collection.objects.link(ob)
        ob.parent = root
        ob.matrix_parent_inverse = Matrix.Identity(4)
        loc, quat, scl = part.matrix_world.decompose()
        ob.location = loc
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = quat
        ob.scale = scl
        is_wheel = "wheel" in part.name.lower()
        if is_wheel:
            d = part.dimensions
            axis = "XYZ"[min(range(3), key=lambda i: d[i])]
            wheels.append(dict(ob=ob, base=quat.copy(), axis=axis))
        ob.data.materials.clear()
        ob.data.materials.append(wheel_mat if is_wheel else body_mat)
    root.scale = (CAR_SCALE,) * 3
    return root, wheels


def outline(ob, thickness, mat):
    """Inverted-hull outline: solidified shell, flipped, backface-culled."""
    for child in ob.children:
        if child.type != "MESH":
            continue
        if len(child.data.materials) < 2:
            child.data.materials.append(mat)
        m = child.modifiers.new("outline", "SOLIDIFY")
        m.thickness = thickness
        m.offset = 1.0
        m.use_flip_normals = True
        m.use_rim = False
        m.material_offset = 1
        m.material_offset_rim = 1


# ---------------------------------------------------------------------- world

def setup_world(look):
    """Procedural sky so the background matches the stylised geometry.

    A photographic HDRI puts real trees on the horizon behind toy cars; the
    Nishita sky gives the same light with none of the clash.
    """
    w = bpy.data.worlds.new("sky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = (
        look["soft_sky"] if STYLE == "soft" else look["sky_strength"])

    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(look["sun_elev"])
    sky.sun_rotation = math.radians(look["sun_rot"])
    sky.aerosol_density = look["dust"]
    sky.ground_albedo = 0.22
    sky.ozone_density = look["ozone"]
    sky.air_density = 1.0
    sky.sun_intensity = 0.6 if look["sun_elev"] > 0 else 0.0
    sky.sun_disc = look["sun_elev"] > 2.0
    sky_out = sky.outputs["Color"]
    if look.get("stars"):
        coord = nt.nodes.new("ShaderNodeTexCoord")
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.feature = "F1"
        vor.inputs["Scale"].default_value = 110.0
        nt.links.new(coord.outputs["Generated"], vor.inputs["Vector"])
        pts = nt.nodes.new("ShaderNodeValToRGB")
        pr = pts.color_ramp
        pr.interpolation = "CONSTANT"
        pr.elements[0].position = 0.0
        pr.elements[0].color = (1, 1, 1, 1)
        pr.elements[1].position = 0.060
        pr.elements[1].color = (0, 0, 0, 1)
        nt.links.new(vor.outputs["Distance"], pts.inputs["Factor"])

        # vary brightness so the field is not a uniform grid of identical dots
        vary = nt.nodes.new("ShaderNodeTexNoise")
        vary.inputs["Scale"].default_value = 9.0
        nt.links.new(coord.outputs["Generated"], vary.inputs["Vector"])
        gain = nt.nodes.new("ShaderNodeMixRGB")
        gain.blend_type = "MULTIPLY"
        gain.inputs["Factor"].default_value = 1.0
        nt.links.new(pts.outputs["Color"], gain.inputs["Color1"])
        nt.links.new(vary.outputs["Fac"], gain.inputs["Color2"])

        # keep them above the horizon
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
        mask = nt.nodes.new("ShaderNodeMapRange")
        mask.inputs["From Min"].default_value = 0.005
        mask.inputs["From Max"].default_value = 0.10
        mask.clamp = True
        nt.links.new(sep.outputs["Z"], mask.inputs["Value"])
        masked = nt.nodes.new("ShaderNodeMixRGB")
        masked.blend_type = "MULTIPLY"
        masked.inputs["Factor"].default_value = 1.0
        nt.links.new(gain.outputs["Color"], masked.inputs["Color1"])
        nt.links.new(mask.outputs["Result"], masked.inputs["Color2"])

        gainup = nt.nodes.new("ShaderNodeMixRGB")
        gainup.blend_type = "MULTIPLY"
        gainup.inputs["Factor"].default_value = 1.0
        g = look.get("star_gain", 2.5)
        gainup.inputs["Color2"].default_value = (g, g, g, 1)
        nt.links.new(masked.outputs["Color"], gainup.inputs["Color1"])

        boost = nt.nodes.new("ShaderNodeMixRGB")
        boost.blend_type = "ADD"
        boost.inputs["Factor"].default_value = 1.0
        nt.links.new(sky_out, boost.inputs["Color1"])
        nt.links.new(gainup.outputs["Color"], boost.inputs["Color2"])
        sky_out = boost.outputs["Color"]

    nt.links.new(sky_out, bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

    sun = bpy.data.lights.new("sun", type="SUN")
    sun.energy = (
        look["soft_sun"] if STYLE == "soft" else look["sun_energy"])
    sun.color = look["sun_color"]
    sun.angle = math.radians(1.8)
    sun.use_shadow = True
    sun.use_shadow_jitter = True
    sun.shadow_filter_radius = 1.2
    try:
        sun.shadow_maximum_resolution = 0.00008
    except Exception:
        pass
    so = bpy.data.objects.new("sun", sun)
    so.rotation_euler = (math.radians(90.0 - look["sun_elev"]), 0.0,
                         math.radians(look["sun_rot"] + 90.0))
    bpy.context.collection.objects.link(so)
    return so


def setup_render(cfg, look):
    scn = bpy.context.scene
    scn.render.engine = "BLENDER_EEVEE"
    scn.render.resolution_x = cfg["width"]
    scn.render.resolution_y = cfg["height"]
    scn.render.resolution_percentage = 100
    scn.render.fps = cfg["fps"]
    scn.render.film_transparent = False

    ee = scn.eevee
    ee.taa_render_samples = cfg["samples"]
    ee.use_raytracing = True
    ee.ray_tracing_method = "SCREEN"
    ee.use_shadows = True

    fid = cfg["fidelity"]
    rt = ee.ray_tracing_options
    if fid == "max":
        # full-resolution tracing; the defaults trace at half res with a
        # quarter-quality screen trace, which softens contact shadows and
        # loses the crisp edge the toon bands depend on
        rt.resolution_scale = "1"
        rt.screen_trace_quality = 1.0
        rt.trace_max_roughness = 1.0
        rt.use_denoise = True
        ee.shadow_ray_count = 4
        ee.shadow_step_count = 16
        ee.use_fast_gi = False
    elif fid == "high":
        rt.resolution_scale = "1"
        rt.screen_trace_quality = 0.5
        rt.trace_max_roughness = 0.75
        ee.shadow_ray_count = 3
        ee.shadow_step_count = 12
        ee.use_fast_gi = True
        ee.fast_gi_method = "GLOBAL_ILLUMINATION"
        ee.fast_gi_resolution = "1"
    else:  # draft
        rt.resolution_scale = "2"
        ee.shadow_ray_count = 1
        ee.shadow_step_count = 4
        ee.use_fast_gi = True
        ee.fast_gi_resolution = "2"
    try:
        ee.shadow_resolution_scale = 1.0
    except Exception:
        pass
    try:
        ee.use_volumetric_shadows = False
    except Exception:
        pass
    scn.render.use_motion_blur = cfg["motion_blur"]
    if cfg["motion_blur"]:
        scn.render.motion_blur_shutter = cfg["shutter"]
        scn.render.motion_blur_position = "CENTER"
        ee.motion_blur_steps = max(2, cfg["mb_steps"])

    scn.view_layers[0].use_pass_mist = True
    wo = scn.world.mist_settings
    wo.start = 40.0
    wo.depth = 900.0
    wo.falloff = "INVERSE_QUADRATIC"
    wo.intensity = 0.0

    if STYLE == "soft":
        # real lighting needs a real tonemap; Standard would clip every
        # highlight the Principled specular produces
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Punchy"
    else:
        scn.view_settings.view_transform = "Standard"
        scn.view_settings.look = "None"
    return scn


def setup_compositor(look):
    """Aerial haze from the mist pass, plus a glare bloom on the highlights."""
    scn = bpy.context.scene
    scn.use_nodes = True
    nt = scn.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")

    fog = nt.nodes.new("CompositorNodeMixRGB")
    fog.blend_type = "MIX"
    fog.inputs[2].default_value = (*look["fog"], 1)
    mult = nt.nodes.new("CompositorNodeMath")
    mult.operation = "MULTIPLY"
    mult.inputs[1].default_value = look["fog_density"] * 420.0
    nt.links.new(rl.outputs["Mist"], mult.inputs[0])
    nt.links.new(mult.outputs[0], fog.inputs[0])
    nt.links.new(rl.outputs["Image"], fog.inputs[1])

    glare = nt.nodes.new("CompositorNodeGlare")
    glare.glare_type = "BLOOM"
    glare.quality = "HIGH"
    try:
        glare.mix = -0.62
        glare.threshold = 0.85
        glare.size = 7
    except Exception:
        pass
    nt.links.new(fog.outputs["Image"], glare.inputs["Image"])
    nt.links.new(glare.outputs["Image"], comp.inputs["Image"])


# ---------------------------------------------------------------- scene build

PAINT = [
    (0.78, 0.13, 0.12), (0.10, 0.22, 0.55), (0.86, 0.86, 0.88), (0.13, 0.14, 0.17),
    (0.72, 0.74, 0.76), (0.09, 0.42, 0.30), (0.88, 0.58, 0.10), (0.42, 0.13, 0.42),
    (0.94, 0.80, 0.18), (0.20, 0.52, 0.66),
]


def lane_u(i, oncoming=False):
    u = MEDIAN + LANE_W * (i + 0.5)
    return -u if oncoming else u


_AXIS = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)),
         "Z": Vector((0, 0, 1))}


class Traffic:
    def __init__(self, road, cfg, look, protos, colormap, seed=7):
        self.road = road
        self.cfg = cfg
        rng = random.Random(seed + 11)
        self.cars = []
        self.wheels = {}

        wheel_mat = toon_material("wheel", (0.07, 0.07, 0.08), look, rough=0.62,
                                  spec=0.10, rim=0.10)
        out_mat = glow_material("outline", (0.02, 0.02, 0.03), 0.0)
        self.contact = contact_shadow_material(look)
        # The inverted hull only reads as a line if the camera-facing half of
        # the shell is culled; without this the shell covers the whole car and
        # every vehicle renders as a black blob.
        out_mat.use_backface_culling = True
        boost = 3.0 if STYLE == "soft" else 1.0
        self.lamp_w = glow_material("lamp_w", (1.0, 0.95, 0.82), 14.0 * boost)
        self.lamp_r = glow_material("lamp_r", (1.0, 0.09, 0.05), 6.0 * boost)

        n = int(cfg["traffic"] * 110)
        kinds = [k for k, _ in CAR_KINDS if k in protos]
        span = cfg["speed"] * cfg["duration"] + 700.0

        # eight shared body materials -- one shader compile each, not one per car
        bodies = [
            toon_material(f"paint{j}", PAINT[j % len(PAINT)], look, rough=0.22,
                          spec=0.55,
                          texture=colormap if cfg["use_atlas"] else None,
                          rim=0.30, hue=(j / 8.0) * 0.10 - 0.05)
            for j in range(8)
        ]

        for i in range(n):
            oncoming = (i % 3 == 2)
            kind = rng.choice(kinds)
            lane = rng.randrange(LANES)
            body = bodies[rng.randrange(len(bodies))]
            root, wheels = make_car(protos, kind, f"car{i}", body, wheel_mat, body)
            if cfg["outline"] > 0:
                outline(root, cfg["outline"], out_mat)

            if i == 0 and cfg["camera"] == "chase":
                # the car the chase camera actually follows
                oncoming, lane = False, cfg["lane"] - 1
                kind = "sedan-sports" if "sedan-sports" in protos else kinds[0]
            own_lane = (not oncoming) and (lane == cfg["lane"] - 1)
            if oncoming:
                speed = rng.uniform(0.88, 1.12) * cfg["speed"]
                s0 = rng.uniform(-120.0, span)
            elif own_lane:
                # holds station ahead so it never passes through the camera
                speed = cfg["speed"]
                if i == 0 and cfg["camera"] == "chase":
                    s0 = 4.6
                else:
                    s0 = rng.uniform(34.0, span)
            else:
                speed = rng.uniform(0.80, 1.18) * cfg["speed"]
                s0 = rng.uniform(-260.0, span)
                # keep the neighbouring lanes clear of the start position too
                if abs(s0) < 16.0:
                    s0 += 40.0
            self.cars.append(dict(root=root, wheels=wheels, lane=lane,
                                  oncoming=oncoming, speed=speed, s0=s0,
                                  drift=rng.uniform(0, math.tau)))
            self._contact(root)
            if look["headlights"]:
                self._lamps(root, kind)

    def _contact(self, root):
        bpy.ops.mesh.primitive_plane_add(size=1.0)
        p = bpy.context.object
        p.parent = root
        p.location = (0.0, 0.0, 0.005)
        p.scale = (1.30, 2.90, 1.0)
        p.data.materials.clear()
        p.data.materials.append(self.contact)
        p.visible_shadow = False

    def _lamps(self, root, kind):
        for (dx, dy, dz, mat, size) in [
            (-0.45, 1.24, 0.28, self.lamp_w, 0.16),
            (0.45, 1.24, 0.28, self.lamp_w, 0.16),
            (-0.48, -1.26, 0.34, self.lamp_r, 0.13),
            (0.48, -1.26, 0.34, self.lamp_r, 0.13),
        ]:
            bpy.ops.mesh.primitive_plane_add(size=size)
            p = bpy.context.object
            p.parent = root
            p.location = (dx, dy, dz)
            p.rotation_euler = (math.radians(90), 0, 0)
            p.data.materials.clear()
            p.data.materials.append(mat)

    def update(self, t):
        road = self.road
        for c in self.cars:
            if c["oncoming"]:
                s = c["s0"] - c["speed"] * t
                u = lane_u(c["lane"], True)
                head = road.heading(s) + math.pi + MODEL_FLIP
            else:
                s = c["s0"] + c["speed"] * t
                u = lane_u(c["lane"], False)
                head = road.heading(s) + MODEL_FLIP
            u += 0.12 * math.sin(t * 0.5 + c["drift"])
            pos = road.point(s, u, 0.0)
            root = c["root"]
            root.location = pos
            root.rotation_euler = (road.pitch(s) * (1 if c["oncoming"] else -1),
                                   0.0, head)
            # angle = distance / rolling radius; wrong radius reads as wheelspin
            spin = (s / WHEEL_RADIUS) % math.tau
            for w in c["wheels"]:
                w["ob"].rotation_quaternion = (
                    w["base"] @ Quaternion(_AXIS[w["axis"]], spin))


def build(cfg):
    global STYLE
    STYLE = cfg["style"]
    look = LOOKS[cfg["look"]]
    bpy.ops.wm.read_factory_settings(use_empty=True)

    road = Road(cfg["curve"], cfg["hills"], cfg["seed"])
    s0 = -320.0
    s1 = cfg["speed"] * cfg["duration"] + 900.0

    dark = 1.0
    if STYLE == "soft":
        dark = 0.90 if look["headlights"] else 0.55
    asphalt = toon_material("asphalt", (0.092 * dark, 0.093 * dark, 0.101 * dark),
                            look, rough=0.55,
                            spec=0.16, rim=0.06, noise=0.30, noise_scale=26.0)
    shoulder_m = toon_material("shoulder", (0.125 * dark, 0.122 * dark, 0.126 * dark),
                               look, rough=0.62,
                               spec=0.10, rim=0.05, noise=0.26, noise_scale=44.0)
    paint_w = toon_material("paint_white", (0.92, 0.92, 0.90), look, rough=0.58,
                            spec=0.14, rim=0.10)
    grass = toon_material("grass", (0.16, 0.34, 0.12), look, rough=0.75,
                          spec=0.05, rim=0.08, noise=0.20, noise_scale=7.0)
    concrete = toon_material("concrete", (0.44, 0.44, 0.43), look, rough=0.70,
                             spec=0.10, rim=0.16, noise=0.14, noise_scale=20.0)
    steel = toon_material("steel", (0.55, 0.57, 0.60), look, rough=0.30,
                          spec=0.40, rim=0.24)

    terrain(road, s0, s1, grass)

    step = 2.5
    strip(road, s0, s1, step, MEDIAN, MEDIAN + CARRIAGE, 0.0, "road_r", asphalt)
    strip(road, s0, s1, step, -(MEDIAN + CARRIAGE), -MEDIAN, 0.0, "road_l", asphalt)
    strip(road, s0, s1, step, MEDIAN + CARRIAGE, MEDIAN + CARRIAGE + SHOULDER,
          -0.02, "shoulder_r", shoulder_m)
    strip(road, s0, s1, step, -(MEDIAN + CARRIAGE + SHOULDER), -(MEDIAN + CARRIAGE),
          -0.02, "shoulder_l", shoulder_m)
    strip(road, s0, s1, step, -MEDIAN, MEDIAN, -0.12, "median", grass)

    lift = 0.012
    strip(road, s0, s1, step, MEDIAN + 0.02, MEDIAN + 0.18, lift, "edge_in", paint_w)
    strip(road, s0, s1, step, MEDIAN + CARRIAGE - 0.20, MEDIAN + CARRIAGE - 0.04,
          lift, "edge_out", paint_w)
    strip(road, s0, s1, step, -(MEDIAN + 0.18), -(MEDIAN + 0.02), lift,
          "edge_in_l", paint_w)
    for i in range(1, LANES):
        dashes(road, s0, s1, MEDIAN + LANE_W * i, lift, f"dash{i}", paint_w)
        dashes(road, s0, s1, -(MEDIAN + LANE_W * i), lift, f"dash_l{i}", paint_w)

    barrier(road, s0, s1, 4.0, 0.0, 0.92, 0.42, "jersey", concrete)
    barrier(road, s0, s1, 6.0, MEDIAN + CARRIAGE + SHOULDER + 0.5, 0.70, 0.11,
            "guardrail", steel)

    scenery(road, s0, s1, look, cfg, trees=False)
    plant_trees(road, s0, s1, look, cfg)
    furniture(road, s0, s1, look, cfg)

    protos, colormap, _ = import_prototypes(look, CAR_KINDS)
    proportion_prototypes(protos)
    round_prototypes(protos, cfg["round"])
    traffic = Traffic(road, cfg, look, protos, colormap, cfg["seed"])

    setup_world(look)
    clouds(look, cfg, road)
    cam = bpy.data.cameras.new("cam")
    cam.lens = cfg["lens"]
    if cfg["dof"] > 0:
        cam.dof.use_dof = True
        cam.dof.focus_distance = 26.0
        cam.dof.aperture_fstop = cfg["dof"]
        cam.dof.aperture_blades = 6
    cam.clip_start = 0.12
    cam.clip_end = 3000.0
    cobj = bpy.data.objects.new("cam", cam)
    bpy.context.collection.objects.link(cobj)
    bpy.context.scene.camera = cobj

    if look["headlights"]:
        # real light on the road ahead; the per-car emissive quads only glow
        for side in (-1, 1):
            sl = bpy.data.lights.new(f"beam{side}", type="SPOT")
            sl.energy = 13000.0 if STYLE == "soft" else 2600.0
            sl.color = (1.0, 0.95, 0.86)
            sl.spot_size = math.radians(72.0)
            sl.spot_blend = 0.55
            sl.shadow_soft_size = 0.22
            sl.use_shadow = True
            ob = bpy.data.objects.new(f"beam{side}", sl)
            bpy.context.collection.objects.link(ob)
            ob.parent = cobj
            ob.location = (0.78 * side, -0.62, -0.9)
            ob.rotation_euler = (math.radians(-7.0), 0.0, 0.0)

    setup_render(cfg, look)
    return road, traffic, cobj, look


def place_camera(road, cobj, cfg, t):
    mode = cfg["camera"]
    s = cfg["speed"] * t
    if mode == "chase":
        s -= 8.2
        height, look_ahead = 2.30, 34.0
    elif mode == "bumper":
        height, look_ahead = 0.62, 46.0
    else:
        height, look_ahead = 1.34, 40.0
    u = lane_u(cfg["lane"] - 1)
    u += 0.10 * math.sin(t * 0.42)
    pos = road.point(s, u, height)
    cobj.location = pos

    ahead = road.point(s + look_ahead, lane_u(cfg["lane"] - 1), height * 0.55)
    d = ahead - pos
    yaw = math.atan2(-d.x, d.y)
    pitch = math.atan2(d.z, math.hypot(d.x, d.y))
    curvature = road.heading(s + 26.0) - road.heading(s)
    roll = max(-0.055, min(0.055, -curvature * 1.45))
    cobj.rotation_mode = "XYZ"
    cobj.rotation_euler = (math.pi / 2 + pitch, roll, yaw)


# ------------------------------------------------------------------------ CLI

DEFAULTS = dict(look="day", camera="driver", width=1920, height=1080, fps=60,
                duration=20.0, seed=7, speed=31.0, traffic=1.0, lane=2,
                curve=1.0, hills=1.0, trees=1.0, samples=64, fidelity="high", mb_steps=12, shutter=0.45, round=1.0, style="soft", dof=4.0, clouds=1.0, motion_blur=True,
                outline=0.0, lens=36.0, use_atlas=True, out="/tmp/out.png",
                still=None, start=0, end=None)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    cfg = dict(DEFAULTS)
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-").replace("-", "_")
        v = argv[i + 1]
        cur = DEFAULTS.get(k)
        if isinstance(cur, bool):
            cfg[k] = v.lower() in ("1", "true", "yes", "on")
        elif isinstance(cur, int) and not isinstance(cur, bool):
            cfg[k] = int(v)
        elif isinstance(cur, float):
            cfg[k] = float(v)
        else:
            cfg[k] = v
        i += 2
    if cfg["still"] is not None:
        cfg["still"] = float(cfg["still"])
    if cfg["end"] is not None:
        cfg["end"] = int(cfg["end"])
    return cfg


def main():
    cfg = parse()
    road, traffic, cobj, look = build(cfg)
    scn = bpy.context.scene

    if cfg["still"] is not None:
        t = cfg["still"]
        traffic.update(t)
        place_camera(road, cobj, cfg, t)
        scn.render.filepath = cfg["out"]
        scn.render.image_settings.file_format = "PNG"
        bpy.ops.render.render(write_still=True)
        print("STILL OK", cfg["out"])
        return

    # animation: bake transforms to keyframes so EEVEE gets motion vectors.
    # Straight-line motion between frames, so new keys must be LINEAR -- set it
    # as the insertion default (Blender 5 moved Action.fcurves behind slots).
    try:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    except Exception:
        pass
    n_frames = int(cfg["duration"] * cfg["fps"])
    start = cfg["start"]
    end = cfg["end"] if cfg["end"] is not None else n_frames - 1
    for f in range(start, end + 2):
        t = f / cfg["fps"]
        traffic.update(t)
        place_camera(road, cobj, cfg, t)
        for c in traffic.cars:
            c["root"].keyframe_insert("location", frame=f)
            c["root"].keyframe_insert("rotation_euler", frame=f)
            for w in c["wheels"]:
                w["ob"].keyframe_insert("rotation_quaternion", frame=f)
        cobj.keyframe_insert("location", frame=f)
        cobj.keyframe_insert("rotation_euler", frame=f)

    scn.frame_start = start
    scn.frame_end = end
    scn.render.filepath = cfg["out"]
    scn.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(animation=True)
    print("ANIM OK", cfg["out"])




# ------------------------------------------------------------------- scenery

def _ring(verts, cx, cy, cz, r, segs, squash=1.0):
    base = len(verts)
    for i in range(segs):
        a = math.tau * i / segs
        verts.append(Vector((cx + math.cos(a) * r, cy + math.sin(a) * r,
                             cz * squash)))
    return base


def _blob(verts, faces, c, r, segs=8, rings=4, squash=0.85,
          jitter=0.0, rng=None):
    """Low-poly rounded canopy centred on c."""
    tops = []
    for j in range(rings + 1):
        t = j / rings
        phi = math.pi * t
        rr = r * math.sin(phi)
        zz = c.z + math.cos(phi) * r * squash
        if rr < 1e-4:
            verts.append(Vector((c.x, c.y, zz)))
            tops.append((len(verts) - 1, 1))
        else:
            b = len(verts)
            for i in range(segs):
                a = math.tau * i / segs
                k = 1.0
                if jitter and rng is not None:
                    # low-frequency lumps plus fine break-up
                    k += jitter * (0.65 * math.sin(a * 3.0 + j * 2.1)
                                   + 0.35 * rng.uniform(-1.0, 1.0))
                verts.append(Vector((c.x + math.cos(a) * rr * k,
                                     c.y + math.sin(a) * rr * k,
                                     zz + (zz - c.z) * (k - 1.0) * 0.5)))
            tops.append((b, segs))
    for j in range(rings):
        b0, n0 = tops[j]
        b1, n1 = tops[j + 1]
        if n0 == 1:
            for i in range(n1):
                faces.append((b0, b1 + i, b1 + (i + 1) % n1))
        elif n1 == 1:
            for i in range(n0):
                faces.append((b0 + i, b1, b0 + (i + 1) % n0))
        else:
            for i in range(n0):
                faces.append((b0 + i, b0 + (i + 1) % n0,
                              b1 + (i + 1) % n1, b1 + i))


def _tube(verts, faces, a, b, r, segs=6):
    ba = len(verts)
    d = (b - a)
    if d.length < 1e-6:
        return
    up = Vector((0, 0, 1))
    n1 = d.cross(up)
    if n1.length < 1e-6:
        n1 = d.cross(Vector((1, 0, 0)))
    n1.normalize()
    n2 = d.normalized().cross(n1)
    for p in (a, b):
        for i in range(segs):
            ang = math.tau * i / segs
            verts.append(p + n1 * (math.cos(ang) * r) + n2 * (math.sin(ang) * r))
    for i in range(segs):
        faces.append((ba + i, ba + (i + 1) % segs,
                      ba + segs + (i + 1) % segs, ba + segs + i))


def scenery(road, s0, s1, look, cfg, trees=True):
    """Trees and lighting masts down both verges, merged into few meshes."""
    rng = random.Random(cfg["seed"] + 91)
    edge = MEDIAN + CARRIAGE + SHOULDER

    tv, tf, cv, cf = [], [], [], []
    s = s1 if not trees else s0
    while s < s1:
        s += rng.uniform(9.0, 26.0) / max(0.05, cfg["trees"])
        for side in (1, -1):
            if rng.random() > 0.55:
                continue
            u = side * (edge + rng.uniform(5.0, 52.0))
            base = road.point(s + rng.uniform(-6, 6), u, -0.3)
            h = rng.uniform(4.2, 9.5)
            top = base + Vector((0, 0, h * 0.62))
            _tube(tv, tf, base, top, h * 0.045, 5)
            crown = rng.uniform(0.30, 0.46) * h
            _blob(cv, cf, top + Vector((0, 0, crown * 0.55)), crown,
                  segs=7, rings=4, squash=rng.uniform(0.8, 1.15))
        s += 1.0

    bark = toon_material("bark", (0.19, 0.13, 0.09), look, rough=0.85, spec=0.05,
                         rim=0.10)
    leaf = toon_material("leaf", (0.13, 0.36, 0.14), look, rough=0.80, spec=0.09,
                         rim=0.14)
    if tf:
        mesh_from("trunks", tv, tf, bark)
    if cf:
        mesh_from("canopies", cv, cf, leaf)

    # lighting masts along the outer verge
    mv, mf, lv, lf = [], [], [], []
    s = s0
    while s < s1:
        s += 48.0
        u = edge + 2.4
        foot = road.point(s, u, -0.1)
        head = foot + Vector((0, 0, 9.6))
        _tube(mv, mf, foot, head, 0.17, 6)
        inner = road.point(s, u - 3.2, -0.1) + Vector((0, 0, 9.35))
        _tube(mv, mf, head + Vector((0, 0, -0.25)), inner, 0.12, 5)
        _blob(lv, lf, inner + Vector((0, 0, -0.18)), 0.42, segs=6, rings=3,
              squash=0.35)

    steel = toon_material("mast", (0.42, 0.44, 0.47), look, rough=0.35, spec=0.34,
                          rim=0.26)
    if mf:
        mesh_from("masts", mv, mf, steel)
    if lf:
        lamp = (glow_material("lamphead", (1.0, 0.86, 0.60),
                              55.0 if STYLE == "soft" else 22.0)
                if look["headlights"] else
                toon_material("lampoff", (0.72, 0.72, 0.70), look, rough=0.3,
                              spec=0.4, rim=0.3))
        mesh_from("lampheads", lv, lf, lamp)



def furniture(road, s0, s1, look, cfg):
    """Sign gantries, guardrail posts and verge marker posts.

    Small stuff, but it is what stops a highway reading as an empty ribbon,
    and it is the first thing that shows up when the resolution goes up.
    """
    edge = MEDIAN + CARRIAGE + SHOULDER
    steel = toon_material("gantry", (0.46, 0.48, 0.51), look, rough=0.34,
                          spec=0.36, rim=0.24)
    board = toon_material("signface", (0.06, 0.28, 0.14), look, rough=0.62,
                          spec=0.14, rim=0.20)
    postm = toon_material("postm", (0.86, 0.86, 0.84), look, rough=0.66,
                          spec=0.12, rim=0.26)

    gv, gf, bv, bf = [], [], [], []
    s = s0 + 180.0
    while s < s1:
        left = road.point(s, MEDIAN - 0.4, 0.0)
        right = road.point(s, edge + 1.0, 0.0)
        top_l = left + Vector((0, 0, 7.2))
        top_r = right + Vector((0, 0, 7.2))
        _tube(gv, gf, left, top_l, 0.20, 6)
        _tube(gv, gf, right, top_r, 0.20, 6)
        _tube(gv, gf, top_l + Vector((0, 0, -0.3)), top_r + Vector((0, 0, -0.3)),
              0.14, 6)
        # sign panel hung over the carriageway
        a = road.point(s, MEDIAN + 1.4, 0.0) + Vector((0, 0, 4.6))
        b = road.point(s, MEDIAN + CARRIAGE - 1.4, 0.0) + Vector((0, 0, 4.6))
        up = Vector((0, 0, 2.1))
        base = len(bv)
        bv += [a, b, b + up, a + up]
        bf.append((base, base + 1, base + 2, base + 3))
        s += 340.0
    if gf:
        mesh_from("gantries", gv, gf, steel)
    if bf:
        mesh_from("signboards", bv, bf, board)

    # guardrail support posts, so the rail is not a floating ribbon
    pv, pf = [], []
    s = s0
    while s < s1:
        foot = road.point(s, edge + 0.5, -0.25)
        _tube(pv, pf, foot, foot + Vector((0, 0, 0.78)), 0.055, 4)
        s += 4.0
    if pf:
        mesh_from("railposts", pv, pf, steel)

    # verge marker posts down both shoulders
    mv, mf = [], []
    s = s0
    while s < s1:
        for u in (edge + 0.1, -(edge + 0.1)):
            foot = road.point(s, u, -0.05)
            _tube(mv, mf, foot, foot + Vector((0, 0, 0.95)), 0.045, 4)
        s += 50.0
    if mf:
        mesh_from("markerposts", mv, mf, postm)



def tree_prototypes(look, rng, count=6):
    """A few well-made trees, instanced many times.

    The old trees were one 7-segment blob merged into a single giant mesh --
    cheap, but the silhouette read as faceted. Instancing lets each prototype
    carry far more geometry for the same render cost.
    """
    bark = toon_material("bark", (0.21, 0.145, 0.10), look, rough=0.88,
                         spec=0.05, rim=0.10, noise=0.28, noise_scale=52.0)
    leaf = toon_material("leaf", (0.145, 0.355, 0.135), look, rough=0.80,
                         spec=0.10, rim=0.16, noise=0.34, noise_scale=26.0,
                         bump=0.75, bump_scale=95.0)

    hidden = bpy.data.collections.new("treeprotos")
    bpy.context.scene.collection.children.link(hidden)
    hidden.hide_render = True
    hidden.hide_viewport = True

    protos = []
    for i in range(count):
        v, f, trunk_faces = [], [], 0
        h = rng.uniform(5.0, 10.0)
        lean = Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 0))
        base = Vector((0, 0, 0))
        top = Vector((0, 0, h * 0.58)) + lean
        _tube(v, f, base, top, h * 0.048, 10)
        # a couple of limbs so the trunk is not a bare pole
        for _ in range(rng.randint(2, 3)):
            a = base.lerp(top, rng.uniform(0.55, 0.85))
            d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1),
                        rng.uniform(0.5, 1.1))).normalized()
            _tube(v, f, a, a + d * (h * rng.uniform(0.16, 0.26)), h * 0.022, 7)
        trunk_faces = len(f)

        # overlapping lobes give an organic outline instead of one ball
        crown = top + Vector((0, 0, h * 0.16))
        r0 = h * rng.uniform(0.30, 0.38)
        _blob(v, f, crown, r0, segs=18, rings=12,
              squash=rng.uniform(0.80, 1.05), jitter=0.13, rng=rng)
        for _ in range(rng.randint(2, 4)):
            off = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1),
                          rng.uniform(-0.45, 0.65))) * r0 * 0.85
            _blob(v, f, crown + off, r0 * rng.uniform(0.52, 0.78),
                  segs=14, rings=10, squash=rng.uniform(0.85, 1.1),
                  jitter=0.16, rng=rng)

        me = bpy.data.meshes.new(f"tree{i}")
        me.from_pydata([tuple(x) for x in v], [], f)
        me.validate()
        me.update()
        me.materials.append(bark)
        me.materials.append(leaf)
        for j, poly in enumerate(me.polygons):
            poly.material_index = 0 if j < trunk_faces else 1
            poly.use_smooth = True
        ob = bpy.data.objects.new(f"tree{i}", me)
        hidden.objects.link(ob)
        protos.append(ob)
    return protos


def plant_trees(road, s0, s1, look, cfg):
    """Scatter instanced trees down both verges."""
    if cfg["trees"] <= 0:
        return
    rng = random.Random(cfg["seed"] + 91)
    protos = tree_prototypes(look, rng)
    edge = MEDIAN + CARRIAGE + SHOULDER
    s = s0
    n = 0
    while s < s1:
        s += rng.uniform(8.0, 22.0) / max(0.05, cfg["trees"])
        for side in (1, -1):
            if rng.random() > 0.58:
                continue
            u = side * (edge + rng.uniform(6.0, 58.0))
            p = road.point(s + rng.uniform(-5, 5), u, -0.3)
            src = protos[rng.randrange(len(protos))]
            ob = bpy.data.objects.new(f"tree_{n}", src.data)
            bpy.context.collection.objects.link(ob)
            ob.location = p
            ob.rotation_euler = (0, 0, rng.uniform(0, math.tau))
            k = rng.uniform(0.75, 1.35)
            ob.scale = (k, k, k * rng.uniform(0.9, 1.15))
            n += 1
    return n


def contact_shadow_material(look):
    """Soft dark patch that sits under a vehicle so it reads as touching."""
    mat = bpy.data.materials.new("contact")
    mat.use_nodes = True
    mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = False
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
    bsdf.inputs["Roughness"].default_value = 1.0
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = (0.5, 0.5, 0.0)
    ln = nt.nodes.new("ShaderNodeVectorMath")
    ln.operation = "LENGTH"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "EASE"
    cr.elements[0].position = 0.14
    cr.elements[0].color = (1, 1, 1, 1)
    cr.elements[1].position = 0.50
    cr.elements[1].color = (0, 0, 0, 1)
    strength = nt.nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    strength.inputs[1].default_value = 0.88
    nt.links.new(coord.outputs["Generated"], sub.inputs[0])
    nt.links.new(sub.outputs["Vector"], ln.inputs[0])
    nt.links.new(ln.outputs["Value"], ramp.inputs["Factor"])
    nt.links.new(ramp.outputs["Color"], strength.inputs[0])
    nt.links.new(strength.outputs[0], bsdf.inputs["Alpha"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat



def _dome(radius, segs=64, rings=20, zmin=0.02):
    """Upper hemisphere shell, normals pointing inward at the camera."""
    verts, faces = [], []
    rows = []
    for j in range(rings + 1):
        t = j / rings
        phi = (math.pi * 0.5) * (1.0 - t)          # zenith down to horizon
        zz = math.sin(phi)
        rr = math.cos(phi)
        if zz < zmin and j != rings:
            continue
        b = len(verts)
        for i in range(segs):
            a = math.tau * i / segs
            verts.append(Vector((math.cos(a) * rr * radius,
                                 math.sin(a) * rr * radius, zz * radius)))
        rows.append((b, segs))
    for j in range(len(rows) - 1):
        b0, n0 = rows[j]
        b1, _ = rows[j + 1]
        for i in range(n0):
            faces.append((b0 + i, b1 + i, b1 + (i + 1) % n0, b0 + (i + 1) % n0))
    return verts, faces


def clouds(look, cfg, road):
    """Cumulus on a sky dome.

    Shaded rather than lit: the dome is far away and nearly edge-on at the
    horizon, so a real BSDF gives almost no gradient. The same noise that cuts
    the cloud shapes also drives a lit-top / shaded-base ramp, which reads as
    volume from the ground.
    """
    if cfg["clouds"] <= 0:
        return None
    v, f = _dome(2400.0, segs=72, rings=22, zmin=0.035)
    mat = bpy.data.materials.new("clouds")
    mat.use_nodes = True
    mat.surface_render_method = "BLENDED"
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")

    coord = nt.nodes.new("ShaderNodeTexCoord")
    scale = nt.nodes.new("ShaderNodeMapping")
    scale.inputs["Scale"].default_value = (4.5, 4.5, 3.0)
    nt.links.new(coord.outputs["Generated"], scale.inputs["Vector"])

    shape = nt.nodes.new("ShaderNodeTexNoise")
    shape.inputs["Scale"].default_value = 3.4 * cfg["clouds"]
    shape.inputs["Detail"].default_value = 12.0
    shape.inputs["Roughness"].default_value = 0.48
    nt.links.new(scale.outputs["Vector"], shape.inputs["Vector"])

    cover = nt.nodes.new("ShaderNodeValToRGB")
    cc = cover.color_ramp
    cc.interpolation = "EASE"
    cc.elements[0].position = 0.495
    cc.elements[0].color = (0, 0, 0, 1)
    cc.elements[1].position = 0.575
    cc.elements[1].color = (1, 1, 1, 1)
    nt.links.new(shape.outputs["Fac"], cover.inputs["Factor"])

    # lit crown vs shaded base, from the same field offset upward
    lit = nt.nodes.new("ShaderNodeValToRGB")
    lc = lit.color_ramp
    lc.interpolation = "EASE"
    top = look.get("cloud_top", (1.0, 0.99, 0.97))
    bot = look.get("cloud_base", (0.62, 0.66, 0.74))
    lc.elements[0].position = 0.50
    lc.elements[0].color = (*bot, 1)
    lc.elements[1].position = 0.64
    lc.elements[1].color = (*top, 1)
    nt.links.new(shape.outputs["Fac"], lit.inputs["Factor"])

    nt.links.new(lit.outputs["Color"], emit.inputs["Color"])
    emit.inputs["Strength"].default_value = look.get("cloud_strength", 1.0)
    mixsh = nt.nodes.new("ShaderNodeMixShader")
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    nt.links.new(cover.outputs["Color"], mixsh.inputs["Fac"])
    nt.links.new(transp.outputs["BSDF"], mixsh.inputs[1])
    nt.links.new(emit.outputs["Emission"], mixsh.inputs[2])
    nt.links.new(mixsh.outputs["Shader"], out.inputs["Surface"])

    ob = mesh_from("clouds", v, f, mat)
    ob.visible_shadow = False
    mid = road.point((cfg["speed"] * cfg["duration"]) * 0.5, 0.0, 0.0)
    ob.location = (mid.x, mid.y, 40.0)
    for poly in ob.data.polygons:
        poly.use_smooth = True
    return ob

if __name__ == "__main__":
    main()
