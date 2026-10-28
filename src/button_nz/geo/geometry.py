"""Plain 2D geometry shared across the geo code. Coordinates are NZTM metres
unless a name says otherwise."""

type Point = tuple[float, float]
type BBox = tuple[float, float, float, float]
type Ring = tuple[Point, ...]


def contains(ring: Ring, point: Point) -> bool:
    """Whether ``point`` lies inside the closed polygon ``ring`` (ray casting)."""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def bounds(points: tuple[Point, ...] | list[Point]) -> BBox:
    """The bounding box of ``points``."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def covers(outer: BBox, inner: BBox) -> bool:
    """Whether box ``outer`` fully contains box ``inner``."""
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )
