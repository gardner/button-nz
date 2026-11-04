# The demo video

The demo video is one real, live run of the app, recorded in a headless
browser and then cut for length. Nothing is staged. Long waits are sped up,
and the video says so on screen.

- **`record.py`:** drives the app live and writes the raw recording. It:
  - shows the survey as the owner decided it, and the site in 3D;
  - enters a brief, designs, and waits for the AI visual;
  - views the design in 3D, revises it, and shows before and after;
  - shows the real prefabs that fit, and asks to place the largest on the site.
- **`screencast.py`:** the recorder `record.py` uses. It captures frames
  through Chrome's CDP screencast, because Playwright's own video recorder
  needs an ffmpeg build this OS lacks. It encodes with the ffmpeg build cached
  by Playwright, which reads files, not pipes, and only encodes VP9.
- **`cut.py`:** cuts the raw recording into a short MP4. It adds a title
  card, a caption per phase, a red "N× speed · live run" label on sped-up
  parts, and a closing card. It can open on the site's relief fly-over
  (`--intro`), captioned as not the live run.

## Prerequisites

1. **The app as judges see it**, served by `scripts/deploy/install.sh`
   ([docs/deploy.md](../../docs/deploy.md)), with the survey fixed as the owner
   decided it. The take records the owner's decisions, so a survey that isn't
   fixed fails it before any paid call. Give the recorder the access code's
   link, which sets the cookie:

   ```bash
   source <(grep ACCESS_CODE ~/.config/button-nz/deploy.env)
   uv run python scripts/demo/record.py out/demo-raw.webm \
     --base-url "http://127.0.0.1:3000/?code=$BUTTON_ACCESS_CODE"
   ```

2. **Playwright's headless shell and ffmpeg.** `record.py` finds the newest
   `chromium_headless_shell-*` and the newest `ffmpeg-*/ffmpeg-linux` under
   `~/.cache/ms-playwright/`, before anything is recorded, so a missing one
   can't cost a paid run. `--chromium` and `--ffmpeg` override them.

   ```bash
   uv run playwright install chromium-headless-shell ffmpeg
   ```

3. **The shell's system libraries.** On Ubuntu 26.04 the headless shell is
   missing a few libraries, and installing them system-wide isn't needed.
   Unpack them from their `.deb` files into a directory of your choice, then
   put that directory on `LD_LIBRARY_PATH`:

   ```bash
   # Download and unpack the libraries into $1 (e.g. ~/.local/opt/browser-libs).
   browser_libs_install() {
     mkdir -p "$1/debs" "$1/root"
     (cd "$1/debs" && apt-get download libatk1.0-0t64 libatk-bridge2.0-0t64 \
       libatspi2.0-0t64 libxcomposite1 libxdamage1 libxrandr2 libxres1)
     for deb in "$1"/debs/*.deb; do dpkg-deb -x "$deb" "$1/root"; done
   }

   # Put the libraries in $1 on the library path of this shell.
   browser_libs_use() {
     export LD_LIBRARY_PATH="$1/root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
   }

   browser_libs_install ~/.local/opt/browser-libs
   browser_libs_use ~/.local/opt/browser-libs
   ldd ~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell | grep 'not found'
   ```

   If `ldd` still lists a library, add its package to the download.

4. **DejaVu fonts** for the cut, at `/usr/share/fonts/truetype/dejavu/`.
   `--sans` and `--bold` override them.

## Record

The run is live: the design, the revision and the placed prefab call the paid
model APIs, and it takes about a quarter of an hour.

```bash
uv run python scripts/demo/record.py out/demo-raw.webm --screenshot out/revised.png \
  --base-url "http://127.0.0.1:3000/?code=$BUTTON_ACCESS_CODE"
```

`--brief` and `--change` replace the brief and the revision instruction.
`--base-url` points it at another web app.

This writes `demo-raw.webm` (VP9, 15 frames a second) and
`demo-raw.webm.marks.json`.

A take fails, with the reason, if a design, the revision or the placement
isn't accepted, or if no checked AI visual appears. Its footage and marks are
still saved, as `demo-raw-partial.webm` and `demo-raw-partial.webm.marks.json`,
so the paid calls aren't lost. A failed take can still be cut up to where it
stopped, from its own marks. The published video was: the final take's
placement wasn't accepted ([docs/submission.md](../../docs/submission.md)), so
it was cut from `demo-raw-partial.webm`, and the committed plan ends before the
placement.

## Phase marks

The recorder prints and saves a timestamped mark as each phase starts, such
as `the brief`, `Muse designs`, `the accepted design`, `the AI visual` and
`revising in plain words`:

