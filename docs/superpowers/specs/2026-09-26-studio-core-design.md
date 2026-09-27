# Studio core: general-purpose audio and video tools over MCP

2026-09-26. Piece 1 of 4.

## Why

The two MCP servers here each wrap one finished pipeline. Lectern (:8767)
makes a lecture with the professor in the study. Highway (:8766) makes a
highway drive. The parts inside them are general: Kokoro speech with word
timings, numpy music, Blender, Manim, GIMP, ffmpeg. But a caller can only get
at them as "a lecture" or "a highway clip". The Pockterm spot showed where
that breaks. Its best lines wanted real app footage, the lecture renderer
cannot cut to footage, and so those shots became chalkboard boards.

What should be makeable, and is not today:

- promos with real footage: voiceover and music cut against screen
  recordings, stills and titles
- explainers with any presenter, or none: voice over images, diagrams and
  shots
- short animated scenes beyond the study and the highway
- audio on its own: voiceovers, music beds, sound effects

## The four pieces

This spec is piece 1. Each later piece gets its own spec and plan.

1. **Studio core** (this spec): a media library, speech, music, drawn and
   generated images, footage brought in as files or URLs, and a timeline
   editor. It makes promos, voice-over explainers and audio on its own.
   1b. **Capture** (next spec): record the iOS Simulator, the Mac screen and
   a cabled iPhone, driven by a script of taps and typing. It needs app
   driving and macOS permissions, which would swamp this spec.
2. **Characters on camera**: any presenter, or none, speaking any audio in
   any set; diagram and equation shots. The lecture presenter, taken out of
   the lecture.
3. **Animated 3D scenes**: a scene description becomes a Blender shot with
   characters, props and places.
4. **One call for Cider**: "make a video about X" plans the video and
   drives pieces 1 to 3, as a job.

Two kinds of caller use this. A capable agent (Claude, Codex) chains the
small tools and does the directing. Cider's 27B gets one tool call per turn,
so it waits for piece 4, which is built on the small tools.

Lectern and highway stay as they are. Cider uses `lecture_make` and
`lecture_status` today.

## Decisions already made

- Our own timeline format, rendered by ffmpeg (approach A). OpenTimelineIO
  and MLT (approach B) and Blender's sequencer (approach C) were weighed and
  set aside. The format stays close enough to OTIO's tracks-of-trimmed-clips
  shape that an OTIO export can be added later for finishing an edit by hand
  in Kdenlive or Resolve.
- iMovie is not an engine. Its AppleScript dictionary cannot build a
  timeline, so it could only be driven by clicking through its UI, which is
  too fragile for other agents to depend on.
- The installed ffmpeg (9.0.1) has `xfade`, `acrossfade`,
  `sidechaincompress` and `zoompan`, and has neither `drawtext` nor
  `subtitles`. Titles and captions are drawn as images and overlaid.
- No LaunchAgent. The server runs as a plain process until John decides the
  stack is stable, so a bad build cannot crash-loop at boot.

## Architecture

A new package, `studio/`, with its own MCP server on port 8768. It is built
on `forgiving.ForgivingServer`, so a bad argument is mended and the result
says what was changed, rather than coming back as a validation error.

The studio orchestrates, and each engine runs in its own interpreter, the
way `lectern/build.py` already works:

| Work | Engine | Where it runs |
|---|---|---|
| speech | Kokoro | `.ttsvenv` |
| music | the numpy composer in `highway3d/music.py` | `studio/.venv` |
| drawn images | GIMP 3.2, headless `gimp-console` | GIMP's own Python |
| generated images | xAI `grok-imagine-image-2.0` | remote, prepaid |
| editing | ffmpeg | subprocess |

One module per job:

- `studio/library.py`: the media library. Every file made or imported gets a
  short id with a prefix saying where it came from: `voice-` (speech),
  `music-`, `card-` (drawn), `pic-` (generated), and for imports `clip-`
  (video), `image-` (still) and `sound-` (audio). Each has a JSON sidecar recording kind,
  length, size, source and, for speech, the word timings. Files live under
  `studio/media/`, which is gitignored. Probing uses ffprobe.
- `studio/speech.py`: text to speech. The six voices already downloaded
  (`af_heart`, `af_nova`, `am_michael`, `am_onyx`, `bf_emma`, `bm_george`)
  go to Kokoro directly: lang code `a` for `a*` voices and `b` for `b*`,
  keeping each word's start and end. The `einstein` preset goes through
  `lectern.narrate`, which already records word timings for its accented
  voice.
