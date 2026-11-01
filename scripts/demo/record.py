"""Record the live demo run in a headless browser.

Open the town map and tilt it into 3D, find the property by its address,
show the survey as the owner decided it, enter a brief, design, stand the
design in 3D among the LiDAR's buildings, show the checked AI visual, revise
it in plain words and show before and after, then the real prefabs that fit,
and place one. Everything is live: the designs, the revision and the placing
call the paid model APIs. Each phase is marked, so ``cut.py`` can caption it
and speed up the waits.

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
FIXED = re.compile(r"Fixed on this server, as (.+?) decided it\.")
ADDRESS = "35 Victory Street, Reefton"
SITE_LIMIT_S = 900  # a site never built before: parcels, LiDAR, aerial, the SAM survey
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


IN_PROGRESS = ("Queued…", "Muse is designing")
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


def map_view(run: Run, label: str) -> None:
    """Switch the map to "2D" or "3D", and let it settle."""
    run.page.get_by_role("group", name="Map view").get_by_role("button", name=label).click()
    run.page.wait_for_timeout(3000)


def open_town(run: Run, base_url: str) -> None:
    page = run.page
    page.goto(base_url, wait_until="networkidle")
    page.get_by_text(re.compile(r"have room for a real prefab")).wait_for(timeout=60_000)
    page.wait_for_timeout(3000)  # the aerial's tiles
    run.cast.mark("Reefton's residential sections, screened: which have room for a real prefab")
    page.wait_for_timeout(5000)
    map_view(run, "3D")
    run.cast.mark("the town in 3D: every building at its LiDAR height")
    page.wait_for_timeout(6000)
    map_view(run, "2D")


def find_site(run: Run, address: str) -> None:
    """Search for the property and open it; a site never built is built first."""
    page = run.page
    box = page.get_by_label("Find an address")
    box.click()
    box.press_sequentially(address, delay=60)
    option = page.get_by_role("listbox", name="Addresses").get_by_role("option").first
    option.wait_for(timeout=30_000)
    run.cast.mark("any New Zealand address, from LINZ's national address register")
    page.wait_for_timeout(1500)
    option.click()
    page.get_by_text("What's on the site?").wait_for(timeout=SITE_LIMIT_S * 1000)
    page.wait_for_timeout(4000)  # the map flies there
    run.cast.mark("the site from open data: its title, the 1 m LiDAR and a 7.5 cm aerial")
    page.wait_for_timeout(3000)


def show_survey(run: Run) -> None:
    """Show the survey as the owner decided it. The take records the owner's
    decisions, so a survey the server hasn't fixed fails it before any paid call."""
    page = run.page
    note = page.get_by_text(FIXED)
    note.wait_for(timeout=30_000)
    who = fixed_by(body_text(page))
    if who is None:
        raise RuntimeError("the survey isn't fixed: serve it as the owner decided it")
    run.cast.mark(f"SAM 3.1 surveyed the photo, checked against the LiDAR; {who} decided each")
    centre(note)
    page.wait_for_timeout(5000)


def design(run: Run, brief: str) -> None:
    page = run.page
    box = page.get_by_label("What would you like to build?")
    centre(box)
    run.cast.mark("the owner's brief, in their own words")
    box.click()
    box.press_sequentially(brief, delay=35)
    page.get_by_role("button", name="Design it").click()
    run.cast.mark(
        "Muse Spark looks at the LiDAR, writes Blender, and the evaluator checks each attempt"
    )
    print("design took", until_accepted(page), "s", flush=True)
    page.wait_for_timeout(2000)
    run.cast.mark("accepted: every check measured, each with its rule")
    page.wait_for_timeout(5000)


def stand_in_3d(run: Run) -> None:
    map_view(run, "3D")
    run.cast.mark(
        "the design standing on the site, among the buildings and trees the LiDAR measured"
    )
    run.page.wait_for_timeout(10_000)  # the camera orbits the design
    map_view(run, "2D")


def hero_tab(run: Run, label: str, limit_s: float = 30) -> Locator:
    """Show the hero's ``label`` tab, once it has something to show."""
    hero = run.page.get_by_label("The accepted design")
    tab = hero.get_by_role("tab", name=label)
    tab.wait_for(timeout=limit_s * 1000)
    tab.click()
    run.page.wait_for_timeout(1500)
    return hero


def show_visual(run: Run) -> None:
    """Wait for Muse Image's checked visual, and show it. The take promises one,
    so without it the take fails (its footage is kept apart)."""
    start = time.time()
    try:
        hero = hero_tab(run, "AI visual", VISUAL_LIMIT_S)
    except PlaywrightError as error:
        raise RuntimeError("no checked AI visual was shown") from error
    took = round(time.time() - start)
    try:
        run.page.wait_for_function(VISUAL_LOADED, timeout=30_000)
    except PlaywrightError as error:
        raise RuntimeError("the AI visual didn't load") from error
    run.cast.mark(f"Muse Image's illustration: SAM 3.1 found the house kept its shape ({took} s)")
    centre(hero)
    run.page.wait_for_timeout(6000)


def revise(run: Run, change: str) -> None:
    page = run.page
    instruction = page.get_by_label("Change this design")
    centre(instruction)
    instruction.click()
    instruction.press_sequentially(change, delay=35)
    page.get_by_role("button", name="Revise").click()
    run.cast.mark("a change in plain words: Muse revises, the evaluator checks again (live)")
    wait_for(page, lambda t: any(status in t for status in IN_PROGRESS), 60, status_text)
    print("revision took", until_accepted(page), "s", flush=True)
    page.wait_for_timeout(3000)


def before_and_after(run: Run) -> None:
    hero = hero_tab(run, "Before / after")
    try:
        run.page.wait_for_function(RENDERS_LOADED, timeout=30_000)
    except PlaywrightError as error:
        raise RuntimeError("the before and after renders didn't load") from error
    run.cast.mark("before and after")
    centre(hero)
    run.page.wait_for_timeout(6000)


def show_products(run: Run) -> None:
    """The real prefabs that fit the design on show, drawn where they'd stand."""
    page = run.page
    ask = page.get_by_role("button", name="Which real prefabs fit?")
    centre(ask)
    ask.click()  # the panel asks the API only when this is pressed
    heading = page.get_by_role("heading", name=re.compile(r"real prefabs? fits?"))
    heading.wait_for(timeout=60_000)
    centre(heading)
    run.cast.mark(
        "real prefabs that fit, with their published prices, drawn where each would stand"
    )
    page.wait_for_timeout(7000)


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
    run.cast.mark(f"the {name}, placed and checked against its footprint and every rule")
    map_view(run, "3D")
    page.wait_for_timeout(8000)


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
    open_town(run, args.base_url)
    find_site(run, ADDRESS)
    show_survey(run)
    design(run, args.brief)
    stand_in_3d(run)
    show_visual(run)
    revise(run, args.change)
    if args.screenshot is not None:
        run.page.screenshot(path=args.screenshot, full_page=True)
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
