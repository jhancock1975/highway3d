"""owui-setup.py's banner while the director's model is not up, against a stand-in Open WebUI.

    python3 studio-vast/ci/test_owui_setup.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    "owui_setup", os.path.join(HERE, "..", "ROOT", "opt", "studio-vast", "bin", "owui-setup.py"))
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)

THEIRS = {"id": "theirs", "type": "info", "title": "", "content": "the person's own banner",
          "dismissible": True, "timestamp": 1}


class FakeOwui:
    def __init__(self, banners):
        self.banners, self.posts = list(banners), []

    def __call__(self, method, path, body=None, token=None, timeout=60):
        assert path == "/api/v1/configs/banners" and token == "tok", (method, path, token)
        if method == "GET":
            return 200, list(self.banners)
        self.posts.append(body["banners"])
        self.banners = list(body["banners"])
        return 200, self.banners


def run(banners, ups):
    fake, answers, naps = FakeOwui(banners), iter(ups), []
    S.call = fake
    S.wait_for_llm("tok", poll=7, up=lambda: next(answers), sleep=naps.append)
    return fake, naps


def test_a_banner_says_the_director_is_coming_until_it_answers():
    fake, naps = run([THEIRS], [False, False, True])
    shown = fake.posts[0]
    ours = [b for b in shown if b["id"] == S.BANNER_ID]
    assert THEIRS in shown and len(ours) == 1, shown
    assert "downloading" in ours[0]["content"] and ours[0]["dismissible"] is False, ours
    assert fake.posts[-1] == [THEIRS], fake.posts
    assert naps == [7], naps          # down at the first look, down once more, then up


def test_nothing_is_posted_when_the_director_is_already_up():
    fake, naps = run([THEIRS], [True])
    assert fake.posts == [] and naps == [], fake.posts


def test_a_banner_left_from_an_earlier_boot_is_taken_down():
    stale = {"id": S.BANNER_ID, "type": "warning", "title": "", "content": "old", "dismissible": False,
             "timestamp": 1}
    fake, _ = run([THEIRS, stale], [True])
    assert fake.posts == [[THEIRS]], fake.posts


if __name__ == "__main__":
    bad = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except (AssertionError, AttributeError) as e:
                bad += 1
                print("FAIL", name, type(e).__name__, str(e)[:300])
    sys.exit(1 if bad else 0)
