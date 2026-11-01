"""An AI illustration of an accepted design, made with Muse Image on the Meta
Model API, and shown only if the building in it is still the design.

The edit starts from the trusted render, ``design.png``, and asks for a
photograph of the same scene. Image models move, shrink and invent things, so
the result is checked before anyone sees it: SAM 3.1 finds the houses in the
illustration, resized to the render's size, and the one that best overlaps
the Dwelling's silhouette from the render camera (``dwelling-mask.png``, from
the trusted pass) must overlap it with an IoU of at least ``MIN_IOU``. A
rejected edit is made again, up to ``EDITS`` in all, each checked the same way.
Even then it is an illustration, not the design: show it labelled AI-illustrated.

These calls run in the host process, never in the Blender sandbox, which has
no network and no keys.
"""

import base64
import io
import json
import math
import os
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from openai import APIError, OpenAI
from PIL import Image

from button_nz.agent.model import META_BASE_URL
from button_nz.perception.sam import SegmentationError, Segmenter

__all__ = [
    "EDITS",
    "MIN_IOU",
    "VISUAL_MODEL",
    "Visual",
    "VisualError",
    "illustrate",
    "illustrate_from_env",
    "iou",
    "save",
]

LANCZOS = Image.Resampling.LANCZOS
VISUAL_MODEL = "muse-image-1.0"
CONCEPT = "house"  # what SAM 3.1 is asked to find in the illustration
# IoU is overlap over union. 0.6 forgives an outline a few pixels off all round
# (SAM's edges; eaves, a porch or planting the illustration adds) but not a
# building moved or resized enough to mislead: the same outline shifted a quarter
# of its width, or shrunk to 77% each way (60% of its area), scores 0.6. The
# feasibility test's failure, a cottage drawn as a shed, falls below it. A first
# setting: tune it on live results.
MIN_IOU = 0.6
# Muse Image's result varies from edit to edit, so a rejected edit is made once
# more. Measured on 12 recorded designs (#133, docs/results): the second edit
# rescued 2 of the 7 it was made for (5 to 7 of 12). Failures mostly repeat for
# the same design, so a third would buy little; it costs an edit (about 25 s) and
# a SAM call, only when the first is rejected.
EDITS = 2
EDIT_TIMEOUT_S = 180.0  # an edit took about 24 s in the feasibility test
VISUAL_PNG, VISUAL_JSON = "visual.png", "visual.json"
# Told only to keep the dwelling, Muse Image reframed the shot and drew the small
# dwelling far bigger (IoU 0.17, then 0.32 asked not to reframe); told its box in
# the frame, it kept it (0.94, then 0.93). One live run each, on a 32 m² design
# 133 x 116 px in the 1280 x 960 render. The box comes from the silhouette.
PROMPT = (
    "Edit this image in place. It is a 3D massing render seen from a drone; make it look "
    "like a real drone photograph of the same place without changing the composition at "
    "all. Do not zoom, crop, pan, rotate or reframe: every object must stay at exactly the "
    "same position and size in the frame, including the black area at the top, which "
    "becomes distant landscape and sky. The plain light-coloured building is a new small "
    "dwelling. It must stay exactly as big as it is in this picture: it fills only the box "
    "from {left}% to {right}% of the image width and from {top}% to {bottom}% of its "
    "height. Keep exactly its position, footprint, size, proportions, roofline and gable "
    "direction, and give it realistic cladding and windows within that same outline. The "
    "orange blocks are trees, hedges and existing structures measured by LiDAR: replace "
    "them with what they most resemble, the same size and in the same places. The green "
    "ground is a grassed New Zealand section; the thin red lines are property boundaries "
    "and may be left out. Do not add any new buildings."
)
RETRY_FAILED = "A second edit failed: {error}"
NOT_VISIBLE = "The dwelling isn't visible from the render camera, so there is nothing to keep."
NO_HOUSE = "SAM 3.1 found no house in the illustration."
MOVED = (
    "The building in the illustration overlaps the design's silhouette with IoU {iou:.2f}, "
    "under {min:.2f}: it was moved, resized or reshaped."
)


class VisualError(RuntimeError):
    """The illustration couldn't be made or checked."""


@dataclass(frozen=True)
class Visual:
    model: str
    accepted: bool
    iou: float | None  # the best IoU of a house in it with the silhouette; None if unchecked
    reason: str | None  # why it isn't shown
    png: bytes | None  # the illustration at the render's size: accepted ones only
    edits: int  # how many edits were made and checked: the last is the one recorded here

    def __post_init__(self) -> None:
        if self.accepted != (self.png is not None):
            raise ValueError("an illustration is kept if, and only if, it is accepted")

    @classmethod
    def failed(cls, reason: str) -> Visual:
        return cls(VISUAL_MODEL, False, None, reason, None, 0)

    def record(self) -> dict[str, object]:
        return {
            "model": self.model,
            "accepted": self.accepted,
            "iou": self.iou,
            "min_iou": MIN_IOU,
            "reason": self.reason,
            "edits": self.edits,
        }


