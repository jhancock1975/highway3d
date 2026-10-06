"""The studio_ui Open WebUI tool, without Open WebUI: needs only fastapi and pydantic.

    $OWUI_PY studio-vast/ROOT/opt/studio-vast/owui/test_studio_ui.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import studio_ui as U  # noqa: E402

STATIC = tempfile.mkdtemp(prefix="owui-static-")
WORK = tempfile.mkdtemp(prefix="studio-work-")
MEDIA = os.path.join(STATIC, "studio", "media")
RENDERS = os.path.join(STATIC, "studio", "renders")
os.makedirs(MEDIA)
os.makedirs(RENDERS)


def note(aid, kind, ext, **extra):
    path = os.path.join(MEDIA, aid + ext)
    open(path, "wb").write(b"x")
    n = dict(id=aid, path=path, kind=kind, width=832, height=480, seconds=5.06, sound=False, **extra)
    json.dump(n, open(os.path.join(MEDIA, aid + ".json"), "w"))
    return n


note("pic-1a2b", "image", ".png")
note("clip-9c01", "video", ".mp4")
open(os.path.join(RENDERS, "rooftop-aa11bb.mp4"), "wb").write(b"x")
json.dump(dict(id="pic-evil", path="/etc/passwd", kind="image", width=1, height=1),
          open(os.path.join(MEDIA, "pic-evil.json"), "w"))


def tools():
    t = U.Tools()
    t.valves.static_dir, t.valves.work_dir, t.valves.poll_seconds = STATIC, WORK, 0.05
    return t


class Events(list):
    async def __call__(self, event):
        self.append(event)


def run(coro):
    return asyncio.run(coro)


def test_show_puts_pictures_clips_and_films_in_the_chat():
    page, text = run(tools().show("pic-1a2b, clip-9c01 rooftop-aa11bb.mp4"))
    body = page.body.decode()
    assert '<img src="/static/studio/media/pic-1a2b.png"' in body, body
    assert '<video src="/static/studio/media/clip-9c01.mp4"' in body
    assert '<video src="/static/studio/renders/rooftop-aa11bb.mp4"' in body
    assert page.headers["content-disposition"] == "inline"
    assert "pic-1a2b" in text and "clip-9c01" in text and "rooftop-aa11bb.mp4" in text


def test_show_says_what_it_could_not_find():
    said = run(tools().show("pic-zzzz"))
    assert isinstance(said, str) and "pic-zzzz" in said and "not in the library" in said, said


def test_show_never_serves_files_outside_the_static_folder():
    said = run(tools().show("pic-evil"))
    assert isinstance(said, str) and "pic-evil" in said, said


def write_log(job, *lines):
    with open(os.path.join(WORK, f"job-{job}.log"), "w") as fh:
        fh.write('JOB {"name": "animate pic-1a2b"}\n' + "".join(x + "\n" for x in lines))


def test_watch_shows_progress_live_then_the_clip():
    U._alive = lambda job: True
    write_log("w1", 'PROGRESS {"stage": "high-noise pass, step 2 of 4", "percent": 50.0}')

    def finish():
        time.sleep(0.3)
        with open(os.path.join(WORK, "job-w1.log"), "a") as fh:
            fh.write('DONE {"out": "%s", "seconds": 5.06, "bytes": 1, "took": 9, "asset": "clip-9c01"}\n'
                     % os.path.join(MEDIA, "clip-9c01.mp4"))
    threading.Thread(target=finish).start()
    ev = Events()
    page, text = run(tools().watch_job("w1", __event_emitter__=ev))
    assert any(e["type"] == "status" and "high-noise pass" in e["data"]["description"]
               and "50%" in e["data"]["description"] for e in ev), ev
    # Progress stays in the status line: an embedded frame redrawn on every update collapses and
    # regrows, and the chat jumps while the person scrolls.
    assert not any(e["type"] == "embeds" for e in ev), [e for e in ev if e["type"] == "embeds"]
    assert any(e["type"] == "status" and "\u25b0" in e["data"]["description"] for e in ev), ev
    assert "clip-9c01" in page.body.decode() and "clip-9c01" in text


def test_watch_reports_a_failure():
    U._alive = lambda job: True
    write_log("w2", "FAILED ComfyUI is not answering at http://127.0.0.1:18188")
    said = run(tools().watch_job("w2", __event_emitter__=Events()))
    assert "failed" in said and "not answering" in said, said


def test_watch_notices_a_job_whose_process_died():
    U._alive = lambda job: False
    write_log("w3", 'PROGRESS {"stage": "low-noise pass, step 1 of 4", "percent": 25.0}')
    old = time.time() - 60
    os.utime(os.path.join(WORK, "job-w3.log"), (old, old))
    said = run(tools().watch_job("w3", __event_emitter__=Events()))
    assert "stopped" in said, said


def test_watch_an_unknown_job():
    said = run(tools().watch_job("nope42", __event_emitter__=Events()))
    assert "no studio job" in said, said


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
