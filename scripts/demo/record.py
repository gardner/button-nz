"""Record the live demo run in a headless browser.

Show the survey as the owner decided it, enter a brief, design, wait for the
AI visual, view the design in 3D, revise it in plain words, show before and
after, then the real prefabs that fit, and place one. Everything is live: the
designs, the revision and the placing call the paid model APIs. Each phase is
marked, so ``cut.py`` can caption it and speed up the waits.

The take records the owner's decisions, so it needs a server that serves the
survey fixed as the owner decided it (``serve --survey-decided-by``); any other
fails the take before a paid call.
"""

import argparse
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, sync_playwright

from screencast import Screencast, find_chromium, find_ffmpeg

BRIEF = (
    "A two-bedroom dwelling of about 60 square metres that gets the afternoon sun"
    " and keeps the trees."
)
CHANGE = "Move it as close to the street as the rules allow, keeping the trees."
FIXED = re.compile(r"This survey is fixed on this server, as (.+?) decided it\.")
PLACE = re.compile(r"^Place the (.+) on the site$")
DESIGN_LIMIT_S = 1200
VISUAL_LIMIT_S = 180


@dataclass(frozen=True)
class Options:
    out: Path
    base_url: str
    brief: str
    change: str
    chromium: Path
    ffmpeg: Path
    fps: int
    screenshot: Path | None


@dataclass(frozen=True)
class Run:
    page: Page
    cast: Screencast


def body_text(page: Page) -> str:
    return page.inner_text("body")


def status_text(page: Page) -> str:
    """The shown job's status line only (``role="status"``), never attempt feedback."""
    status = page.get_by_role("status")
    return status.first.inner_text() if status.count() else ""


def wait_for(
    page: Page, done: Callable[[str], bool], limit_s: float, read: Callable[[Page], str] = body_text
) -> int:
    """Poll ``read(page)`` until ``done``; the seconds it took."""
    start = time.time()
    while time.time() - start < limit_s:
        if done(read(page)):
            return round(time.time() - start)
        page.wait_for_timeout(3000)
    raise TimeoutError(f"the page didn't finish within {limit_s} s")


IN_PROGRESS = ("Design queued…", "Design running…")
RENDERS_LOADED = """() => ["Before", "After"].every((side) => {
  const image = document.querySelector(`img[alt^="${side}"]`);
  return image !== null && image.complete && image.naturalWidth > 0;
})"""
VISUAL_LOADED = """() => {
  const shown = [...document.querySelectorAll('img[alt^="AI illustration"]')].at(-1);
  return shown !== undefined && shown.complete && shown.naturalWidth > 0;
}"""


def outcome(text: str) -> str | None:
    """How the shown design ended, read from its status line (not from words in
    attempt feedback, which can say "running"); None while it is being made."""
    if any(status in text for status in IN_PROGRESS):
        return None
    if "The design run failed:" in text:
        return "the design run failed"
    if "No attempt passed every check." in text:
        return "no attempt passed every check"
    if re.search(r"Accepted: attempt \d+", text):
        return "accepted"
    return None


def fixed_by(text: str) -> str | None:
    """Who decided the survey the page shows fixed, or None if it isn't."""
    found = FIXED.search(text)
    return None if found is None else found.group(1)


def placed_name(label: str) -> str | None:
    """The product a "Place the ... on the site" button places."""
    found = PLACE.match(label)
    return None if found is None else found.group(1)


def partial_path(out: Path) -> Path:
    """Where a failed take's footage goes: paid calls aren't thrown away."""
    return out.with_name(f"{out.stem}-partial{out.suffix}")


def until_accepted(page: Page) -> int:
    """Wait for the shown design to end; anything but accepted fails the take."""
    took = wait_for(page, lambda t: outcome(t) is not None, DESIGN_LIMIT_S, status_text)
    ended = outcome(status_text(page))
    if ended != "accepted":
        raise RuntimeError(f"no design was accepted: {ended}")
    return took


