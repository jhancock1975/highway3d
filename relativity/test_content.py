"""Check every line of the lecture renders before committing to a long build.

    python3 test_content.py

A single unsupported LaTeX command kills a 35,000-frame render 20 minutes in,
and matplotlib's mathtext supports a subset of LaTeX -- \\emph is not in it.
This renders every math line and instantiates every panel, which takes seconds.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content
import visuals


def main():
    segs = content.all_segments()
    failures = []

    for seg in segs:
        v = seg["visual"]
        if v["kind"] == "math":
            for ln in v["lines"]:
                try:
                    visuals.math_image(ln, 34, (255, 255, 255))
                except Exception as e:
                    failures.append(("math", ln, str(e).splitlines()[-1][:90]))
        elif v["kind"] == "diagram":
            if v["name"] not in visuals.DIAGRAMS:
                failures.append(("diagram", v["name"], "no such diagram"))
        try:
            visuals.render_panel(v, 0.5)
        except Exception as e:
            failures.append(("panel", v.get("name", v["kind"]),
                             str(e).splitlines()[-1][:90]))

    words = content.word_count()
    print(f"chapters {len(content.CHAPTERS)}  segments {len(segs)}  "
          f"words {words}  (~{words/145:.1f} min of speech)")
    if failures:
        for kind, what, err in failures:
            print(f"  FAIL [{kind}] {str(what)[:60]} -> {err}")
        print(f"FAIL: {len(failures)} problem(s)")
        sys.exit(1)
    print("PASS: every math line renders and every panel builds")


if __name__ == "__main__":
    main()
