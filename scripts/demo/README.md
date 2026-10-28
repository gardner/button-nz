# The demo video

The demo video is one real, live run of the app, recorded in a headless
browser and then cut for length. Nothing is staged. Long waits are sped up,
and the video says so on screen.

- **`record.py`:** drives the app live and writes the raw recording. It
  confirms the survey, enters a brief, designs, waits for the AI visual, views
  the design in 3D, revises it, and shows before and after.
- **`screencast.py`:** the recorder `record.py` uses. It captures frames
  through Chrome's CDP screencast, because Playwright's own video recorder
  needs an ffmpeg build this OS lacks. It encodes with the ffmpeg build cached
  by Playwright, which reads files, not pipes, and only encodes VP9.
- **`cut.py`:** cuts the raw recording into a short MP4. It adds a title
  card, a caption per phase, a red "N× speed · live run" label on sped-up
  parts, and a closing card.

## Prerequisites

1. **The API and the production web build**, as in the top-level README. The
   recorder expects the web app at `http://localhost:3100/` by default:

   ```bash
   uv run --env-file .env python -m button_nz.api.serve --port 8000
   cd apps/web && pnpm build && pnpm start --port 3100
   ```

2. **Playwright's headless shell and ffmpeg.** `record.py` finds the newest
   `chromium_headless_shell-*` under `~/.cache/ms-playwright/`. It uses
   `ffmpeg-1013/ffmpeg-linux` from the same cache. `--chromium` and `--ffmpeg`
   override them.

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

The run is live: the design and the revision call the paid model APIs, and it
takes about eight minutes.

```bash
uv run python scripts/demo/record.py out/demo-raw.webm --screenshot out/revised.png
```

`--brief` and `--change` replace the brief and the revision instruction.
`--base-url` points it at another web app. The survey answers (`CHOICES`)
match the demo site's survey.

This writes `demo-raw.webm` (VP9, 15 frames a second) and
`demo-raw.webm.marks.json`.

A take fails, with the reason, if a design or the revision isn't accepted, or
if no checked AI visual appears. Its footage is still saved, as
`demo-raw-partial.webm`, so the paid calls aren't lost, but it isn't the take
the cut expects.

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
