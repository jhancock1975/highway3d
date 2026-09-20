"""Stage everything the document asks for, cheaply, before rendering any of it.

Runs inside Blender:

    blender --background --factory-startup --python lectern/preflight.py -- \
        --demos light_clock_rest,twin_paths --look study

Validation in `script.py` checks that a demonstration's module exists. This
checks that it actually builds -- which is a different question, and the
expensive one to get wrong. It takes seconds and it runs before the first
frame.

The reason it exists: a hardcoded list said `gamma_curve` was fine, the
document asked for it, `lecture_check` answered "ready to render", and the job
then died thirty shots in and left the machine idle for six hours. Anything
that can fail at shot zero should fail here instead.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lectern.presenter import character  # noqa: E402
from lectern.stage import demos  # noqa: E402
from lectern.stage import set as stage  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    # Told what to check rather than reading the document: Blender ships no
    # yaml, and the orchestrator has already parsed it anyway.
    ap.add_argument("--demos", default="",
                    help="comma-separated names the document actually uses")
    ap.add_argument("--look", default="study")
    ap.add_argument("--frames", type=int, default=24)
    a = ap.parse_args(argv)

    wanted = sorted({x.strip() for x in a.demos.split(",") if x.strip()})
    problems = []

    # The presenter and the set, once: if they cannot be built there is no
    # point checking anything else.
    for what, fn in (("the set", lambda: stage.build(a.look)),
                     ("the presenter", character.build)):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        try:
            fn()
        except Exception as e:
            problems.append(f"{what} failed to build: {e}")
            traceback.print_exc()

    for name in wanted:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        try:
            staged = demos.build(name, n_frames=a.frames, fps=24)
            if not staged.get("objects"):
                problems.append(f"'{name}' built nothing")
        except Exception as e:
            problems.append(f"'{name}' failed to stage: "
                            f"{type(e).__name__}: {e}")

    print("PREFLIGHT " + json.dumps(dict(
        demos=len(wanted), problems=problems)), flush=True)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