def centre(element: Locator) -> None:
    """Bring ``element`` to the middle of the screen. Playwright's "if needed"
    leaves a partly visible element where it is, half off screen."""
    element.evaluate("e => e.scrollIntoView({block: 'center'})")


def open_site(run: Run, base_url: str) -> None:
    run.page.goto(base_url, wait_until="networkidle")
    run.cast.mark("the site: title, parcels and the aerial")
    run.page.wait_for_timeout(4000)
    run.page.mouse.wheel(0, 900)
    run.page.wait_for_timeout(1500)


def show_survey(run: Run) -> None:
    """Show the survey as the owner decided it, feature by feature."""
    page = run.page
    note = page.get_by_text(FIXED)
    note.wait_for(timeout=30_000)
    who = fixed_by(body_text(page))
    if who is None:
        raise RuntimeError("the survey isn't fixed: serve it as the owner decided it")
    run.cast.mark(f"SAM 3.1 survey, as {who} decided it")
    centre(note)
    page.wait_for_timeout(3000)
    for card in page.get_by_role("article").all():
        centre(card)
        page.wait_for_timeout(1200)


def design(run: Run, brief: str) -> None:
    page = run.page
    page.mouse.wheel(0, -3000)
    page.wait_for_timeout(1500)
    page.locator("svg[aria-label='Site plan, north up']").scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    box = page.get_by_role("textbox").first
    run.cast.mark("the brief")
    box.click()
    box.press_sequentially(brief, delay=35)
    page.get_by_role("button", name="Design").click()
    run.cast.mark("Muse designs (live; Blender builds and the evaluator checks each attempt)")
    print("design took", until_accepted(page), "s", flush=True)
    page.wait_for_timeout(2000)
    run.cast.mark("the accepted design")


def show_visual(run: Run) -> None:
    """Wait for Muse Image's checked, labelled visual, and show it. The take
    promises one, so without it the take fails (its footage is kept apart)."""
    try:
        took = wait_for(run.page, lambda t: "AI-illustrated" in t, VISUAL_LIMIT_S)
    except TimeoutError as error:
        raise RuntimeError("no checked AI visual was shown") from error
    try:  # the caption shows at once; the take needs the image itself, decoded
        run.page.wait_for_function(VISUAL_LOADED, timeout=30_000)
    except PlaywrightError as error:
        raise RuntimeError("the AI visual didn't load") from error
    run.cast.mark(f"the AI visual (Muse Image, silhouette checked by SAM 3.1; {took} s later)")
    centre(run.page.get_by_alt_text(re.compile(r"^AI illustration")).last)
    run.page.wait_for_timeout(5000)


def view_3d(run: Run) -> None:
    run.page.get_by_role("button", name="View in 3D").last.click()
    # The viewer is drawn below the attempt cards: bring it, not the button, on screen.
    viewer = run.page.locator('[data-model="loaded"]').last
    try:  # the canvas shows before the model has loaded: wait for the model
        viewer.wait_for(state="visible", timeout=60_000)
    except PlaywrightError as error:
        raise RuntimeError("the 3D model didn't load") from error
    centre(viewer)
    run.cast.mark("the 3D model")
    run.page.wait_for_timeout(6000)


def revise(run: Run, change: str) -> None:
    page = run.page
    instruction = page.get_by_label("Change this design")
    instruction.scroll_into_view_if_needed()
    instruction.click()
    instruction.press_sequentially(change, delay=35)
    page.get_by_role("button", name="Revise").click()
    run.cast.mark("revising in plain words (live)")
    # The revision is shown once it starts; until then the last design's status shows.
    wait_for(page, lambda t: any(status in t for status in IN_PROGRESS), 60, status_text)
    print("revision took", until_accepted(page), "s", flush=True)
    page.wait_for_timeout(3000)


