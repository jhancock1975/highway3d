"""The memory guard's arithmetic, on vm_stat output. No engines.

    studio/.venv/bin/python studio/test_memory.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from studio import memory as M  # noqa: E402

# 65536 + 131072 + 65536 pages of 16 KiB is exactly 4 GiB available.
SAMPLE = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               65536.
Pages active:                            800000.
Pages inactive:                          131072.
Pages speculative:                        65536.
Pages throttled:                              0.
Pages wired down:                        900000.
"""


def test_available_counts_free_inactive_and_speculative():
    assert M.available_gb(SAMPLE) == 4.0


def test_room_means_no_refusal():
    assert M.refusal("speech", 7.0) == ""
    assert M.refusal("assembly", 9.5) == ""


def test_no_room_is_a_sentence_with_the_numbers():
    got = M.refusal("speech", 6.0)
    assert got == (f"The {M.MACHINE} has 6 GB available and speech needs about 3 GB "
                   "plus 4 GB of headroom; try again when the other work "
                   "finishes."), got
    assert "drawing needs about 1 GB" in M.refusal("gimp", 1.0)


MEMINFO = """MemTotal:       65843916 kB
MemFree:         1234567 kB
MemAvailable:   41943040 kB
Buffers:          123456 kB
"""


def test_linux_reads_memavailable():
    assert M.available_gb(meminfo_text=MEMINFO) == 40.0


def test_this_mac_reads():
    assert M.available_gb() > 0


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("ok  ", name)
        except AssertionError as e:
            bad += 1
            print("FAIL", name, str(e)[:300])
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
