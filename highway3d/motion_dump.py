"""Dump the traffic simulation to JSON so audio can be synthesised from it.

    blender -b -P motion_dump.py -- --look day --camera chase --duration 8 \
        --motion-out /tmp/motion.json

The renderer already knows, for every frame, where the camera is and where
every vehicle is relative to it. That is exactly what a soundtrack needs: a
pass-by whoosh should be triggered by an actual pass, panned to the side the
vehicle actually went, and Doppler-shifted by its actual closing speed. So the
audio is generated from the same simulation as the picture rather than guessed.
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scene as SC


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = "/tmp/motion.json"
    if "--motion-out" in argv:
        i = argv.index("--motion-out")
        out_path = argv[i + 1]
        del argv[i:i + 2]
        sys.argv = sys.argv[:sys.argv.index("--") + 1] + argv

    cfg = SC.parse()
    cfg.update(width=64, height=36, samples=1, motion_blur=False)
    road, traffic, cobj, look = SC.build(cfg)

    fps = cfg["fps"]
    frames = int(cfg["duration"] * fps)
    cam_lane_u = SC.lane_u(cfg["lane"] - 1)

    events = []
    for c in traffic.cars:
        u = SC.lane_u(c["lane"], c["oncoming"])
        events.append(dict(lane=c["lane"], oncoming=bool(c["oncoming"]),
                           u=u, length=c["length"], kind=c["kind"],
                           v0=c["v0"]))

    rel = []           # per frame: camera speed, then (index, dz, dx) per car
    prev_s = None
    for f in range(frames):
        t = f / fps
        s_cam = traffic.camera_s(t)
        v_cam = (s_cam - prev_s) * fps if prev_s is not None else cfg["speed"]
        prev_s = s_cam
        near = []
        for i, c in enumerate(traffic.cars):
            travelled = traffic._at(c, t)
            s = -travelled if c["oncoming"] else travelled
            dz = s - s_cam                       # ahead is positive
            if abs(dz) > 90.0:                   # inaudible, skip
                continue
            dx = events[i]["u"] - cam_lane_u     # right is positive
            near.append([i, round(dz, 2), round(dx, 2)])
        rel.append(dict(v=round(v_cam, 3), near=near))

    data = dict(fps=fps, frames=frames, duration=cfg["duration"],
                look=cfg["look"], camera=cfg["camera"],
                speed=cfg["speed"], cars=events, motion=rel)
    with open(out_path, "w") as fh:
        json.dump(data, fh)
    print(json.dumps(dict(ok=True, out=out_path, frames=frames,
                          cars=len(events))))


if __name__ == "__main__":
    main()
