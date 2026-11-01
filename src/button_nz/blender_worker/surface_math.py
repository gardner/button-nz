"""Texture coordinates for the baked Dwelling, in metres. Pure Python: imported
by path inside Blender (``design_measure``) and tested outside it.

Each triangle is mapped onto its own plane, so every edge keeps its length and
a texture tiles at true scale on walls and roof slopes alike: ``u`` runs level
along the face, ``v`` up it (up a wall, up a roof's slope). A level face maps
east and north. Coplanar triangles share the mapping whatever their winding, so
a wall or roof plane is seamless however it is triangulated.
"""

import math

Point = tuple[float, float, float]
UV = tuple[float, float]
LEVEL = 1e-9  # a normal with less horizontal component than this: a level face


def face_uvs(a: Point, b: Point, c: Point) -> list[UV]:
    """The UVs of triangle ``abc``'s corners, in metres in its own plane."""
    n = _cross(_minus(b, a), _minus(c, a))
    length = math.sqrt(_dot(n, n))
    across = math.hypot(n[0], n[1])
    if length == 0.0 or across / length < LEVEL:  # level (or no area): east and north
        return [(p[0], p[1]) for p in (a, b, c)]
    dominant = n[0] if abs(n[0]) >= abs(n[1]) else n[1]  # its sign is never rounding noise
    if dominant < 0:  # the plane's normal, not the winding's: always the same one of two
        n = (-n[0], -n[1], -n[2])
    u = (-n[1] / across, n[0] / across, 0.0)  # level, in the plane
    v = _cross(n, u)  # in the plane, with a positive height component
    v_length = math.sqrt(_dot(v, v))
    v = (v[0] / v_length, v[1] / v_length, v[2] / v_length)
    return [(_dot(p, u), _dot(p, v)) for p in (a, b, c)]


def _minus(p: Point, q: Point) -> Point:
    return (p[0] - q[0], p[1] - q[1], p[2] - q[2])


def _cross(p: Point, q: Point) -> Point:
    return (p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0])


def _dot(p: Point, q: Point) -> float:
    return p[0] * q[0] + p[1] * q[1] + p[2] * q[2]
