"""The presenter, built from code rather than downloaded.

Runs inside Blender. Nothing here is an asset: the head, the hair, the
moustache and the cardigan are all generated, so a second presenter is a
different set of numbers rather than a different file to find a licence for.

The proportions are a caricature on purpose -- a big head on a small body,
the way a cartoon figure is drawn -- and the likeness is carried by the three
things everybody actually recognises (the hair, the moustache, the eyes)
rather than by any attempt at a real face. A photoreal synthetic person
saying words they never said is a different thing, and this deliberately is
not that.

Hair is geometry, not particles. Real hair on 34,000 frames costs days; six
displaced lumps hold the silhouette, which is what the recognition lives in.
"""

from __future__ import annotations

import bpy
from mathutils import Matrix, Vector

# Caricature proportions, in metres. A real head is about 1/7.5 of a standing
# figure; this is nearer 1/4, which is what reads as "drawn" not "scanned".
HEAD_R = 0.145
BODY_H = 0.62
SHOULDER_W = 0.30

# The skull's front surface, which everything on the face has to clear.
FACE_Y = -HEAD_R * 0.94

SKIN = (0.74, 0.52, 0.40, 1.0)
HAIR = (0.88, 0.88, 0.90, 1.0)
CARDIGAN = (0.085, 0.100, 0.150, 1.0)
SHIRT = (0.72, 0.73, 0.76, 1.0)
EYE_WHITE = (0.90, 0.90, 0.91, 1.0)
IRIS = (0.15, 0.10, 0.07, 1.0)
MOUTH = (0.115, 0.048, 0.052, 1.0)
BROW = (0.82, 0.82, 0.85, 1.0)
CARDIGAN_EDGE = (0.055, 0.068, 0.108, 1.0)
BUTTON = (0.28, 0.24, 0.20, 1.0)
TIE = (0.32, 0.11, 0.13, 1.0)
TROUSERS = (0.20, 0.19, 0.22, 1.0)
SHOE = (0.070, 0.062, 0.058, 1.0)


# ------------------------------------------------------------------ helpers

def _mat(name, rgba, rough=0.6, sheen=0.0):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgba
    b.inputs["Roughness"].default_value = rough
    if "Sheen Weight" in b.inputs:
        b.inputs["Sheen Weight"].default_value = sheen
    return m


def _shade(obj, material):
    obj.data.materials.append(material)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def _sphere(name, r, loc, scale=(1, 1, 1), segments=48, rings=26):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc,
                                         segments=segments, ring_count=rings)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    return o