- `studio/music.py`: a music bed from a mood (`drive`, `open` or `night`,
  the three `highway3d/music.py` defines, read from it rather than copied)
  and a length.
- `studio/images.py`: cards drawn by GIMP, and pictures from xAI.
- `studio/timeline.py`: load an edit, normalise it, and check it. Every
  problem comes back as a sentence, and all of them at once.
- `studio/assemble.py`: turn a checked edit into one ffmpeg run. All the
  text images the edit needs (cards referenced by style, caption chunks) are
  drawn first, in a single GIMP session.
- `studio/jobs.py`: background jobs, logs and status.
- `studio/mcp_server.py`: the tools.

## Tools

All are prefixed `studio_`: local names win a collision in Cider, so a tool
called something Cider already uses would be ignored. Every description
names its allowed values and defaults in its own text, because Cider's
router shows descriptions and argument names only, never the schema's enums.
Every tool that makes something returns the asset id and the file's absolute
path.

| Tool | Takes | Gives back |
|---|---|---|
| `studio_describe` | nothing | voices, moods, card styles, and the edit format with one worked example |
| `studio_import` | `source`: a file path on this Mac or an http(s) URL; `name` (optional, a label shown by `studio_list`; edits still use the id) | an asset (video, image or audio) with length and size |
| `studio_speak` | `text`; `voice` (af_heart, af_nova, am_michael, am_onyx, bf_emma, bm_george or einstein; default am_michael); `speed` (0.5 to 2, default 1) | an audio asset with word timings kept |
| `studio_music` | `mood` (drive, open or night; default drive); `seconds` (1 to 600, default 30) | a music asset |
| `studio_card` | `title`; `subtitle`; `style` (dark, light, chalkboard or sign; default dark); `width`, `height` (default 1920x1080) | an image asset drawn by GIMP |
| `studio_picture` | `prompt`; `aspect` (16:9, 9:16, 1:1, 4:3, 3:4, 3:2, 2:3, 21:9 or auto; default 16:9); `resolution` (1k, 1.5k or 2k; default 2k); `references`: up to 5 asset ids | an image asset from xAI |
| `studio_assemble` | `edit`: the format below | a job id and a time estimate |
| `studio_status` | `job` (optional) | the newest job and any still running, or the named one |
| `studio_list` | `kind` (optional: video, image, audio) | library assets, newest first |

Speech, music, cards and pictures run inline, because each takes seconds.
Only assembly runs as a background job. `studio_picture` posts to
`/v1/images/generations`, or with `references` to `/v1/images/edits` (as
`images`, base64 data URIs), so a GIMP layout can be repainted. It asks for
`b64_json`, so nothing depends on xAI keeping a URL alive, and saves the
image into the library. xAI's pricing page lists a flat per-image price per
model; the first real call confirms whether 2k costs more than 1k.

Sound-effect generation is not in this piece. Effects can be imported and
mixed.

## The edit format

```json
{
  "size": "1920x1080",
  "fps": 30,
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
  ],
  "name": "pockterm-spot"
}
```

**video** plays in order, so start times follow from lengths and nobody
computes timecodes.

- `from` and `seconds` trim. A video clip runs to its end by default; a
  still is 4 seconds by default.
- `transition` into a clip: `cut` (default), `dissolve` (xfade) or `fade`
  (through black). Each lasts 0.5 s and overlaps the clip before it.
- `fit`: `cover` (crop to fill, default) or `contain` (letterbox).
- `move` animates a still: `none` (default), `push-in`, `pull-out`,
  `pan-left` or `pan-right`.
- A clip's own sound is kept at `level` 1 unless set otherwise; `level: 0`
  mutes it.

**overlays** are timed images on top.

- `at` and `seconds` place them in time. `place`: `full` (default),
  `center`, `top`, `bottom`, `top-left`, `top-right`, `bottom-left` or
  `bottom-right`.
- `captions` names a speech asset. Its words are drawn in chunks of up to
  seven words, each shown from its first word's start to its last word's
  end, offset by wherever that speech sits in `audio`.

**audio** items are placed by `at` (default 0).

- `level` is 0 to 1 (default 1). `fade` is seconds of fade in and out
  (default 0 for speech, 1 for music).
- `duck: true` dips the track under every speech asset in the edit, with
  `sidechaincompress`.
