"""Masks of a concept on the site's aerial from SAM 3.1 on the Meta Model API.

One request asks about one concept, a short noun phrase ("tree", "shed"): SAM
3.1 matches lists ("tree, shed") with nothing. The reply is SAM's own record
grammar, decoded by Meta's ``meta_sam_parser``; each record is a box and a mask
of the bounding box, which is placed back on the whole crop for
``features.features`` to georeference. A reply that doesn't parse, or a
refusal, is an error, never fewer masks; no match at all is an empty reply.
"""

import base64
import io
import os
import re
from dataclasses import dataclass
from typing import Any, cast

import meta_sam_parser as sam
import numpy as np
from numpy.typing import NDArray
from openai import OpenAI
from PIL import Image

from button_nz.agent.model import META_BASE_URL
from button_nz.perception.features import Mask

__all__ = ["SAM_MODEL", "SegmentationError", "Segmenter", "parse_masks"]

SAM_MODEL = "sam-3.1"
SIZE = re.compile(r"<\|box;[^|]*?\bw=(\d+);h=(\d+)")  # the image size SAM saw


class SegmentationError(RuntimeError):
    """SAM's reply couldn't be read, or isn't about the image that was sent."""


@dataclass(frozen=True)
class Segmenter:
    client: OpenAI
    model: str = SAM_MODEL

    @classmethod
    def from_env(cls) -> Segmenter:
        """A client for the Meta Model API using the ``META_API_KEY`` key."""
        key = os.environ.get("META_API_KEY")
        if not key:
            raise KeyError("META_API_KEY is not set: get a Meta Model API key")
        return cls(OpenAI(base_url=META_BASE_URL, api_key=key))

    def masks(self, rgb: NDArray[np.uint8], concept: str) -> list[Mask]:
        """Every match for ``concept`` on ``rgb`` (rows x columns x RGB)."""
        if any(separator in concept for separator in ",;+"):
            raise ValueError(f"ask SAM about one concept at a time, not {concept!r}")
        response = self.client.responses.create(
            model=self.model,
            input=cast(
                "Any",
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": concept},
                            {"type": "input_image", "image_url": _data_url(rgb)},
                        ],
                    }
                ],
            ),
            metadata={"include_confidence": "true"},
        )
        if response.status != "completed":
            raise SegmentationError(f"SAM's reply for {concept!r} is {response.status}")
        refusals = [
            part.refusal
            for item in response.output
            if item.type == "message"
            for part in item.content
            if part.type == "refusal"
        ]
        if refusals:  # a refusal is "completed" with no text: not zero matches
            raise SegmentationError(f"SAM refused {concept!r}: {refusals[0]}")
        return parse_masks(response.output_text, concept, (rgb.shape[0], rgb.shape[1]))


def parse_masks(text: str, concept: str, shape: tuple[int, int]) -> list[Mask]:
    """The masks in SAM's reply ``text`` about an image of ``shape`` (rows, columns)."""
    rows, cols = shape
    sizes = {(int(w), int(h)) for w, h in SIZE.findall(text)}
    if sizes - {(cols, rows)}:
        seen = ", ".join(f"{w} x {h}" for w, h in sorted(sizes))
        raise SegmentationError(f"SAM saw a {seen} px image, not {cols} x {rows}")
    parser = sam.image_segmentation_format().create_parser()
    parser.push(text)
    result = parser.finish(sam.CompletedOutcome()).result
    # Warnings (e.g. a field this parser doesn't know yet) leave the records intact.
    errors = [d for d in result.diagnostics if d.severity == "error"]
    if errors:
        raise SegmentationError(f"SAM's reply didn't parse: {errors[0].message}")
    masks: list[Mask] = []
    for record in result.records:
        if record.kind == "text":
            raise SegmentationError(f"SAM replied with text, not masks: {record.text[:80]!r}")
        if record.kind == "mask":
            masks.append(_placed(record, concept, shape))
    return masks


def _placed(record: sam.SegmentationMaskRecord, concept: str, shape: tuple[int, int]) -> Mask:
    """``record``'s mask, which covers its bounding box, on the whole image."""
    if record.confidence is None:
        raise SegmentationError("SAM gave a mask without the confidence asked for")
    mask, bounds = record.mask, record.bounds
    raster = np.frombuffer(sam.decode_mask_to_raster(mask), dtype=np.uint8)
    pixels = np.zeros(shape, dtype=np.bool_)
    box = pixels[int(bounds.top) : int(bounds.bottom), int(bounds.left) : int(bounds.right)]
    if box.shape != (mask.height, mask.width):
        raise SegmentationError(f"a {concept} mask runs off the {shape[1]} x {shape[0]} image")
    box[:] = raster.reshape(mask.height, mask.width) > 0
    return Mask(concept, record.confidence, pixels)


def _data_url(rgb: NDArray[np.uint8]) -> str:
    """``rgb`` as a lossless PNG data URL, so SAM sees exactly the crop's pixels."""
    buffer = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
