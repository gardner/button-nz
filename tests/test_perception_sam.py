"""Tests for button_nz.perception.sam: SAM 3.1 masks from the Meta Model API.

``data/sam-tree.txt`` is two records of a real ``sam-3.1`` reply for "tree" on
the demo site's 672 x 688 px aerial.
"""

import base64
import io
import json
from pathlib import Path
from typing import Any

import httpx2  # the HTTP client the openai SDK is built on
import numpy as np
import pytest
from openai import DefaultHttpxClient, OpenAI
from PIL import Image

from button_nz.agent.model import META_BASE_URL
from button_nz.perception.sam import SAM_MODEL, SegmentationError, Segmenter, parse_masks

REPLY = (Path(__file__).parent / "data" / "sam-tree.txt").read_text(encoding="utf-8")
SHAPE = (688, 672)  # the aerial's rows x columns


def test_each_mask_is_placed_on_the_whole_crop_with_its_confidence() -> None:
    first, second = parse_masks(REPLY, "tree", SHAPE)
    assert first.concept == "tree" and first.score == pytest.approx(0.75)
    assert first.pixels.shape == SHAPE and first.pixels.sum() == 457
    rows, cols = np.nonzero(first.pixels)
    assert (rows.min(), rows.max(), cols.min(), cols.max()) == (559, 584, 141, 163)
    assert second.pixels.sum() == 480 and second.score == pytest.approx(0.54, abs=0.01)


def test_a_reply_for_an_image_of_another_size_is_refused() -> None:
    with pytest.raises(SegmentationError, match="672 x 688"):
        parse_masks(REPLY, "tree", (100, 100))


def test_no_match_is_no_masks() -> None:
    assert parse_masks("", "swimming pool", SHAPE) == []  # as the live API replies


@pytest.mark.parametrize("reply", [REPLY[:300], "<0f>", "I can't see any trees."])
def test_a_malformed_reply_is_an_error_not_fewer_masks(reply: str) -> None:
    with pytest.raises(SegmentationError):
        parse_masks(reply, "tree", SHAPE)


def _response(text: str, status: str = "completed") -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": SAM_MODEL,
        "status": status,
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


def _segmenter(response: dict[str, Any]) -> tuple[Segmenter, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/responses")
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=response)

    client = OpenAI(
        base_url=META_BASE_URL,
        api_key="test",
        http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return Segmenter(client), sent


def test_one_concept_is_asked_about_the_image_with_confidences() -> None:
    segmenter, sent = _segmenter(_response(REPLY))
    aerial = np.zeros((*SHAPE, 3), dtype=np.uint8)
    masks = segmenter.masks(aerial, "tree")
    assert len(masks) == 2
    (request,) = sent
    assert request["model"] == "sam-3.1"
    assert request["metadata"] == {"include_confidence": "true"}
    text, image = request["input"][0]["content"]
    assert text == {"type": "input_text", "text": "tree"}
    prefix, data = image["image_url"].split(",", 1)
    assert prefix == "data:image/png;base64"
    sent_image = Image.open(io.BytesIO(base64.b64decode(data)))
    assert sent_image.size == (672, 688)  # lossless, at the crop's own size


def test_an_incomplete_response_is_an_error() -> None:
    segmenter, _ = _segmenter(_response(REPLY, status="incomplete"))
    with pytest.raises(SegmentationError, match="incomplete"):
        segmenter.masks(np.zeros((*SHAPE, 3), dtype=np.uint8), "tree")


def test_a_list_of_concepts_is_refused_before_asking() -> None:
    """SAM 3.1 takes one noun phrase; a list silently matches nothing."""
    segmenter, sent = _segmenter(_response(REPLY))
    with pytest.raises(ValueError, match="one concept"):
        segmenter.masks(np.zeros((*SHAPE, 3), dtype=np.uint8), "tree, shed")
    assert sent == []


def test_the_key_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(KeyError, match="META_API_KEY"):
        Segmenter.from_env()


def test_a_parser_warning_keeps_the_masks() -> None:
    """A field this parser doesn't know is a warning (newer SAM syntax), not an error."""
    newer = REPLY.replace(";h=688;c=", ";h=688;q=1;c=", 1)
    assert len(parse_masks(newer, "tree", SHAPE)) == 2


def test_a_refusal_is_an_error_not_no_match() -> None:
    """A refused request can still be 'completed', with no text: not zero matches."""
    refused = _response("")
    refused["output"][0]["content"] = [{"type": "refusal", "refusal": "I can't help."}]
    segmenter, _ = _segmenter(refused)
    with pytest.raises(SegmentationError, match="refused"):
        segmenter.masks(np.zeros((*SHAPE, 3), dtype=np.uint8), "tree")
