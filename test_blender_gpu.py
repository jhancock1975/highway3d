"""Which Cycles back end wins, on any machine. Pure: no Blender needed.

    python3 test_blender_gpu.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_gpu as G  # noqa: E402


class _Dev:
    def __init__(self, name, kind):
        self.name, self.type, self.use = name, kind, False


class _Prefs:
    """Cycles' add-on preferences, for a machine with the given back ends."""
    def __init__(self, available):
        self.available = available          # {kind: [device names]}
        self._kind = "NONE"
        self.devices = []

    @property
    def compute_device_type(self):
        return self._kind

    @compute_device_type.setter
    def compute_device_type(self, kind):
        if kind not in self.available:
            raise TypeError(f"enum '{kind}' not found")
        self._kind = kind

    def refresh_devices(self):
        self.devices = [_Dev(n, self._kind) for n in self.available[self._kind]] + [_Dev("CPU", "CPU")]


class _Bpy:
    def __init__(self, available):
        prefs = _Prefs(available)
        addon = type("A", (), {"preferences": prefs})()
        self.context = type("C", (), {"preferences": type("P", (), {"addons": {"cycles": addon}})()})()
        self.prefs = prefs


def test_nvidia_prefers_optix_over_cuda():
    assert G.choose({"OPTIX": ["RTX PRO 6000"], "CUDA": ["RTX PRO 6000"]}) == "OPTIX"


def test_cuda_when_optix_finds_nothing():
    assert G.choose({"OPTIX": [], "CUDA": ["A40"]}) == "CUDA"


def test_mac_metal():
    assert G.choose({"METAL": ["Apple M3 Max"]}) == "METAL"


def test_cpu_when_nothing_found():
    assert G.choose({}) is None and G.choose({"CUDA": []}) is None


def test_enable_on_linux_nvidia_turns_optix_devices_on():
    bpy = _Bpy({"OPTIX": ["RTX PRO 6000"], "CUDA": ["RTX PRO 6000"], "NONE": []})
    assert G.enable(bpy) == "OPTIX"
    assert bpy.prefs.compute_device_type == "OPTIX"
    assert [d.use for d in bpy.prefs.devices] == [True, False]   # the GPU yes, the CPU no


def test_enable_on_a_mac_turns_metal_on():
    bpy = _Bpy({"METAL": ["Apple M3 Max"], "NONE": []})
    assert G.enable(bpy) == "METAL"


def test_enable_without_a_gpu_says_cpu():
    assert G.enable(_Bpy({"NONE": []})) == "CPU"


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
