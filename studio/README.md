# studio

General audio and video tools over MCP. Lectern makes lectures and highway
makes highway drives; the studio makes the pieces anything else is cut
from, and cuts them together.

```bash
studio/.venv/bin/python -m studio.mcp_server --port 8768   # streamable HTTP at /mcp
```

It runs as a plain process, not a LaunchAgent, until the stack is judged
stable. Log it with `>> ~/Library/Logs/studio-mcp.log 2>&1`.

## Tools

| Tool | Does |
|---|---|
| `studio_describe` | the voices, moods, card styles, and the edit format with an example |
| `studio_import` | brings in a video, picture or sound from a path or URL |
| `studio_speak` | text to speech, with word timings for captions |
| `studio_music` | a music bed from a mood, exactly as long as asked |
| `studio_card` | a text card drawn by GIMP |
| `studio_picture` | a picture from xAI (needs `XAI_API_KEY`; prepaid credit) |
| `studio_assemble` | cuts it all into an mp4 (or m4a), as a job |
| `studio_status` | how a job is going; no id means the newest |
| `studio_list` | what is in the library |

Every asset has an id saying where it came from: `voice-`, `music-`,
`card-`, `pic-`, and for imports `clip-`, `image-`, `sound-`. Files live in
`studio/media/` beside a JSON note each; finished edits go to `renders/`.

## The edit

```json
{
  "size": "1920x1080", "fps": 30, "name": "pockterm-spot",
  "video": [
    {"asset": "card-1a2b", "seconds": 3},
    {"asset": "clip-9c01", "from": 12, "seconds": 6, "transition": "dissolve"},
    {"asset": "pic-44d0", "seconds": 5, "move": "push-in", "transition": "fade"}
  ],
  "overlays": [
    {"asset": "card-7d3e", "at": 4, "seconds": 3, "place": "bottom"},
    {"captions": "voice-3f2a"}
  ],
  "audio": [
    {"asset": "voice-3f2a", "at": 0.5},
    {"asset": "music-77e1", "level": 0.15, "duck": true}
  ]
}
```

The video track plays in order, so nobody computes a timecode. The design
is in `docs/superpowers/specs/2026-09-26-studio-core-design.md`.

## Engines

| Work | Engine |
|---|---|
| speech | Kokoro, under `.ttsvenv` (`studio/speech_engine.py`, or `lectern.narrate` for einstein) |
| music | `highway3d/music.py` through `lectern.score` |
| cards and captions | GIMP 3.2, headless (`studio/gimp_draw.py`) |
| pictures | xAI `grok-imagine-image-2.0` |
| assembly | ffmpeg; this build has no drawtext, so text arrives as pictures |

Before starting speech, drawing or assembly, the studio checks the Mac has
the memory for it plus 4 GB, and says so if it does not.

## Tests

```bash
for t in library memory jobs timeline assemble speech music xai server; do
  studio/.venv/bin/python studio/test_$t.py | tail -1
done
studio/.venv/bin/python studio/test_engines.py   # real engines; only when the Mac is quiet
```
