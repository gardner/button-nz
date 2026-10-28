"""Coordinate transforms between NZTM2000, WGS84 and a site's local frame.

Site work is in NZTM2000 (EPSG:2193) metres. Blender scenes use a local frame:
metre offsets from a site origin, so the scene never carries seven-digit
coordinates.
"""

from dataclasses import dataclass

from pyproj import Transformer

from button_nz.geo.geometry import BBox, Point

_TO_WGS84 = Transformer.from_crs(2193, 4326, always_xy=True)
_TO_NZTM = Transformer.from_crs(4326, 2193, always_xy=True)


def nztm_to_wgs84(point: Point) -> Point:
    """NZTM2000 (easting, northing) to WGS84 (longitude, latitude)."""
    lon, lat = _TO_WGS84.transform(point[0], point[1])
    return (float(lon), float(lat))


def wgs84_to_nztm(point: Point) -> Point:
    """WGS84 (longitude, latitude) to NZTM2000 (easting, northing)."""
    x, y = _TO_NZTM.transform(point[0], point[1])
    return (float(x), float(y))


@dataclass(frozen=True)
class LocalFrame:
    """Metre offsets from an NZTM origin. Axes stay aligned with NZTM: +x east,
    +y north (grid north)."""

    origin: Point

    @classmethod
    def centred_on(cls, bbox: BBox) -> LocalFrame:
        return cls(origin=((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2))

    def to_local(self, point: Point) -> Point:
        return (point[0] - self.origin[0], point[1] - self.origin[1])

    def to_nztm(self, point: Point) -> Point:
        return (point[0] + self.origin[0], point[1] + self.origin[1])
