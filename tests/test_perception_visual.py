"""Tests for button_nz.perception.visual: an AI illustration of an accepted
design, shown only if the building in it keeps the design's silhouette.

The Meta Model API is mocked. The image edit returns the very picture it was
sent, or that picture changed (moved, shrunk, blanked), and a stand-in for SAM
3.1 finds the house by its colour, so the check sees exactly what the edit was
given. One test sends SAM's real request; its reply, ``data/sam-tree.txt``, is
two real masks on a 672 x 688 px image.
"""

import base64
import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2  # the HTTP client the openai SDK is built on
import numpy as np
import pytest
from numpy.typing import NDArray
from openai import BadRequestError, DefaultHttpxClient, OpenAI
from PIL import Image

from button_nz.agent.model import META_BASE_URL
from button_nz.perception.features import Mask
from button_nz.perception.sam import SAM_MODEL, SegmentationError, Segmenter
from button_nz.perception.visual import (
    CONTEXT,
    EDITS,
    MIN_IOU,
    VISUAL_MODEL,
    Visual,
    VisualError,
    close_up,
    illustrate,
    illustrate_from_env,
    iou,
    save,
)

TREES = (Path(__file__).parent / "data" / "sam-tree.txt").read_text(encoding="utf-8")
SHAPE = (900, 1200)  # the render's rows x columns
GRASS, HOUSE = (90, 120, 60), (250, 250, 250)
Draw = Callable[[Image.Image], Image.Image | None]  # what Muse Image makes of a picture


def _box(top: int, bottom: int, left: int, right: int) -> NDArray[np.bool_]:
    silhouette = np.zeros(SHAPE, dtype=np.bool_)
    silhouette[top:bottom, left:right] = True
    return silhouette


# 100 x 75 px, a twelfth of the render each way: the close-up three times its
# box is the window (400, 325)-(700, 550), shown four times bigger.
DWELLING = _box(400, 475, 500, 600)
WINDOW = (400, 325, 700, 550)


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _files(tmp_path: Path, silhouette: NDArray[np.bool_]) -> tuple[Path, Path]:
    """The render, grass with the dwelling painted in, and its silhouette."""
    render, mask = tmp_path / "design.png", tmp_path / "dwelling-mask.png"
    pixels = np.empty((*SHAPE, 3), dtype=np.uint8)
    pixels[:] = GRASS
    pixels[silhouette] = HOUSE
    render.write_bytes(_png(Image.fromarray(pixels, "RGB")))
    mask.write_bytes(_png(Image.fromarray(silhouette.astype(np.uint8) * 255, "L")))
    return render, mask


def _sent(content: bytes) -> Image.Image:
    """The PNG in a multipart edit request."""
    start = content.index(b"\x89PNG")
    end = content.index(b"IEND", start) + 8
    with Image.open(io.BytesIO(content[start:end])) as image:
        return image.convert("RGB")


def _house(image: Image.Image) -> NDArray[np.bool_]:
    """The pixels near the dwelling's colour."""
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    return (np.abs(rgb - np.array(HOUSE)) < 40).all(axis=2)


def echo(image: Image.Image) -> Image.Image:
    return image


