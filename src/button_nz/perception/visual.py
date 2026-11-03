"""An AI illustration of an accepted design, made with Muse Image on the Meta
Model API, and shown only if the building in it is still the design.

The edit starts from a close-up of the trusted render, ``design.png``: a
window around the dwelling, ``CONTEXT`` times its box, scaled up to the
render's size. It asks for a photograph of the same scene. Image models move,
shrink and invent things, so the result is checked before anyone sees it: SAM
3.1 finds the houses in the illustration, resized to the render's size, and
one of them must overlap the Dwelling from the render camera, cut and scaled
as the render was, with an IoU of at least ``MIN_IOU``: either its visible
silhouette (``dwelling-mask.png``, from the trusted pass), or its whole outline
(``dwelling-outline.png``, the same with nothing in front of it). Muse Image
redraws what stands in front of the house, so it may hide what the render hid or
show the whole house; either way the house must be where, and as big as, the
design is. The close-up is what
is checked and what is shown: nothing is pasted back into a wider picture. A
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
    "CONTEXT",
    "EDITS",
    "MIN_IOU",
    "VISUAL_MODEL",
    "Visual",
    "VisualError",
    "close_up",
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
# In the 12 recorded renders the dwelling's box is 50 to 161 px of 1280 (0.25% to
# 0.9% of the picture), and Muse Image redrew it loosely: bigger, or a little off
# (#133). The close-up is this many times the box, so the dwelling spans about a
# third of it and the section around it stays in view. Measured on those 12
# (docs/results): 10 passed, all on the first edit (IoU 0.83-0.98), against 8
# of the whole render in a run just before (6 on the first edit).
CONTEXT = 3
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
    "same position and size in the frame. The plain light-coloured building is a new small "
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
    "and its whole outline with {outline:.2f}, both under {min:.2f}: it was moved, resized "
    "or reshaped."
)
NOT_INSIDE = "The dwelling's silhouette isn't inside its whole outline: they aren't of one render."


Box = tuple[int, int, int, int]  # left, top, right, bottom, in pixels


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
    window: Box | None = None  # the render's pixels illustrated; None if none were
    outline_iou: float | None = None  # as ``iou``, with the dwelling's whole outline

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
            "window": None if self.window is None else list(self.window),
            "outline_iou": self.outline_iou,
        }


@dataclass(frozen=True)
class Dwelling:
    """The dwelling in the close-up: what of it shows, and its whole outline."""

    silhouette: NDArray[np.bool_]
    outline: NDArray[np.bool_]


def illustrate(
    render_png: Path,
    mask_png: Path,
    outline_png: Path,
    image_client: OpenAI,
    segmenter: Segmenter,
    model: str = VISUAL_MODEL,
) -> Visual:
    """Illustrate a close-up of the render and check the building in it against
    the silhouette and the whole outline, up to ``EDITS`` times: the first
    illustration that passes, or the last rejection."""
    with Image.open(render_png) as render:
        size = render.size
        silhouette = _silhouette(mask_png, size)
        outline = _silhouette(outline_png, size)
        if (silhouette & ~outline).any():
            raise VisualError(NOT_INSIDE)
        if not silhouette.any():
            return Visual(model, False, None, NOT_VISIBLE, None, 0)
        window = close_up(silhouette)
        scene = _png(render.convert("RGB").crop(window).resize(size, LANCZOS))
    dwelling = Dwelling(_scaled(silhouette, window, size), _scaled(outline, window, size))
    visual = _edits(scene, dwelling, image_client, segmenter, model)
    return replace(visual, window=window)


def close_up(silhouette: NDArray[np.bool_]) -> Box:
    """The window of the render to illustrate: the render's shape, ``CONTEXT``
    times the dwelling's box (on whichever side is longer relative to the
    render), centred on it and moved inside the render. The whole render if the
    window would be as big."""
    rows, cols = np.nonzero(silhouette)
    height, width = int(silhouette.shape[0]), int(silhouette.shape[1])
    box_width = int(cols.max()) + 1 - int(cols.min())
    box_height = int(rows.max()) + 1 - int(rows.min())
    scale = min(1.0, CONTEXT * max(box_width / width, box_height / height))
    w, h = round(width * scale), round(height * scale)
    middle_x = (int(cols.min()) + int(cols.max()) + 1) / 2
    middle_y = (int(rows.min()) + int(rows.max()) + 1) / 2
    left = min(max(round(middle_x - w / 2), 0), width - w)
    top = min(max(round(middle_y - h / 2), 0), height - h)
    return (left, top, left + w, top + h)


def _edits(
    scene: bytes,
    dwelling: Dwelling,
    image_client: OpenAI,
    segmenter: Segmenter,
    model: str,
) -> Visual:
    """Up to ``EDITS`` illustrations of ``scene``, each checked against
    ``dwelling``, of the same size."""
    size = (int(dwelling.silhouette.shape[1]), int(dwelling.silhouette.shape[0]))
    prompt = _prompt(dwelling.silhouette)
    visual = Visual.failed(NO_HOUSE)  # replaced by the first edit's check
    for edits in range(1, EDITS + 1):
        try:
            illustration = _edit(scene, prompt, image_client, model)
            visual = _check(illustration.resize(size, LANCZOS), dwelling, segmenter, model, edits)
        except (APIError, VisualError, SegmentationError) as error:
            if edits == 1:  # nothing measured yet: the failure is the record
                raise
            return replace(visual, reason=f"{visual.reason} {RETRY_FAILED.format(error=error)}")
        if visual.accepted:
            break
    return visual


def _check(
    illustration: Image.Image,
    dwelling: Dwelling,
    segmenter: Segmenter,
    model: str,
    edits: int,
) -> Visual:
    """Whether a house SAM finds in ``illustration`` overlaps the dwelling's
    silhouette, or its whole outline, enough."""
    masks = segmenter.masks(np.asarray(illustration), CONCEPT)
    if not masks:
        return Visual(model, False, 0.0, NO_HOUSE, None, edits, outline_iou=0.0)
    shown = max(iou(mask.pixels, dwelling.silhouette) for mask in masks)
    whole = max(iou(mask.pixels, dwelling.outline) for mask in masks)
    if max(shown, whole) < MIN_IOU:
        reason = MOVED.format(iou=shown, outline=whole, min=MIN_IOU)
        return Visual(model, False, shown, reason, None, edits, outline_iou=whole)
    return Visual(model, True, shown, None, _png(illustration), edits, outline_iou=whole)


def illustrate_from_env(render_png: Path, mask_png: Path, outline_png: Path) -> Visual:
    """``illustrate`` with a Meta Model API client using the ``META_API_KEY`` key."""
    key = os.environ.get("META_API_KEY")
    if not key:
        raise KeyError("META_API_KEY is not set: get a Meta Model API key")
    client = visual_client(key)
    return illustrate(render_png, mask_png, outline_png, client, Segmenter(client))


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


def _scaled(silhouette: NDArray[np.bool_], window: Box, size: tuple[int, int]) -> NDArray[np.bool_]:
    """``silhouette`` cut to ``window`` and scaled to ``size``, as the render was."""
    mask = Image.fromarray(silhouette.astype(np.uint8) * 255, "L")
    return np.asarray(mask.crop(window).resize(size, Image.Resampling.BILINEAR)) > 127


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


def _edit(scene: bytes, prompt: str, client: OpenAI, model: str) -> Image.Image:
    response = client.images.edit(
        model=model,
        image=("design.png", scene, "image/png"),
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