def _subsurf(obj, levels=2, render=3):
    m = obj.modifiers.new("subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = render
    return m


def _frizz(obj, name, strength, scale, seed=0.0):
    """Lumpy displacement -- the difference between hair and a helmet."""
    tex = bpy.data.textures.new(name, "CLOUDS")
    tex.noise_scale = scale
    tex.noise_depth = 4
    m = obj.modifiers.new(name, "DISPLACE")
    m.texture = tex
    m.strength = strength
    m.mid_level = 0.40
    obj.data.use_auto_texspace = False
    obj.data.texspace_location = Vector((seed, seed * 0.7, seed * 1.3))
    return m


def _join(parts, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts[1:]:
        o.select_set(True)
    parts[0].select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = name
    return o


# --------------------------------------------------------------------- head

def build_head():
    """Skull, jaw, nose, ears -- welded into one surface."""
    skull = _sphere("head", HEAD_R, (0, 0, 0), scale=(1.0, 0.94, 1.08))
    jaw = _sphere("jaw", HEAD_R * 0.76, (0, -0.014, -HEAD_R * 0.50),
                  scale=(0.92, 0.94, 0.70))
    nose = _sphere("nose", HEAD_R * 0.34, (0, FACE_Y * 0.90, -HEAD_R * 0.06),
                   scale=(0.66, 1.30, 0.80))
    ear_l = _sphere("ear.L", HEAD_R * 0.28, (HEAD_R * 0.94, 0.01, -HEAD_R * 0.04),
                    scale=(0.34, 0.76, 1.0))
    ear_r = _sphere("ear.R", HEAD_R * 0.28, (-HEAD_R * 0.94, 0.01, -HEAD_R * 0.04),
                    scale=(0.34, 0.76, 1.0))

    head = _join([skull, jaw, nose, ear_l, ear_r], "einstein_head")
    rm = head.modifiers.new("weld", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = 0.0038
    rm.use_smooth_shade = True
    _subsurf(head, 1, 2)
    return _shade(head, _mat("skin", SKIN, rough=0.58, sheen=0.20))


def build_mouth():
    """A cavity, because a mouth that is only a line cannot open.

    Scaled by the viseme track at render time: this is the object the phoneme
    timeline actually drives.
    """
    # Pressed flat against the face, not floating in front of it. A cavity
    # with real depth needs a hole cut in the skull to look through; a drawn
    # mouth on the surface is what a cartoon face wants anyway, and it cannot
    # poke through the chin from any angle.
    # Seated ON the jaw surface, which at this height sits at about
    # FACE_Y * 0.82 -- far enough forward to be seen, not so far that it
    # reads as a tongue hanging past the chin.
    m = _sphere("mouth", HEAD_R * 0.26, (0, FACE_Y * 0.82, -HEAD_R * 0.46),
                scale=(1.52, 0.17, 0.40), segments=32, rings=18)
    return _shade(m, _mat("mouth", MOUTH, rough=0.45))


def build_eyes():
    """Proud of the skull, the way a drawn eye is. Buried eyes read as closed."""
    white = _mat("eye_white", EYE_WHITE, rough=0.18)
    iris = _mat("iris", IRIS, rough=0.22)
    out = []
    for side, x in (("L", 1), ("R", -1)):
        cy = FACE_Y * 0.80
        e = _sphere(f"eye.{side}", HEAD_R * 0.255,
                    (x * HEAD_R * 0.375, cy, HEAD_R * 0.09),
                    segments=32, rings=20)
        _shade(e, white)
        p = _sphere(f"iris.{side}", HEAD_R * 0.125,
                    (x * HEAD_R * 0.375, cy - HEAD_R * 0.205, HEAD_R * 0.09),
                    scale=(1.0, 0.42, 1.0), segments=28, rings=16)
        _shade(p, iris)
        out += [e, p]
    return out


def build_brows():
    """Heavy and white. Half the expression lives here."""
    mat = _mat("brow", BROW, rough=0.88)
    out = []
    for side, x in (("L", 1), ("R", -1)):
        b = _sphere(f"brow.{side}", HEAD_R * 0.235,
                    (x * HEAD_R * 0.385, FACE_Y * 0.80, HEAD_R * 0.305),
                    scale=(1.40, 0.44, 0.30), segments=28, rings=16)
        _subsurf(b, 1, 2)
        _frizz(b, f"brow.{side}.frizz", 0.006, 0.09, 29.0 + x * 3)
        _shade(b, mat)
        out.append(b)
    return out


def build_hair(seed: int = 5, count: int = 300):
    """The hair, which is most of the recognition.

    Two parts, because either alone is wrong. A displaced sphere reads as
    cotton wool -- the silhouette stays convex however much noise you put on
    it. Bare radiating spikes read as a sea urchin. Real Einstein hair is a
    *mass* with a broken edge: volume at the sides and back, and shorter
    clumps standing out of it to spoil the outline.

    The forehead stays bare throughout. The high brow is as much of the
    caricature as the frizz is.
    """
    import math
    import random

    rng = random.Random(seed)
    mat = _mat("hair", HAIR, rough=0.92, sheen=0.55)
    pieces = []

    # ---- the mass: lumps that overlap into one continuous volume
    masses = [
        ("mass.crown", HEAD_R * 0.80, (0.0, HEAD_R * 0.42, HEAD_R * 0.54),
         (1.30, 1.10, 0.60), 0.034, 0.0),
        ("mass.L", HEAD_R * 0.74, (HEAD_R * 0.94, HEAD_R * 0.32, HEAD_R * 0.20),
         (1.00, 0.92, 1.26), 0.038, 3.1),
        ("mass.R", HEAD_R * 0.74, (-HEAD_R * 0.94, HEAD_R * 0.32, HEAD_R * 0.20),
         (1.00, 0.92, 1.26), 0.038, 7.4),
        ("mass.back", HEAD_R * 0.88, (0.0, HEAD_R * 0.66, HEAD_R * 0.06),
         (1.14, 0.94, 1.10), 0.036, 11.2),
        ("mass.nape", HEAD_R * 0.50, (0.0, HEAD_R * 0.70, -HEAD_R * 0.44),
         (1.30, 0.86, 0.68), 0.026, 15.8),
    ]
    for name, r, loc, scale, strength, sd in masses:
        o = _sphere(name, r, loc, scale=scale, segments=36, rings=20)
        _frizz(o, f"{name}.frizz", strength, 0.19, sd)
        pieces.append(o)

    # ---- the broken edge: short clumps standing out of the mass
    for i in range(count):
        u = rng.uniform(-1.0, 1.0)
        phi = rng.uniform(0.0, 2.0 * math.pi)
        s_ = math.sqrt(max(0.0, 1.0 - u * u))
        d = Vector((s_ * math.cos(phi), s_ * math.sin(phi), u))

        if d.z < -0.40:                      # no hair on the jaw
            continue
        if d.y < -0.26 and d.z > 0.02:       # the forehead stays bare
            continue
        if d.y < -0.52:                      # nor the face
            continue

        splay = 1.0 + 0.55 * (1.0 - abs(d.z))
        length = HEAD_R * rng.uniform(0.16, 0.40) * splay
        base_r = HEAD_R * rng.uniform(0.055, 0.095)

        jitter = Vector((rng.gauss(0, 0.30), rng.gauss(0, 0.30), rng.gauss(0, 0.26)))
        out = d + jitter * 0.6
        out.normalize()
        out.z += 0.16
        out.normalize()

        # seat on the outside of the mass, not on the skull
        seat = HEAD_R * (1.08 + 0.34 * (1.0 - abs(d.z)))
        loc = Vector((d.x * seat, d.y * seat * 0.94, d.z * seat)) \
            + out * (length * 0.34)

        bpy.ops.mesh.primitive_cone_add(
            vertices=6, radius1=base_r, radius2=base_r * 0.20, depth=length,
            location=loc)
        c = bpy.context.object
        c.name = f"wisp.{i:03d}"
        c.rotation_euler = out.to_track_quat("Z", "Y").to_euler()
        pieces.append(c)

    hair = _join(pieces, "einstein_hair")
    _subsurf(hair, 1, 2)
    _frizz(hair, "hair.frizz", 0.007, 0.11, 41.0)
    return _shade(hair, mat)


def build_moustache():
    """Walrus, drooping past the corners of the mouth."""
    mat = _mat("hair", HAIR, rough=0.90, sheen=0.5)
    o = _sphere("moustache", HEAD_R * 0.30,
                (0.0, FACE_Y * 0.88, -HEAD_R * 0.30),
                scale=(1.95, 0.62, 0.48), segments=44, rings=22)
    _subsurf(o, 2, 3)
    _frizz(o, "moustache.frizz", 0.013, 0.11, 37.0)
    return _shade(o, mat)


# --------------------------------------------------------------------- body

# The arm chain, in metres. Measured down from the shoulder joint, so the
# hand lands beside the hip rather than wherever the numbers happened to put
# it.
UPPER_ARM = 0.200
FOREARM = 0.180
HAND_L = 0.090
HIP_Z = -HEAD_R - BODY_H * 0.76
FLOOR_Z = -0.98
THIGH = 0.180
SHIN = 0.140


def _limb(name, top_r, bot_r, length, segments=20, rings=12):
    """A tapered capsule whose origin is at its top -- that is, at the joint.

    Origin at the joint and not at the centre of the mesh is the whole point.
    A limb rotates about the end it hangs from; a mesh centred on itself
    swings its own shoulder through the torso the first time it is keyframed,
    and the fix looks like a rigging problem when it is really an origin one.
    """
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=segments,
                                         ring_count=rings, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    # The capsule runs past the joint at both ends. A segment that stops dead
    # on its own origin leaves a gap you can see straight through at every
    # shoulder, elbow and knee -- which is what makes a figure read as a doll
    # assembled from parts rather than as a body. The overlap costs nothing
    # and the joint closes.
    over_t = top_r * 0.90
    over_b = bot_r * 0.55
    span = length + over_t + over_b
    for v in o.data.vertices:
        t = (1.0 - v.co.z) * 0.5          # 0 at the top, 1 at the bottom
        r = top_r + (bot_r - top_r) * t
        v.co.x *= r
        v.co.y *= r
        v.co.z = over_t - (1.0 - v.co.z) * 0.5 * span
    return o


def _empty(name, location, parent=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.03
    bpy.context.scene.collection.objects.link(e)
    if parent is not None:
        e.parent = parent
        e.matrix_parent_inverse = Matrix.Identity(4)
    e.location = location
    return e


def build_body():
    """A cardigan, two arms that can move, and legs that reach the floor.

    What was here before was one voxel-remeshed lump: torso, neck and two arm
    stubs joined into a single mesh and then baked, so from the neck down the
    figure was one rigid object with nothing to keyframe. It also stopped at
    z=-0.69 above a floor at -0.98 -- a bust on an invisible plinth, which
    worked only because every framing cropped him at the chest.

    So the arms are separate objects on a joint chain, and he has legs. The
    joints are empties rather than an armature: there is no skinning here,
    the parts are rigid, and an empty per joint is a transform the animation
    code can keyframe directly without a rig to maintain.
    """
    body_root = _empty("body_root", (0, 0, 0))

    chest = _sphere("chest", BODY_H * 0.30, (0, 0, -HEAD_R - BODY_H * 0.34),
                    scale=(1.12, 0.74, 0.92))
    waist = _sphere("waist", BODY_H * 0.255, (0, 0.004, -HEAD_R - BODY_H * 0.62),
                    scale=(1.04, 0.76, 0.86))
    caps = []
    for side, x in (("L", 1), ("R", -1)):
        caps.append(_sphere(f"deltoid.{side}", BODY_H * 0.125,
                            (x * SHOULDER_W * 0.62, -0.004,
                             -HEAD_R - BODY_H * 0.26),
                            scale=(1.0, 0.94, 0.86)))
    hips = _sphere("hips", BODY_H * 0.215, (0, 0.004, HIP_Z + BODY_H * 0.10),
                   scale=(1.06, 0.82, 0.70))

    torso = _join([chest, waist, hips] + caps, "einstein_body")
    rm = torso.modifiers.new("weld", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = 0.009
    rm.use_smooth_shade = True
    _subsurf(torso, 1, 2)
    _shade(torso, _mat("cardigan", CARDIGAN, rough=0.94, sheen=0.6))

    buttons = []
    for i, z in enumerate((-0.285, -0.375, -0.465)):
        b = _sphere(f"button.{i}", 0.0115, (0, -0.131, z),
                    scale=(1.0, 0.42, 1.0), segments=16, rings=10)
        _shade(b, _mat("button", BUTTON, rough=0.42))
        buttons.append(b)

    collar = _sphere("collar", HEAD_R * 0.50, (0, -0.025, -HEAD_R * 1.12),
                     scale=(1.30, 1.05, 0.50))
    _shade(collar, _mat("shirt", SHIRT, rough=0.74))

    neck = _sphere("neck", HEAD_R * 0.34, (0, 0.006, -HEAD_R * 1.02),
                   scale=(1.0, 1.0, 0.95))
    _shade(neck, _mat("skin", SKIN, rough=0.56))

    sleeve = _mat("cardigan", CARDIGAN, rough=0.94, sheen=0.6)
    skin = _mat("skin", SKIN, rough=0.56)

    arms = {}
    for side, x in (("L", 1), ("R", -1)):
        # Measured, not guessed: the torso reaches x = +-0.263 at the
        # chest, so a joint at 0.64 * SHOULDER_W = 0.192 put the whole upper
        # arm inside the cardigan.
        shoulder = _empty(f"shoulder.{side}",
                          (x * 0.238, -0.010,
                           -HEAD_R - BODY_H * 0.27), parent=body_root)
        shoulder.rotation_euler = (0.06, x * 0.13, 0)
        upper = _limb(f"upperarm.{side}", 0.056, 0.046, UPPER_ARM)
        _shade(upper, sleeve)
        elbow = _empty(f"elbow.{side}", (0, 0, -UPPER_ARM))
        fore = _limb(f"forearm.{side}", 0.046, 0.038, FOREARM)
        _shade(fore, sleeve)
        wrist = _empty(f"wrist.{side}", (0, 0, -FOREARM))
        hand = _limb(f"hand.{side}", 0.040, 0.030, HAND_L, segments=18, rings=10)
        hand.scale = (1.0, 0.62, 1.0)
        _shade(hand, skin)
        thumb = _limb(f"thumb.{side}", 0.017, 0.013, 0.040, segments=12, rings=8)
        thumb.location = (x * 0.030, -0.004, -0.028)
        thumb.rotation_euler = (0, x * 1.15, 0)
        _shade(thumb, skin)
        for o in (upper, fore, hand, thumb):
            _subsurf(o, 1, 2)
        arms[side] = dict(shoulder=shoulder, upper=upper, elbow=elbow,
                          fore=fore, wrist=wrist, hand=hand, thumb=thumb,
                          sign=x)

    legs = {}
    for side, x in (("L", 1), ("R", -1)):
        hip = _empty(f"hip.{side}", (x * 0.085, 0.0, HIP_Z), parent=body_root)
        thigh = _limb(f"thigh.{side}", 0.062, 0.050, THIGH)
        knee = _empty(f"knee.{side}", (0, 0, -THIGH))
        shin = _limb(f"shin.{side}", 0.048, 0.040, SHIN)
        trouser = _mat("trousers", TROUSERS, rough=0.90)
        _shade(thigh, trouser)
        _shade(shin, trouser)
        ankle = _empty(f"ankle.{side}", (0, 0, -SHIN))
        shoe = _sphere(f"shoe.{side}", 0.052, (0, -0.030, -0.016),
                       scale=(0.80, 1.55, 0.44))
        _shade(shoe, _mat("shoe", SHOE, rough=0.35))
        for o in (thigh, shin, shoe):
            _subsurf(o, 1, 2)
        legs[side] = dict(hip=hip, thigh=thigh, knee=knee, shin=shin,
                          ankle=ankle, shoe=shoe, sign=x)

    meshes = ([torso, collar, neck] + buttons
              + [p for a in arms.values()
                 for p in (a["upper"], a["fore"], a["hand"], a["thumb"])]
              + [p for l in legs.values()
                 for p in (l["thigh"], l["shin"], l["shoe"])])
    return dict(root=body_root, torso=torso, collar=collar, neck=neck,
                arms=arms, legs=legs, meshes=meshes)


def _chain(pairs) -> None:
    """Parent each child to its joint, keeping the local offset as written.

    Identity parent-inverse on purpose: every location in the chain is
    already expressed relative to the joint above it, so Blender must not
    compensate for where the object happened to be in world space.
    """
    for child, parent in pairs:
        loc = tuple(child.location)
        child.parent = parent
        child.matrix_parent_inverse = Matrix.Identity(4)
        child.location = loc


def dress_torso(torso) -> None:
    """Cardigan opening, shirt and tie, painted onto the torso's own faces.

    They were three separate slabs floating in front of the chest, and no
    amount of nudging fixes that: the torso is a voxel remesh, its front
    surface is a curve nobody wrote down, and a straight ellipsoid laid on it
    stands 14 mm proud at the sternum and pokes out through the waist below.
    Measured, that is exactly what it did -- the V-neck read as a bib and the
    two cardigan edges hung below the hem like tusks.

    Painting the faces cannot come unstuck from the surface, because it is
    the surface. It has to run after `bake`, since the remesh and the subsurf
    both replace every face this selects.
    """
    me = torso.data
    names = [m.name for m in me.materials]
    for mat in (_mat("shirt", SHIRT, rough=0.74),
                _mat("tie", TIE, rough=0.52),
                _mat("cardigan_edge", CARDIGAN_EDGE, rough=0.90, sheen=0.7)):
        if mat.name not in names:
            me.materials.append(mat)
            names.append(mat.name)
    shirt_i, tie_i, edge_i = (names.index("shirt"), names.index("tie"),
                              names.index("cardigan_edge"))

    # World space, not local. `poly.center` is in the mesh's own frame, and
    # the torso's origin is wherever `_join` left it -- at the chest sphere,
    # 0.356 m above the figure's origin. Thresholds written as if they were
    # world z were therefore all shifted by that much, which painted the
    # shirt from the collar to the navel instead of a collar opening. It is
    # silent: every face gets a material either way.
    mw = torso.matrix_world
    nm = mw.to_3x3()
    for poly in me.polygons:
        c = mw @ poly.center
        if c.y > -0.05 or (nm @ poly.normal).y > -0.25:
            continue                      # not on the front
        # A V-neck is wide at the collar and closes to a point below it. The
        # first version had the inequality the other way round, so it was
        # widest at the apex and had shrunk to nothing by the time it reached
        # the collar -- 382 faces out of 45,432, which is why it read as a
        # stray patch on the chest rather than as a shirt.
        if c.z > -0.30 and abs(c.x) < min(0.090, 0.090 * (c.z + 0.30) / 0.115):
            poly.material_index = shirt_i
        elif -0.50 < c.z <= -0.30 and abs(c.x) < 0.026:
            poly.material_index = tie_i
        elif abs(c.x) < 0.048 and c.z > -0.60:
            poly.material_index = edge_i           # the cardigan opening


def bake(objects) -> None:
    """Apply every modifier once, so no frame pays for them again.

    Remesh, subdivision and displacement are expensive and they are also
    constant: the character is animated by moving transforms, not by changing
    geometry. Left live, Blender re-evaluates the whole stack per frame --
    measured at 8.8 seconds a frame, which over a 24-minute lecture is six
    days. Baked, the same scene renders static geometry.
    """
    bpy.ops.object.select_all(action="DESELECT")
    live = [o for o in objects if o.type == "MESH" and o.modifiers]
    if not live:
        return
    for o in live:
        o.select_set(True)
    bpy.context.view_layer.objects.active = live[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.select_all(action="DESELECT")


def build(name: str = "einstein") -> dict:
    """Every piece of the presenter, in one collection.

    The face is parented to an empty so the head can turn, nod and settle as
    one thing. Without it every tilt would have to move nine objects in step,
    and they would drift apart the first time one of them was keyframed alone.
    """
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)

    body = build_body()
    parts = {
        "head": build_head(),
        "mouth": build_mouth(),
        "eyes": build_eyes(),
        "brows": build_brows(),
        "hair": build_hair(),
        "moustache": build_moustache(),
        "body": body["meshes"],
    }

    flat = []
    for v in parts.values():
        flat += v if isinstance(v, list) else [v]
    joints = [body["root"]]
    for limb in list(body["arms"].values()) + list(body["legs"].values()):
        joints += [v for k, v in limb.items()
                   if k in ("shoulder", "elbow", "wrist", "hip", "knee",
                            "ankle")]
    for o in flat + joints:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    # Bake before parenting. Converting an object applies its modifiers in
    # world space, and doing it after the chain is built bakes the parent's
    # rotation into the child's mesh.
    bake(flat)
    dress_torso(body["torso"])

    root = bpy.data.objects.new("head_root", None)
    root.empty_display_size = 0.05
    coll.objects.link(root)
    ON_BODY = ("einstein_body", "collar", "vee", "tie", "placket", "button",
               "upperarm", "forearm", "hand", "thumb", "thigh", "shin",
               "shoe")
    for o in flat:
        if o.name.startswith(ON_BODY):
            continue
        o.parent = root
        o.matrix_parent_inverse = root.matrix_world.inverted()

    # The arm hangs off the shoulder, the forearm off the elbow, the hand off
    # the wrist. Rotating the shoulder therefore carries the whole arm, which
    # is what lets a gesture be three keyframes instead of nine.
    for limb in body["arms"].values():
        _chain([(limb["upper"], limb["shoulder"]),
                (limb["elbow"], limb["upper"]),
                (limb["fore"], limb["elbow"]),
                (limb["wrist"], limb["fore"]),
                (limb["hand"], limb["wrist"]),
                (limb["thumb"], limb["hand"])])
    for limb in body["legs"].values():
        _chain([(limb["thigh"], limb["hip"]),
                (limb["knee"], limb["thigh"]),
                (limb["shin"], limb["knee"]),
                (limb["ankle"], limb["shin"]),
                (limb["shoe"], limb["ankle"])])

    # The head rides on the body, not beside it: when he shifts his weight
    # the head goes with him, and his own sway adds on top of that rather
    # than fighting it.
    body_meshes = [o for o in flat if o.name.startswith(ON_BODY)]
    for o in body_meshes:
        if o.parent is None:
            o.parent = body["root"]
            o.matrix_parent_inverse = body["root"].matrix_world.inverted()
    root.parent = body["root"]
    root.matrix_parent_inverse = Matrix.Identity(4)

    # One handle for the whole figure, so a demonstration can be staged
    # beside him by moving him rather than by rebuilding him somewhere else.
    stand = bpy.data.objects.new("presenter_root", None)
    stand.empty_display_size = 0.08
    coll.objects.link(stand)
    body["root"].parent = stand
    body["root"].matrix_parent_inverse = Matrix.Identity(4)

    parts["root"] = root
    parts["stand"] = stand
    parts["body_root"] = body["root"]
    parts["torso"] = body["torso"]
    parts["arms"] = body["arms"]
    parts["legs"] = body["legs"]
    parts["collection"] = coll
    parts["all"] = flat
    return parts