def moved(image: Image.Image) -> Image.Image:
    """The house moved half its width east, at the close-up's scale."""
    return Image.fromarray(np.roll(np.asarray(image), image.width // 6, axis=1), "RGB")


def halved(image: Image.Image) -> Image.Image:
    """The same picture at half the size: it is checked at the render's."""
    return image.resize((image.width // 2, image.height // 2), Image.Resampling.LANCZOS)


def blank(image: Image.Image) -> Image.Image:
    return Image.new("RGB", image.size, GRASS)


def nothing(image: Image.Image) -> None:
    return None


class ColourSam(Segmenter):
    """SAM 3.1, standing in: the house is whatever is near the dwelling's colour."""

    def masks(self, rgb: NDArray[np.uint8], concept: str) -> list[Mask]:
        assert concept == "house"
        pixels = _house(Image.fromarray(rgb, "RGB"))
        return [Mask(concept, 0.9, pixels)] if pixels.any() else []


def _sam_reply(text: str) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": SAM_MODEL,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }


class Api:
    """The Meta Model API, mocked: what was asked, and what it replies. Each edit
    draws with the next of ``draws``; the last repeats."""

    def __init__(self, *draws: Draw, real_sam: bool = False) -> None:
        self.draws: list[Draw] = list(draws) or [echo]
        self.edits: list[bytes] = []
        self.failing_edits: set[int] = set()  # which edits, counted from 1, are refused
        self.segmentations: list[dict[str, Any]] = []
        self.client = OpenAI(
            base_url=META_BASE_URL,
            api_key="test",
            http_client=DefaultHttpxClient(transport=httpx2.MockTransport(self._handle)),
        )
        self.segmenter = Segmenter(self.client) if real_sam else ColourSam(self.client)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/images/edits"):
            self.edits.append(request.content)
            if len(self.edits) in self.failing_edits:
                return httpx2.Response(400, json={"error": {"message": "refused"}})
            draw = self.draws.pop(0) if len(self.draws) > 1 else self.draws[0]
            drawn = draw(_sent(request.content))
            data = [{"b64_json": base64.b64encode(_png(drawn)).decode()}] if drawn else []
            return httpx2.Response(200, json={"created": 0, "data": data})
        assert request.url.path.endswith("/responses")
        self.segmentations.append(json.loads(request.content))
        return httpx2.Response(200, json=_sam_reply(TREES))

    def illustrate(self, render: Path, mask: Path) -> Visual:
        return illustrate(render, mask, self.client, self.segmenter)


def test_iou_is_overlap_over_union() -> None:
    a = np.zeros((4, 4), dtype=np.bool_)
    b = np.zeros((4, 4), dtype=np.bool_)
    a[0:2, 0:2] = True  # 4 px
    b[1:3, 0:2] = True  # 4 px, 2 shared
    assert iou(a, b) == pytest.approx(2 / 6)
    assert iou(a, a) == 1.0
    assert iou(a, np.zeros_like(a)) == 0.0


def test_the_close_up_is_three_times_the_dwellings_box_around_it() -> None:
    """In the recorded renders the dwelling's box is 50 to 161 px of 1280: Muse
    Image redrew a house that small loosely (#133). The close-up keeps the
    render's shape, so its longer side relative to the render sets the size."""
    assert CONTEXT == 3
    assert close_up(DWELLING) == WINDOW


def test_a_close_up_near_the_edge_moves_inside_the_render() -> None:
    corner = _box(10, 85, 1150, 1190)  # 40 x 75 px, at the top right
    left, top, right, bottom = close_up(corner)
    assert (right, top) == (1200, 0)
    assert (right - left, bottom - top) == (300, 225)  # 3 x 75 px tall, at 4:3


def test_a_big_dwelling_is_illustrated_in_the_whole_render() -> None:
    big = _box(300, 650, 400, 800)  # 400 px of 1200: three times is wider than the render
    assert close_up(big) == (0, 0, 1200, 900)


def test_the_edit_is_sent_the_close_up_at_the_renders_size(tmp_path: Path) -> None:
    api = Api()
    api.illustrate(*_files(tmp_path, DWELLING))
    sent = _sent(api.edits[0])
    assert sent.size == (SHAPE[1], SHAPE[0])
    rows, cols = np.nonzero(_house(sent))
    assert (cols.min(), cols.max() + 1) == pytest.approx((400, 800), abs=2)  # a third of it
    assert (rows.min(), rows.max() + 1) == pytest.approx((300, 600), abs=2)


def test_an_illustration_that_keeps_the_silhouette_is_accepted(tmp_path: Path) -> None:
    """The close-up's silhouette is cut and scaled as the render was: an edit that
    changes nothing overlaps it all but exactly."""
    visual = Api().illustrate(*_files(tmp_path, DWELLING))
    assert visual.accepted and visual.reason is None
    assert visual.iou == pytest.approx(1.0, abs=0.02)
    assert visual.model == VISUAL_MODEL == "muse-image-1.0"
    assert visual.window == WINDOW


def test_what_is_checked_is_what_is_shown(tmp_path: Path) -> None:
    visual = Api(halved).illustrate(*_files(tmp_path, DWELLING))
    assert visual.accepted and visual.png is not None
    with Image.open(io.BytesIO(visual.png)) as shown:
        assert shown.size == (SHAPE[1], SHAPE[0])
        house = _house(shown)
    assert iou(house, _house(_sent_close_up())) > 0.95  # the close-up, not the render


def _sent_close_up() -> Image.Image:
    """The dwelling as the close-up shows it: a third of the picture each way."""
    pixels = np.empty((*SHAPE, 3), dtype=np.uint8)
    pixels[:] = GRASS
    pixels[300:600, 400:800] = HOUSE
    return Image.fromarray(pixels, "RGB")


def test_an_illustration_accepted_first_time_takes_one_edit(tmp_path: Path) -> None:
    api = Api()
    visual = api.illustrate(*_files(tmp_path, DWELLING))
    assert visual.accepted and visual.edits == 1 and len(api.edits) == 1


def test_a_rejected_illustration_gets_a_second_edit(tmp_path: Path) -> None:
    """Muse Image's result varies from edit to edit: of the seven designs whose
    first edit was rejected, the second rescued two (#133). It is checked just
    the same."""
    api = Api(blank, echo)  # no house in the first, the dwelling in the second
    visual = api.illustrate(*_files(tmp_path, DWELLING))
    assert visual.accepted and visual.iou == pytest.approx(1.0, abs=0.02)
    assert visual.edits == EDITS == 2 and len(api.edits) == 2
    assert visual.record()["edits"] == 2


def test_a_failed_second_edit_keeps_the_first_edits_rejection(tmp_path: Path) -> None:
    """The first edit was made and measured: its IoU is the record, not lost."""
    api = Api(moved)
    api.failing_edits = {2}
    visual = api.illustrate(*_files(tmp_path, DWELLING))
    assert not visual.accepted and visual.iou is not None and visual.iou < MIN_IOU
    assert visual.edits == 1  # edits checked
    assert visual.reason is not None and "second edit failed" in visual.reason
    assert visual.window == WINDOW


def test_a_failed_first_edit_is_an_error_as_before(tmp_path: Path) -> None:
    api = Api()
    api.failing_edits = {1}
    with pytest.raises(BadRequestError):
        api.illustrate(*_files(tmp_path, DWELLING))


def test_an_illustration_rejected_every_time_is_not_shown(tmp_path: Path) -> None:
    api = Api(moved)
    visual = api.illustrate(*_files(tmp_path, DWELLING))
    assert not visual.accepted and visual.png is None and visual.edits == EDITS
    assert len(api.edits) == EDITS


def test_the_edit_asks_muse_image_to_keep_the_building(tmp_path: Path) -> None:
    api = Api()
    api.illustrate(*_files(tmp_path, DWELLING))
    (edit,) = api.edits
    assert b'name="model"\r\n\r\nmuse-image-1.0' in edit
    assert b'filename="design.png"' in edit
    for kept in (b"zoom, crop", b"footprint", b"roofline", b"Do not add any new buildings"):
        assert kept in edit


def test_the_edit_is_told_where_the_dwelling_is_in_the_close_up(tmp_path: Path) -> None:
    """Told only to keep it, Muse Image drew the small dwelling far bigger (IoU 0.3);
    told its box in the frame, it kept it (0.94). In the close-up the dwelling
    spans the middle third each way."""
    api = Api()
    api.illustrate(*_files(tmp_path, DWELLING))
    (edit,) = api.edits
    assert b"from 33% to 67% of the image width and from 33% to 67% of its height" in edit


def test_the_prompt_names_no_black_area(tmp_path: Path) -> None:
    """A close-up seldom has sky in it, and the render's sky isn't black."""
    api = Api()
    api.illustrate(*_files(tmp_path, DWELLING))
    assert b"black area" not in api.edits[0]


def test_sam_is_asked_about_the_house_in_the_illustration_at_the_renders_size(
    tmp_path: Path,
) -> None:
    api = Api(real_sam=True)
    with pytest.raises(SegmentationError, match="672 x 688"):  # a canned reply
        api.illustrate(*_files(tmp_path, DWELLING))
    (request,) = api.segmentations
    text, image = request["input"][0]["content"]
    assert text["text"] == "house"
    data = base64.b64decode(image["image_url"].split(",", 1)[1])
    with Image.open(io.BytesIO(data)) as sent:
        assert sent.size == (SHAPE[1], SHAPE[0])


def test_an_illustration_that_moves_the_building_is_rejected(tmp_path: Path) -> None:
    visual = Api(moved).illustrate(*_files(tmp_path, DWELLING))
    assert not visual.accepted and visual.png is None
    assert visual.iou is not None and visual.iou < MIN_IOU
    assert visual.reason is not None and f"{MIN_IOU:.2f}" in visual.reason


def test_no_house_in_the_illustration_is_rejected(tmp_path: Path) -> None:
    visual = Api(blank).illustrate(*_files(tmp_path, DWELLING))
    assert not visual.accepted and visual.iou == 0.0 and visual.png is None
    assert visual.reason is not None and "no house" in visual.reason


def test_a_dwelling_the_camera_cannot_see_is_not_illustrated(tmp_path: Path) -> None:
    api = Api()
    visual = api.illustrate(*_files(tmp_path, np.zeros(SHAPE, dtype=np.bool_)))
    assert not visual.accepted and visual.iou is None and visual.window is None
    assert visual.reason is not None and "isn't visible" in visual.reason
    assert api.edits == [] and api.segmentations == []  # nothing to keep: nothing asked


def test_a_silhouette_of_another_size_is_an_error(tmp_path: Path) -> None:
    render, mask = _files(tmp_path, DWELLING)
    mask.write_bytes(_png(Image.new("L", (10, 10))))
    with pytest.raises(VisualError, match="10 x 10"):
        Api().illustrate(render, mask)


def test_an_edit_without_an_image_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(VisualError, match="no image"):
        Api(nothing).illustrate(*_files(tmp_path, DWELLING))


def test_an_accepted_visual_is_saved_with_its_record(tmp_path: Path) -> None:
    visual = Visual(VISUAL_MODEL, True, 0.82, None, b"\x89PNG visual", 1, WINDOW)
    save(visual, tmp_path)
    assert (tmp_path / "visual.png").read_bytes() == b"\x89PNG visual"
    record = json.loads((tmp_path / "visual.json").read_text(encoding="utf-8"))
    assert record == {
        "model": "muse-image-1.0",
        "accepted": True,
        "iou": 0.82,
        "min_iou": MIN_IOU,
        "reason": None,
        "edits": 1,
        "window": [400, 325, 700, 550],  # the render's pixels it shows
    }


def test_a_rejected_visual_is_recorded_but_not_saved(tmp_path: Path) -> None:
    (tmp_path / "visual.png").write_bytes(b"stale")
    save(Visual(VISUAL_MODEL, False, 0.31, "It moved.", None, 2), tmp_path)
    assert not (tmp_path / "visual.png").exists()
    record = json.loads((tmp_path / "visual.json").read_text(encoding="utf-8"))
    assert record["accepted"] is False and record["reason"] == "It moved."
    assert record["window"] is None


def test_the_key_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(KeyError, match="META_API_KEY"):
        illustrate_from_env(*_files(tmp_path, DWELLING))


def test_only_an_accepted_visual_carries_an_image() -> None:
    with pytest.raises(ValueError, match="accepted"):
        Visual(VISUAL_MODEL, False, 0.2, "It moved.", b"\x89PNG", 1)
    with pytest.raises(ValueError, match="accepted"):
        Visual(VISUAL_MODEL, True, 0.9, None, None, 1)
