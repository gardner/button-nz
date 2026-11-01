"""The site a design is made for: its scene, local frame and evaluation context."""

from dataclasses import dataclass

from button_nz.blender_worker.scene_input import SceneInput
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.sites.frontages import Frontage


@dataclass(frozen=True)
class DesignSite:
    scene: SceneInput
    frame: LocalFrame
    context: SiteContext
    frontages: tuple[Frontage, ...] | None = None  # None: not known for this site