```json
{"seconds": 476.9, "marks": [[3.0, "the site: title, parcels and the aerial"], [8.5, "..."]]}
```

The times are seconds into the raw recording. They tell you where each phase
begins, so you can choose the segments to cut and which waits to speed up.
The AI visual's mark also records how long the visual took.

## Cut

```bash
uv run python scripts/demo/cut.py out/demo-raw.webm out/button-nz-demo.mp4 --outro out/outro.json
```

**`plan.json`** holds the title card and the segments. Each segment is a span
of the raw recording, in its seconds, with a playback speed and a caption.
Segments run in order and must not overlap. A segment with `speed` above 1
keeps every `speed`-th frame and gets the speed label. The committed plan
matches the recording in the published video, and its captions describe that
run. A new recording needs new times and captions, read from its marks.
`--plan` picks another file.

```json
{"start": 23.0, "end": 217.0, "speed": 12, "caption": "Muse Spark chooses LiDAR views..."}
```

A segment may also carry `lines`, a fact shown over its footage on a dark
panel, for a long sped-up wait. The footage is darkened, and the caption and
speed label stay, so it's still clear what is playing. Take every fact from a
report, and give its source in the docs.

**`opening`** (optional, in the plan) is the why before the how: beats shown
first, each a span of the raw recording from anywhere in it (not in order),
darkened under a headline on a dark panel. A beat's `at` is `"centre"`, the
default, or `"bottom"`, which keeps the middle of the frame, where the result
usually is, clear. With an opening, the title card may be empty (`"title": []`),
and is then left out.

```json
{"start": 503.1, "end": 515.1, "speed": 1, "at": "bottom",
 "lines": [{"text": "Our solution", "size": 44, "bold": true}, {"text": "Type any address…", "size": 30}]}
```

**`--intro`** (optional) plays a clip between the title card and the live
run: the demo site's relief fly-over (#149), its LINZ aerial photo draped on
its own LiDAR. Every intro frame is letterboxed to the recording's size,
resampled to its frame rate, and captioned as not the live run. Make the clip
with the relief benchmark, outside the repo:

```bash
uv run python -m button_nz.bench.relief out/relief --full out/relief/full
uv run python scripts/demo/cut.py out/demo-raw.webm out/button-nz-demo.mp4 \
  --outro out/outro.json --intro out/relief/full/flyover.mp4
```

**`--outro`** is the closing card: a JSON list of lines. Each line has a
`text`, a pixel `size`, and optionally `"bold": true`. An empty text is a
spacer. The card's claims are yours, so take them from the benchmark reports:

```json
[
  {"text": "What feedback buys", "size": 40, "bold": true},
  {"text": "", "size": 14},
  {"text": "Full reports in the repository", "size": 22}
]
```

The title shows for 4 seconds and the closing card for 7 seconds. The output is
H.264 at the raw recording's rate (`--fps`, 15 by default).

## Score

`score.py` puts music under the cut. The video stream is copied unchanged. The
music is cut to the video's length, faded in over 0.5 s and out over 4 s, and
scaled so its peak is at -1 dBFS, then encoded as AAC. Music shorter than the
video is refused, never looped or padded.

```bash
uv run python scripts/demo/score.py out/button-nz-demo.mp4 out/music.wav out/button-nz-demo-scored.mp4
```

**The published video's music** is original, generated with
[MiniMax-Music3](https://huggingface.co/MiniMaxAI/MiniMax-Music3) (MiniMax-Music3
Community License) from a description in words. The model takes only text, so
no recording was given to it. The description is of a style, tribal
percussion with a wordless chant at about 112 BPM. It names no work, composer
or melody. It was run with the model card's diffusers pipeline on one RTX 5090,
outside this project's environment, because it needs a pre-release diffusers
build and torch:

```text
Genre: tribal drumming, percussion ensemble, cinematic world music. BPM: 112. Key: B major.
The drums are the lead instrument, loud and upfront the whole time; melody is minimal.
Mood: earthy, driving and hopeful; a lone frame drum opens, hand drums, deep low toms and
shakers join in turn, the full drum ensemble drives the middle, and it resolves on a final
unison hit. Vocals: an occasional wordless group chant of mixed voices, short sustained
open vowels answering the drums, no words, always behind the percussion. Arrangement:
frame drums, hand drums and deep low toms in interlocking syncopated sixteenth-note
patterns, shakers, wooden clicks and claps, a low drone underneath; no synths, no guitars,
no piano, no strings. Production: dry and close, wide stereo percussion, natural room,
punchy transients, strong clean low end.
```

The lyrics were section tags only (`[Intro]`, `[Verse]`, … `[Outro]`, each
`[Instrumental]`), with `audio_duration=140.0`. The output is 44.1 kHz stereo.
