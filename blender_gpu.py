"""Which GPU Cycles should render on, on whatever machine this is.

Imported inside Blender by cartoon/shot.py, cartoon/tools/look_set.py,
lectern/shot.py and lectern/render.py. Cycles names its back ends by vendor:
Metal on a Mac, OptiX or CUDA on an NVIDIA card. The first back end that
finds a device wins, so the same scripts render on the Mac and on a rented
Linux GPU instead of naming Metal and falling back to the CPU everywhere else.
"""

from __future__ import annotations

PREFERENCE = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")


def choose(found: dict) -> str | None:
    """The back end to use, given {back end: [device names]}; None for the CPU."""
    for kind in PREFERENCE:
        if found.get(kind):
            return kind
    return None


def _refresh(prefs) -> None:
    for attr in ("get_devices", "refresh_devices"):
        if hasattr(prefs, attr):
            getattr(prefs, attr)()


def enable(bpy) -> str:
    """Point Cycles at the best GPU and say which back end; "CPU" when there is none."""
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        return "CPU"
    prefs = addon.preferences
    found = {}
    for kind in PREFERENCE:
        try:
            prefs.compute_device_type = kind
        except TypeError:            # this Blender has no such back end
            continue
        _refresh(prefs)
        found[kind] = [d.name for d in prefs.devices if d.type == kind]
    kind = choose(found)
    if kind is None:
        return "CPU"
    prefs.compute_device_type = kind
    _refresh(prefs)
    for d in prefs.devices:
        d.use = (d.type == kind)
    print(f"cycles device ({kind}):", ", ".join(found[kind]), flush=True)
    return kind
