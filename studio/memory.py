"""Whether this Mac has room to start something heavy.

On 2026-09-26 this Mac took a watchdog panic from memory exhaustion: a
music-model trial, a resident 8B, Cider's 27B and Blender, all at once, with
0.25 GB free and nothing left to reclaim. So speech, drawing and assembly
each check first, and refuse with the numbers rather than add to a pile.

Available is what macOS can hand out without paging: free, inactive and
speculative pages. The needs are what each engine was measured to take,
and the headroom is for everything else on the machine.
"""

from __future__ import annotations

import re
import subprocess
import sys

# Measured 2026-09-26 with /usr/bin/time -l: Kokoro peaked at 2.72 GB on a
# 60-word paragraph (the einstein voice at 1.43), GIMP at 0.54 GB drawing a
# card, and ffmpeg at 1.1 GB encoding 1080p.
NEEDS_GB = {"speech": 3.0, "gimp": 1.0, "assembly": 2.0}
HEADROOM_GB = 4.0
CALLED = {"speech": "speech", "gimp": "drawing", "assembly": "assembly"}
MACHINE = "Mac" if sys.platform == "darwin" else "machine"


def available_gb(vm_stat_text: str | None = None,
                 meminfo_text: str | None = None) -> float:
    """Gigabytes the system could hand out now: vm_stat on a Mac,
    MemAvailable from /proc/meminfo on Linux."""
    if vm_stat_text is None and meminfo_text is None:
        if sys.platform == "darwin":
            vm_stat_text = subprocess.run(["vm_stat"], capture_output=True,
                                          text=True).stdout
        else:
            with open("/proc/meminfo") as fh:
                meminfo_text = fh.read()
    if meminfo_text is not None:
        kb = int(re.search(r"^MemAvailable:\s+(\d+) kB", meminfo_text,
                           re.M).group(1))
        return round(kb / 2 ** 20, 2)
    text = vm_stat_text
    page = int(re.search(r"page size of (\d+) bytes", text).group(1))

    def pages(label: str) -> int:
        m = re.search(rf"^{label}:\s+(\d+)\.", text, re.M)
        return int(m.group(1)) if m else 0

    free = (pages("Pages free") + pages("Pages inactive")
            + pages("Pages speculative"))
    return round(free * page / 2 ** 30, 2)


def refusal(task: str, available: float | None = None) -> str:
    """'' if there is room for `task`, else the sentence saying why not."""
    have = available_gb() if available is None else available
    need = NEEDS_GB[task]
    if have >= need + HEADROOM_GB:
        return ""
    return (f"The {MACHINE} has {have:.0f} GB available and {CALLED[task]} needs "
            f"about {need:g} GB plus {HEADROOM_GB:g} GB of headroom; try "
            f"again when the other work finishes.")