- Anything running past the end of the video is trimmed, and music fades
  out over its last `fade` seconds.

**Output.** `size` is any WxH (1920x1080, 1080x1920 and 1080x1080 are the
usual ones). `fps` defaults to 30. The result is an H.264 and AAC mp4 in
`renders/<name>-<job>.mp4`. An edit with no `video` makes
`renders/<name>-<job>.m4a`. The length is the video track's, or the longest
audio item's when there is no video.

**Assets** may be ids or absolute file paths. A path is imported first, so
the result can name the id it was given.

**Checking** happens before anything renders, like `lecture_check`, and
reports every problem at once:

- "video item 2: clip-9c01 is 9 seconds long, so from 12 is past its end."
- "overlay 1: there is no asset called card-7d3e."
- "captions: voice-3f2a is music, not speech, so it has no words to show."

## Jobs

`studio_assemble` checks the edit, writes it to `studio/.work/`, and starts
`python -m studio.assemble` as a detached process (`start_new_session`).
The log `studio/.work/job-<id>.log` opens with a `JOB {...}` line naming the
output, then `PROGRESS {...}` lines, then `DONE {...}` or `FAILED <reason>`.

`studio_status` works as `lecture_status` does now:

- with no job, it reports the newest job, and every other job still running,
  one line each: "Job 5a1c ('pockterm-spot'): encoding, 40% done."
- a job whose process has died with no `DONE` or `FAILED` is reported as
  stopped, not as stuck at its last progress line. Liveness comes from `ps`.
- with no jobs: "Nothing has been assembled on this server yet."

The time estimate comes from measured encode speed on this Mac, calibrated
by the first real renders, not guessed. The result says outright that
nothing announces the finish, and that `studio_status` answers whenever it
is asked.

## Errors

Every failure is a sentence, never a traceback.

- Bad arguments are mended by `forgiving.py`.
- An engine failure reports its last meaningful error line: "ffmpeg stopped:
  clip-9c01 has no video stream."
- xAI failures name the cause: "No xAI key is set; put XAI_API_KEY in the
  environment." "The xAI credits are used up; add more at console.x.ai." A
  refused prompt is reported with xAI's reason.
- The `XAI_API_KEY` is read from the environment only. It is never written
  to a log, a sidecar or a result.

## Memory guard

This Mac panicked on 2026-09-26 from memory exhaustion, so before starting
Kokoro, GIMP or an assembly, the studio reads available memory (free,
inactive and speculative pages from `vm_stat`). If that is less than the
job's need plus 4 GB of headroom, it refuses with the numbers: "The Mac has
6 GB available and speech needs about 2 GB plus headroom; try again when the
other work finishes."

Starting needs: speech 2 GB, GIMP 1 GB, assembly 2 GB. The first real runs
measure these, and the table is updated from the measurements.

## Testing

1. **Pure Python, no engines.** The edit checker (each mistake produces the
   expected sentence), the ffmpeg command builder (an edit plus probed
   assets gives the expected filtergraph), the library, caption chunking,
   job status (including a dead job), and the memory guard's arithmetic.
   These run in seconds and run every time.
2. **Real engines, only when the Mac is quiet.** Speak a sentence in a plain
   voice and in `einstein`; compose 5 s of music; draw a card in each style.
   Then assemble a 6-second edit with a card, a still with `push-in`, a
   dissolve, an imported clip, a voice, ducked music and captions. Check the
   output's length and streams with ffprobe, pull frames at set times, and
   look at them.
3. **Over HTTP.** List the tools, and call every one that does not start an
   assembly or spend xAI credit.

`studio_picture` gets one real test after the xAI key exists, to confirm
the request shape and the credits-used-up message.

## Running it

```bash
studio/.venv/bin/python -m studio.mcp_server --port 8768
```

`studio/.venv` is a uv venv with the MCP SDK and numpy. It runs as a plain
process, logging to `~/Library/Logs/studio-mcp.log`. `studio/README.md`
covers starting it and the edit format.

The studio is not added to Cider's `tool-servers.json` in this piece. Its
router would gain nine tool lines with nothing it can use in one call; piece
4 gives it that call.

## Not in this piece

- capture of the Simulator, the Mac screen or an iPhone (piece 1b)
- characters, diagrams and 3D shots (pieces 2 and 3)
- sound-effect generation
- OTIO export
- any change to lectern or highway