def illustrate(
    render_png: Path,
    mask_png: Path,
    image_client: OpenAI,
    segmenter: Segmenter,
    model: str = VISUAL_MODEL,
) -> Visual:
    """Illustrate the render and check the building in it against the silhouette,
    up to ``EDITS`` times: the first illustration that passes, or the last rejection."""
    with Image.open(render_png) as render:
        size = render.size
    silhouette = _silhouette(mask_png, size)
    if not silhouette.any():
        return Visual(model, False, None, NOT_VISIBLE, None, 0)
    prompt = _prompt(silhouette)
    visual = Visual.failed(NO_HOUSE)  # replaced by the first edit's check
    for edits in range(1, EDITS + 1):
        try:
            illustration = _edit(render_png, prompt, image_client, model)
            visual = _check(illustration.resize(size, LANCZOS), silhouette, segmenter, model, edits)
        except (APIError, VisualError, SegmentationError) as error:
            if edits == 1:  # nothing measured yet: the failure is the record
                raise
            return replace(visual, reason=f"{visual.reason} {RETRY_FAILED.format(error=error)}")
        if visual.accepted:
            break
    return visual


def _check(
    illustration: Image.Image,
    silhouette: NDArray[np.bool_],
    segmenter: Segmenter,
    model: str,
    edits: int,
) -> Visual:
    """Whether a house SAM finds in ``illustration`` overlaps ``silhouette`` enough."""
    masks = segmenter.masks(np.asarray(illustration), CONCEPT)
    if not masks:
        return Visual(model, False, 0.0, NO_HOUSE, None, edits)
    best = max(iou(mask.pixels, silhouette) for mask in masks)
    if best < MIN_IOU:
        return Visual(model, False, best, MOVED.format(iou=best, min=MIN_IOU), None, edits)
    return Visual(model, True, best, None, _png(illustration), edits)


def illustrate_from_env(render_png: Path, mask_png: Path) -> Visual:
    """``illustrate`` with a Meta Model API client using the ``META_API_KEY`` key."""
    key = os.environ.get("META_API_KEY")
    if not key:
        raise KeyError("META_API_KEY is not set: get a Meta Model API key")
    client = visual_client(key)
    return illustrate(render_png, mask_png, client, Segmenter(client))


def visual_client(key: str) -> OpenAI:
    """A Meta Model API client for the visual: one try each, since a retried slow
    edit would wait, and be billed, again."""
    return OpenAI(base_url=META_BASE_URL, api_key=key, timeout=EDIT_TIMEOUT_S, max_retries=0)


def iou(a: NDArray[np.bool_], b: NDArray[np.bool_]) -> float:
    """Intersection over union of two masks of the same shape; 0 if both are empty."""
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def save(visual: Visual, directory: Path) -> None:
    """Write ``visual.json``, and ``visual.png`` only if the visual was accepted."""
    png = directory / VISUAL_PNG
    png.unlink(missing_ok=True)
    if visual.png is not None:
        _write(png, visual.png)
    _write(directory / VISUAL_JSON, json.dumps(visual.record(), indent=2).encode())


def _silhouette(mask_png: Path, size: tuple[int, int]) -> NDArray[np.bool_]:
    with Image.open(mask_png) as mask:
        if mask.size != size:
            raise VisualError(
                f"the silhouette is {mask.size[0]} x {mask.size[1]} px, "
                f"the render {size[0]} x {size[1]}"
            )
        return np.asarray(mask.convert("L")) > 127


def _prompt(silhouette: NDArray[np.bool_]) -> str:
    """``PROMPT`` with the silhouette's bounding box, in whole percent of the
    image, rounded outwards."""
    rows, cols = np.nonzero(silhouette)
    height, width = int(silhouette.shape[0]), int(silhouette.shape[1])
    top, bottom = int(rows.min()), int(rows.max()) + 1
    left, right = int(cols.min()), int(cols.max()) + 1
    return PROMPT.format(
        left=math.floor(100 * left / width),
        right=math.ceil(100 * right / width),
        top=math.floor(100 * top / height),
        bottom=math.ceil(100 * bottom / height),
    )


def _edit(render_png: Path, prompt: str, client: OpenAI, model: str) -> Image.Image:
    response = client.images.edit(
        model=model,
        image=("design.png", render_png.read_bytes(), "image/png"),
        prompt=prompt,
    )
    data = response.data or []
    encoded = data[0].b64_json if data else None
    if not encoded:
        raise VisualError(f"{model} returned no image")
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
        return image.convert("RGB")


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _write(path: Path, data: bytes) -> None:
    """Whole or not at all: the API may be serving the directory meanwhile."""
    partial = path.with_name(f"{path.name}.partial")
    partial.write_bytes(data)
    partial.replace(path)
