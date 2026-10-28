"""Tests for button_nz.perception.visual: an AI illustration of an accepted
design, shown only if the building in it keeps the design's silhouette.

Both Meta Model API calls are mocked: the image edit returns a PNG, and SAM
3.1 replies with ``data/sam-tree.txt``, two real masks on a 672 x 688 px image,
standing in for the masks of houses in the illustration.
"""

import base64
import io
import json
from pathlib import Path
from typing import Any

import httpx2  # the HTTP client the openai SDK is built on
import numpy as np
import pytest
from numpy.typing import NDArray
from openai import DefaultHttpxClient, OpenAI
from PIL import Image

from button_nz.agent.model import META_BASE_URL
from button_nz.perception.sam import SAM_MODEL, Segmenter, parse_masks
from button_nz.perception.visual import (
    MIN_IOU,
    VISUAL_MODEL,
    Visual,
    VisualError,
    illustrate,
    illustrate_from_env,
    iou,
    save,
)

TREES = (Path(__file__).parent / "data" / "sam-tree.txt").read_text(encoding="utf-8")
SHAPE = (688, 672)  # rows x columns, as SAM saw them
FIRST, SECOND = (m.pixels for m in parse_masks(TREES, "house", SHAPE))


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _files(tmp_path: Path, silhouette: NDArray[np.bool_]) -> tuple[Path, Path]:
    render, mask = tmp_path / "design.png", tmp_path / "dwelling-mask.png"
    render.write_bytes(_png(Image.new("RGB", (SHAPE[1], SHAPE[0]), (90, 120, 60))))
    mask.write_bytes(_png(Image.fromarray(silhouette.astype(np.uint8) * 255, "L")))
    return render, mask


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
    """The Meta Model API, mocked: what was asked, and what it replies."""

    def __init__(self, sam_text: str = TREES, edit: dict[str, Any] | None = None) -> None:
        # Half the render's size: the illustration is checked at the render's.
        illustration = Image.new("RGB", (SHAPE[1] // 2, SHAPE[0] // 2), (200, 180, 150))
        b64 = base64.b64encode(_png(illustration)).decode("ascii")
        self.edit = edit if edit is not None else {"created": 0, "data": [{"b64_json": b64}]}
        self.sam_text = sam_text
        self.edits: list[bytes] = []
        self.segmentations: list[dict[str, Any]] = []
        client = OpenAI(
            base_url=META_BASE_URL,
            api_key="test",
            http_client=DefaultHttpxClient(transport=httpx2.MockTransport(self._handle)),
        )
        self.client, self.segmenter = client, Segmenter(client)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/images/edits"):
            self.edits.append(request.content)
            return httpx2.Response(200, json=self.edit)
        assert request.url.path.endswith("/responses")
        self.segmentations.append(json.loads(request.content))
        return httpx2.Response(200, json=_sam_reply(self.sam_text))

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


def test_an_illustration_that_keeps_the_silhouette_is_accepted(tmp_path: Path) -> None:
    api = Api()
    visual = api.illustrate(*_files(tmp_path, FIRST))
    assert visual.accepted and visual.reason is None
    assert visual.iou == pytest.approx(1.0)
    assert visual.model == VISUAL_MODEL == "muse-image-1.0"
    assert visual.png is not None
    with Image.open(io.BytesIO(visual.png)) as shown:
        assert shown.size == (SHAPE[1], SHAPE[0])  # what was checked is what is shown


def test_the_edit_asks_muse_image_to_keep_the_building(tmp_path: Path) -> None:
    api = Api()
    api.illustrate(*_files(tmp_path, FIRST))
    (edit,) = api.edits
    assert b'name="model"\r\n\r\nmuse-image-1.0' in edit
    assert b'filename="design.png"' in edit
    for kept in (b"camera", b"footprint", b"roof", b"Do not add any new buildings"):
        assert kept in edit


def test_sam_is_asked_about_the_house_in_the_illustration_at_the_renders_size(
    tmp_path: Path,
) -> None:
    api = Api()
    api.illustrate(*_files(tmp_path, FIRST))
    (request,) = api.segmentations
    text, image = request["input"][0]["content"]
    assert text["text"] == "house"
    data = base64.b64decode(image["image_url"].split(",", 1)[1])
    with Image.open(io.BytesIO(data)) as sent:
        assert sent.size == (SHAPE[1], SHAPE[0])


def test_the_best_matching_mask_is_the_one_compared(tmp_path: Path) -> None:
    """Other buildings in the illustration don't count against it."""
    visual = Api().illustrate(*_files(tmp_path, SECOND))
    assert visual.accepted and visual.iou == pytest.approx(1.0)


def test_an_illustration_that_moves_or_resizes_the_building_is_rejected(tmp_path: Path) -> None:
    shifted = np.roll(FIRST, 12, axis=1)  # 12 px east: about half its 23 px width
    visual = Api().illustrate(*_files(tmp_path, shifted))
    assert not visual.accepted and visual.png is None
    assert visual.iou is not None and visual.iou < MIN_IOU
    assert visual.reason is not None and f"{MIN_IOU:.2f}" in visual.reason


def test_no_house_in_the_illustration_is_rejected(tmp_path: Path) -> None:
    visual = Api(sam_text="").illustrate(*_files(tmp_path, FIRST))
    assert not visual.accepted and visual.iou == 0.0 and visual.png is None
    assert visual.reason is not None and "no house" in visual.reason


def test_a_dwelling_the_camera_cannot_see_is_not_illustrated(tmp_path: Path) -> None:
    api = Api()
    visual = api.illustrate(*_files(tmp_path, np.zeros(SHAPE, dtype=np.bool_)))
    assert not visual.accepted and visual.iou is None
    assert visual.reason is not None and "isn't visible" in visual.reason
    assert api.edits == [] and api.segmentations == []  # nothing to keep: nothing asked


def test_a_silhouette_of_another_size_is_an_error(tmp_path: Path) -> None:
    render, mask = _files(tmp_path, FIRST)
    mask.write_bytes(_png(Image.new("L", (10, 10))))
    with pytest.raises(VisualError, match="10 x 10"):
        Api().illustrate(render, mask)


def test_an_edit_without_an_image_is_an_error(tmp_path: Path) -> None:
    api = Api(edit={"created": 0, "data": [{"url": "https://example.com/x.png"}]})
    with pytest.raises(VisualError, match="no image"):
        api.illustrate(*_files(tmp_path, FIRST))


def test_an_accepted_visual_is_saved_with_its_record(tmp_path: Path) -> None:
    visual = Visual(VISUAL_MODEL, True, 0.82, None, b"\x89PNG visual")
    save(visual, tmp_path)
    assert (tmp_path / "visual.png").read_bytes() == b"\x89PNG visual"
    record = json.loads((tmp_path / "visual.json").read_text(encoding="utf-8"))
    assert record == {
        "model": "muse-image-1.0",
        "accepted": True,
        "iou": 0.82,
        "min_iou": MIN_IOU,
        "reason": None,
    }


def test_a_rejected_visual_is_recorded_but_not_saved(tmp_path: Path) -> None:
    (tmp_path / "visual.png").write_bytes(b"stale")
    save(Visual(VISUAL_MODEL, False, 0.31, "It moved.", None), tmp_path)
    assert not (tmp_path / "visual.png").exists()
    record = json.loads((tmp_path / "visual.json").read_text(encoding="utf-8"))
    assert record["accepted"] is False and record["reason"] == "It moved."


def test_the_key_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(KeyError, match="META_API_KEY"):
        illustrate_from_env(*_files(tmp_path, FIRST))


def test_only_an_accepted_visual_carries_an_image() -> None:
    with pytest.raises(ValueError, match="accepted"):
        Visual(VISUAL_MODEL, False, 0.2, "It moved.", b"\x89PNG")
    with pytest.raises(ValueError, match="accepted"):
        Visual(VISUAL_MODEL, True, 0.9, None, None)
