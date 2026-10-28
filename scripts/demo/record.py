"""Record the live demo run in a headless browser.

Confirm the survey, enter a brief, design, wait for the AI visual, view the
design in 3D, revise it in plain words, and show before and after. Everything
is live: the design and the revision call the paid model APIs. Each phase is
marked, so ``cut.py`` can caption it and speed up the waits.
"""

import argparse
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

from screencast import FFMPEG, Screencast, find_chromium

BRIEF = (
    "A two-bedroom dwelling of about 60 square metres that gets the afternoon sun"
    " and keeps the trees."
)
CHANGE = "Move it as close to the street as the rules allow, keeping the trees."
# The owner's answer for each feature SAM 3.1 found on the demo site.
CHOICES = {
    "#1 shed": "Existing building",
    "#2 shed": "Existing building",
    "#3 tree": "Keep clear",
    "#4 tree": "Keep clear",
    "#5 tree": "Keep clear",
}
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


def wait_for(page: Page, done: Callable[[str], bool], limit_s: float) -> int:
    """Poll the page's text until ``done``; the seconds it took."""
    start = time.time()
    while time.time() - start < limit_s:
        if done(page.inner_text("body")):
            return round(time.time() - start)
        page.wait_for_timeout(3000)
    raise TimeoutError(f"the page didn't finish within {limit_s} s")


def open_site(run: Run, base_url: str) -> None:
    run.page.goto(base_url, wait_until="networkidle")
    run.cast.mark("the site: title, parcels and the aerial")
    run.page.wait_for_timeout(4000)
    run.page.mouse.wheel(0, 900)
    run.page.wait_for_timeout(1500)


def confirm_survey(run: Run) -> None:
    page = run.page
    run.cast.mark("SAM 3.1 survey: the owner confirms what is there")
    for name, choice in CHOICES.items():
        item = page.locator("li, article, section > div").filter(has_text=name).last
        item.scroll_into_view_if_needed()
        item.get_by_role("button", name=choice).click()
        expect(item.get_by_role("button", name=choice)).to_have_attribute("aria-pressed", "true")
        page.wait_for_timeout(900)
    box = page.get_by_label("Every building on the site is listed")
    box.scroll_into_view_if_needed()
    box.click()
    expect(box).to_be_checked(timeout=10000)
    page.wait_for_timeout(1500)


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
    took = wait_for(
        page, lambda t: "Change this design" in t or "No attempt passed" in t, DESIGN_LIMIT_S
    )
    print("design took", took, "s", flush=True)
    page.wait_for_timeout(2000)
    run.cast.mark("the accepted design")


def show_visual(run: Run) -> None:
    """Wait for Muse Image's checked, labelled visual, and show it; go on without one."""
    try:
        took = wait_for(run.page, lambda t: "AI-illustrated" in t, VISUAL_LIMIT_S)
    except TimeoutError:
        print("no AI visual shown", flush=True)
        return
    run.cast.mark(f"the AI visual (Muse Image, silhouette checked by SAM 3.1; {took} s later)")
    run.page.get_by_text("AI-illustrated", exact=False).last.scroll_into_view_if_needed()
    run.page.wait_for_timeout(5000)


def view_3d(run: Run) -> None:
    run.page.get_by_role("button", name="View in 3D").last.click()
    run.cast.mark("the 3D model")
    run.page.wait_for_timeout(6000)


def revised(text: str) -> bool:
    return "After" in text and "running" not in text and "queued" not in text


def revise(run: Run, change: str) -> None:
    page = run.page
    instruction = page.get_by_label("Change this design")
    instruction.scroll_into_view_if_needed()
    instruction.click()
    instruction.press_sequentially(change, delay=35)
    page.get_by_role("button", name="Revise").click()
    run.cast.mark("revising in plain words (live)")
    page.wait_for_timeout(3000)
    print("revision took", wait_for(page, revised, DESIGN_LIMIT_S), "s", flush=True)
    page.wait_for_timeout(3000)


def before_and_after(run: Run) -> None:
    run.cast.mark("before and after")
    run.page.get_by_text("Before", exact=False).first.scroll_into_view_if_needed()
    run.page.wait_for_timeout(6000)


def record(args: Options) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=args.chromium, args=["--use-gl=angle", "--use-angle=swiftshader"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        run = Run(page, Screencast(context, page, ffmpeg=args.ffmpeg))
        open_site(run, args.base_url)
        confirm_survey(run)
        design(run, args.brief)
        show_visual(run)
        view_3d(run)
        revise(run, args.change)
        if args.screenshot is not None:
            page.screenshot(path=args.screenshot, full_page=True)
        show_visual(run)
        before_and_after(run)
        print(page.inner_text("body")[-3500:])
        run.cast.encode(args.out, fps=args.fps)
        print(len(run.cast.frames), "frames")
        browser.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Record the live demo run.")
    parser.add_argument("out", type=Path, help="the raw recording, a .webm")
    parser.add_argument("--base-url", default="http://localhost:3100/")
    parser.add_argument("--brief", default=BRIEF)
    parser.add_argument("--change", default=CHANGE, help="the revision, in plain words")
    parser.add_argument("--chromium", type=Path, help="default: Playwright's headless shell")
    parser.add_argument("--ffmpeg", type=Path, default=FFMPEG)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--screenshot", type=Path, help="a full-page shot after the revision")
    args = parser.parse_args(argv)
    chromium: Path = args.chromium or find_chromium()
    record(
        Options(
            out=args.out,
            base_url=args.base_url,
            brief=args.brief,
            change=args.change,
            chromium=chromium,
            ffmpeg=args.ffmpeg,
            fps=args.fps,
            screenshot=args.screenshot,
        )
    )


if __name__ == "__main__":
    main()