def before_and_after(run: Run) -> None:
    try:
        run.page.wait_for_function(RENDERS_LOADED, timeout=30_000)
    except PlaywrightError as error:
        raise RuntimeError("the before and after renders didn't load") from error
    run.cast.mark("before and after")
    # The renders themselves, not the first text that says "Before".
    centre(run.page.get_by_alt_text(re.compile(r"^Before")).first)
    run.page.wait_for_timeout(6000)


def show_products(run: Run) -> None:
    """Ask which real prefabs fit the design on show, and show them."""
    page = run.page
    ask = page.get_by_role("button", name="Which real prefabs fit?").last
    centre(ask)
    ask.click()
    page.get_by_role("heading", name="Next steps").wait_for(timeout=30_000)
    run.cast.mark("real prefabs that fit, with their published prices, and the next steps")
    centre(page.get_by_role("listitem").filter(has=page.get_by_role("link")).first)
    page.wait_for_timeout(6000)


def place_product(run: Run) -> None:
    """Place the largest prefab that fits, and wait for it to be checked."""
    page = run.page
    place = page.get_by_role("button", name=PLACE).first
    name = placed_name(place.get_attribute("aria-label") or "")
    if name is None:
        raise RuntimeError("no prefab fits the design, so there is none to place")
    centre(place)
    place.click()
    page.get_by_text(f"Placing the {name}").wait_for(timeout=30_000)
    run.cast.mark(f"placing the {name} on the site (live)")
    print("placing took", until_accepted(page), "s", flush=True)
    page.wait_for_timeout(2000)
    run.cast.mark(f"the {name}, placed: its walls checked against its footprint")
    centre(page.get_by_text("product_footprint").last)
    page.wait_for_timeout(6000)


def record(args: Options) -> None:
    args.out.parent.mkdir(parents=True, exist_ok=True)  # before any paid call
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=args.chromium, args=["--use-gl=angle", "--use-angle=swiftshader"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        run = Run(page, Screencast(context, page, ffmpeg=args.ffmpeg))
        try:
            take(run, args)
        except Exception:
            partial = partial_path(args.out)
            run.cast.encode(partial, fps=args.fps)
            print(f"the take failed; its footage is in {partial}", file=sys.stderr)
            raise
        run.cast.encode(args.out, fps=args.fps)
        print(len(run.cast.frames), "frames")
        browser.close()


def take(run: Run, args: Options) -> None:
    open_site(run, args.base_url)
    show_survey(run)
    design(run, args.brief)
    show_visual(run)
    view_3d(run)
    revise(run, args.change)
    if args.screenshot is not None:
        run.page.screenshot(path=args.screenshot, full_page=True)
    show_visual(run)
    before_and_after(run)
    show_products(run)
    place_product(run)
    print(run.page.inner_text("body")[-3500:])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Record the live demo run.")
    parser.add_argument("out", type=Path, help="the raw recording, a .webm")
    parser.add_argument("--base-url", default="http://localhost:3100/")
    parser.add_argument("--brief", default=BRIEF)
    parser.add_argument("--change", default=CHANGE, help="the revision, in plain words")
    parser.add_argument("--chromium", type=Path, help="default: Playwright's headless shell")
    parser.add_argument("--ffmpeg", type=Path, help="default: Playwright's newest build")
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--screenshot", type=Path, help="a full-page shot after the revision")
    args = parser.parse_args(argv)
    chromium: Path = args.chromium or find_chromium()
    ffmpeg: Path = args.ffmpeg or find_ffmpeg()  # both found before any paid call
    if not ffmpeg.is_file():
        raise FileNotFoundError(f"no ffmpeg at {ffmpeg}")
    record(
        Options(
            out=args.out,
            base_url=args.base_url,
            brief=args.brief,
            change=args.change,
            chromium=chromium,
            ffmpeg=ffmpeg,
            fps=args.fps,
            screenshot=args.screenshot,
        )
    )


if __name__ == "__main__":
    main()
