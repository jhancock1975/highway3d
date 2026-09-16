"""Assert the no-interpenetration rule for a clip's whole traffic history.

    blender -b -P test_no_overlap.py -- --look day --camera chase --duration 20

Exits non-zero if any two vehicles in the same lane ever overlap. Run this
after touching anything in Traffic; the rule is a hard invariant, not a
best-effort.
"""
import bpy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scene as SC


def main():
    cfg = SC.parse()
    cfg.update(width=64, height=36, samples=1, motion_blur=False)
    road, traffic, cobj, look = SC.build(cfg)

    agents = traffic.cars + [traffic.cam]
    groups = {}
    for a in agents:
        groups.setdefault((a["oncoming"], a["lane"]), []).append(a)

    worst, where = 1e9, None
    for f in range(traffic.frames):
        t = f / cfg["fps"]
        for key, group in groups.items():
            order = sorted(((traffic._at(a, t), a) for a in group),
                           key=lambda p: -p[0])
            for k in range(len(order) - 1):
                lead_x, lead = order[k]
                fol_x, _ = order[k + 1]
                gap = lead_x - fol_x - lead["length"]
                if gap < worst:
                    worst, where = gap, (f, key)

    ok = worst >= 0.0
    print(f"agents={len(agents)} frames={traffic.frames} "
          f"min_bumper_gap={worst:.3f}m at frame {where[0]} lane {where[1]}")
    print("PASS: no interpenetration" if ok else "FAIL: vehicles overlap")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
