"""The professor as a real human figure: MPFB body, sculpted visemes, curves hair.

    python3 lectern/presenter/human.py                 # builds professor.blend
    python3 lectern/presenter/human.py --out x.blend

Run setup_human.sh once first; it installs MPFB and the MakeHuman asset packs
into lectern/.blender, which this points Blender at. Run as a plain python
script it re-launches itself inside Blender with that environment.

What gets built, and why each piece is what it is:

- The body is MakeHuman's base mesh through MPFB: male, about seventy, slim,
  with the modelling targets pushed toward a caricature -- a larger head and
  eyes, a heavier nose, baggy lids -- while staying a human being.
- The mouth is the fifteen visemes02 shape keys (Meta/Oculus set, sculpted on
  this mesh) plus the 52 ARKit face units, interpolated onto the teeth,
  tongue, brows and lashes so they travel with the lips and jaw. Every copy
  on a child mesh is driven from the body's key, so animation keys the body
  alone. visemes.face() produces the values.
- Hair, brows and the walrus moustache are real curves strands grown from the
  skin and bound to it with Deform Curves on Surface: they ride the armature
  and the shape keys, so the moustache moves with the upper lip.
- Modelling targets are baked into the basis before the hair is grown, so the
  rest surface the hair is bound to is the finished face.
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LECTERN = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(HERE, "professor.blend")
USER_RESOURCES = os.path.join(LECTERN, ".blender")

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False


def _relaunch():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--blender", default=os.environ.get("BLENDER", "blender"))
    a = ap.parse_args()
    env = dict(os.environ, BLENDER_USER_RESOURCES=USER_RESOURCES)
    if not os.path.isdir(os.path.join(USER_RESOURCES, "extensions", "user_default", "mpfb")):
        sys.exit("MPFB is not installed: run lectern/presenter/setup_human.sh")
    cmd = [a.blender, "--background", "--python", os.path.abspath(__file__), "--", "--out", a.out]
    sys.exit(subprocess.call(cmd, env=env))


if not IN_BLENDER:
    if __name__ == "__main__":
        _relaunch()
    raise SystemExit

# ---------------------------------------------------------------- in Blender

import importlib  # noqa: E402

import bpy  # noqa: E402,F811
from mathutils import Vector  # noqa: E402

svc = importlib.import_module("bl_ext.user_default.mpfb.services")
HumanService = svc.HumanService
FaceService = svc.FaceService
faceservice_mod = importlib.import_module("bl_ext.user_default.mpfb.services.faceservice")
FACE_KEYS = set(faceservice_mod.META_VISEMES) | set(faceservice_mod.ARKIT_FACEUNITS) \
    | set(faceservice_mod.MICROSOFT_VISEMES)

NAME = "Professor"

# MakeHuman macros: age 0.5 is 25 years and 1.0 is 90, so 0.85 is about 70.
PHENOTYPE = {
    "gender": 1.0, "age": 0.85, "muscle": 0.25, "weight": 0.28,
    "proportions": 0.55, "height": 0.42, "cupsize": 0.5, "firmness": 0.5,
    "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0},
}

# Toward the caricature, not past it: a real skull with a cartoonist's
# emphasis. Values are MakeHuman target weights.
STYLE_TARGETS = {
    "head-scale-vert-incr": 0.35,
    "head-scale-horiz-incr": 0.30,
    "head-scale-depth-incr": 0.22,
    "head-round": 0.35,
    "l-eye-scale-incr": 0.55, "r-eye-scale-incr": 0.55,
    "l-eye-bag-incr": 0.6, "r-eye-bag-incr": 0.6,
    "l-eye-height2-incr": 0.2, "r-eye-height2-incr": 0.2,
    "nose-volume-incr": 0.35,
    "nose-point-width-incr": 0.35,
    "nose-scale-vert-incr": 0.15,
    "nose-flaring-incr": 0.25,
    "eyebrows-angle-down": 0.35,
    "mouth-scale-horiz-incr": 0.12,
    "mouth-upperlip-volume-incr": 0.2,
    "mouth-lowerlip-volume-incr": 0.25,
    "neck-scale-horiz-decr": 0.15,
}

CLOTHES = [
    "elvs_male_shirt_tie_tucked1.mhclo",          # CC-BY Elvaerwyn
    "mindfront_cardigan_long_open_front.mhclo",   # CC-BY Mindfront
    "toigo_wool_pants.mhclo",                     # CC0 Margaret Toigo
    "mindfront_shoes_oxford_male.mhclo",          # CC-BY Mindfront
]

# warmer, softer skin than MPFB's photographic default
SKIN = {
    "Roughness": 0.52,
    "Clearcoat": 0.06,
    "Clearcoat Roughness": 0.4,
    "Pore strength": 0.08,
    "colorMixIn": [1.0, 0.45, 0.32, 1.0],
    "colorMixInStrength": 0.12,
}


def log(*a):
    print("[human]", *a, flush=True)


# ------------------------------------------------------------------- body

def build_body():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    info = HumanService._create_default_human_info_dict()
    info["phenotype"] = PHENOTYPE
    info["targets"] = [{"target": k, "value": v} for k, v in STYLE_TARGETS.items()]
    info.update({
        "name": NAME,
        "rig": "default",
        "eyes": "high-poly.mhclo",
        "eyebrows": "eyebrow001.mhclo",
        "eyelashes": "eyelashes01.mhclo",
        "teeth": "teeth_base.mhclo",
        "tongue": "tongue01.mhclo",
        "hair": "",
        "clothes": list(CLOTHES),
        "skin_mhmat": "old_caucasian_male.mhmat",
        "skin_material_type": "ENHANCED_SSS",
        "eyes_material_type": "PROCEDURAL_EYES",
        "skin_material_settings": {k: dict(SKIN) for k in ("body", "ears")},
    })
    settings = HumanService.get_default_deserialization_settings()
    settings["subdiv_levels"] = 1
    body = HumanService.deserialize_from_dict(info, settings)
    FaceService.load_targets(body, load_microsoft_visemes=False,
                             load_meta_visemes=True, load_arkit_faceunits=True)
    FaceService.interpolate_targets(body)
    return body


def children(body):
    root = body.parent or body
    return [o for o in bpy.data.objects if o.type == "MESH" and o is not body
            and (o.parent is root or o.parent is body)]


def bake_modelling_targets(body):
    """Fold every macro and modelling shape key into the basis.

    Face keys stay, re-expressed relative to the new basis. After this the
    mesh at rest *is* the finished face, which is what the hair binds to.
    """
    keys = body.data.shape_keys.key_blocks
    basis = keys[0]
    n = len(body.data.vertices)
    delta = [Vector((0, 0, 0)) for _ in range(n)]
    model = [k for k in keys[1:] if k.name not in FACE_KEYS]
    for k in model:
        if k.value == 0.0:
            continue
        rel = k.relative_key
        for i in range(n):
            delta[i] += (k.data[i].co - rel.data[i].co) * k.value
    for k in keys:
        if k.name in FACE_KEYS or k is basis:
            for i in range(n):
                k.data[i].co += delta[i]
    for i, v in enumerate(body.data.vertices):
        v.co = basis.data[i].co
    for k in model:
        body.shape_key_remove(k)
    log("baked", len(model), "modelling keys;", len(body.data.shape_keys.key_blocks) - 1, "face keys remain")


def drive_children(body):
    """Child meshes' copies of face keys follow the body's."""
    n = 0
    for ob in children(body):
        sk = ob.data.shape_keys
        if not sk:
            continue
        for kb in sk.key_blocks[1:]:
            if kb.name not in body.data.shape_keys.key_blocks:
                continue
            kb.driver_remove("value")
            fc = kb.driver_add("value")
            d = fc.driver
            d.type = "AVERAGE"
            var = d.variables.new()
            var.type = "SINGLE_PROP"
            var.targets[0].id_type = "KEY"
            var.targets[0].id = body.data.shape_keys
            var.targets[0].data_path = f'key_blocks["{kb.name}"].value'
            n += 1
    log("drivers", n)


def fix_eyes(body):
    """MPFB's procedural eye renders blank in EEVEE.

    The eyeball is two shells in one material: an outer cornea with full
    transmission over an inner iris/sclera. EEVEE without raytraced
    refraction sees only the world probe through the transmission, so the
    whole eye reads as background. Make the cornea shell transparent by
    alpha instead (only where the shader's own IsInRange says it is the outer
    layer), keep a little of it for the wet highlight, and colour the iris
    brown.
    """
    eyes = [o for o in children(body) if "high-poly" in o.name]
    for ob in eyes:
        mat = ob.active_material
        gn = next(n for n in mat.node_tree.nodes if n.type == "GROUP")
        g = gn.node_tree.copy()
        gn.node_tree = g
        coord = g.nodes["EyeCoordinateInfo"]
        p = g.nodes["Principled BSDF"]
        gi = g.nodes["Group Input"]
        for link in list(p.inputs["Alpha"].links):
            g.links.remove(link)
        mx = g.nodes.new("ShaderNodeMath")
        mx.operation = "MAXIMUM"
        g.links.new(coord.outputs["IsInRange"], mx.inputs[0])
        g.links.new(gi.outputs["OuterLayerAlpha"], mx.inputs[1])
        g.links.new(mx.outputs[0], p.inputs["Alpha"])
        gn.inputs["OuterLayerTransmission"].default_value = 0.0
        gn.inputs["OuterLayerAlpha"].default_value = 0.12
        gn.inputs["IrisMajorColor"].default_value = (0.20, 0.09, 0.035, 1)
        gn.inputs["IrisMinorColor"].default_value = (0.07, 0.03, 0.012, 1)
        gn.inputs["IrisSection4Color"].default_value = (0.03, 0.018, 0.01, 1)
        gn.inputs["EyeWhiteColor"].default_value = (0.92, 0.88, 0.84, 1)
        gn.inputs["PupilSize"].default_value = 0.34
        gn.inputs["IrisToEyeWhiteRelation"].default_value = 0.43
        mat.surface_render_method = "BLENDED"
    log("eyes fixed", [o.name for o in eyes])


# ------------------------------------------------------------------ main

def main():
    import argparse
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-hair", action="store_true")
    a = ap.parse_args(argv)

    body = build_body()
    bake_modelling_targets(body)
    fix_eyes(body)
    drive_children(body)
    if not a.no_hair:
        import importlib.util
        spec = importlib.util.spec_from_file_location("lectern_hair", os.path.join(HERE, "hair.py"))
        hair = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hair)
        hair.grow_all(body, children(body))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    log("saved", a.out)


main()
