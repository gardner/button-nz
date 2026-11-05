"""Build a design spec, deterministically: the Blender script the design run
executes, so the model chooses and this code builds.

The Dwelling is a few convex solids in one mesh, in the scene's local frame:
the walls (a solid box from the floor's underside, the envelope the
evaluator measures), the roof over the walls grown by the eaves (a
``FASCIA_M`` edge, then its form), and a deck as a thin slab level with the
floor, above its underside. Each solid's faces come from its points (a convex
hull, here in Python), so the geometry is tested without Blender, and Blender
only turns it into the mesh. ``check`` refuses, before any build, a spec its
placement can't hold.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from button_nz.agent.offers import Offer, Offers, floor_range_text
from button_nz.agent.spec import DesignSpec, Side, SpecError, spec_json
from button_nz.evaluation.checks import MAX_FLOOR_AREA_M2, MAX_HEIGHT_ABOVE_FLOOR_M

FLOOR_M = 0.2  # the floor's build-up, from its underside to where the walls start
FASCIA_M = 0.15  # the roof's edge, at the eaves
DECK_M = 0.12  # the deck's slab: its top is level with the floor
WALL_M = 0.15  # the walls' thickness, for the internal floor area
_EPS = 1e-6

type Vertex = tuple[float, float, float]
type Plan = tuple[float, float, float]  # along the long walls, across them, z


@dataclass(frozen=True)
class Solid:
    vertices: tuple[Vertex, ...]
    faces: tuple[tuple[int, ...], ...]  # anticlockwise seen from outside


@dataclass(frozen=True)
class Dwelling:
    solids: tuple[Solid, ...]
    floor_area_m2: float  # inside walls ``WALL_M`` thick

    def triangles(self) -> list[list[list[float]]]:
        """Every face as triangles, as ``design_measure.py`` reports a Dwelling."""
        return [
            [list(s.vertices[face[0]]), list(s.vertices[a]), list(s.vertices[b])]
            for s in self.solids
            for face in s.faces
            for a, b in zip(face[1:], face[2:], strict=False)
        ]


def check(spec: DesignSpec, offers: Offers) -> Offer:
    """The placement ``spec`` is built on; a ``SpecError`` if it can't hold it."""
    offer = offers.get(spec.placement)
    if offer is None:
        numbers = ", ".join(str(o.number) for o in offers.offers)
        raise SpecError(f"There is no placement {spec.placement}: choose one of {numbers}.")
    low, high = offer.floor_range
    if not low - _EPS <= spec.floor_z_m <= high + _EPS:
        raise SpecError(
            f"The floor's underside at z {spec.floor_z_m:g} is outside placement "
            f"{offer.number}'s floor range, z {floor_range_text(low, high)}."
        )
    _check_sides(spec, offer)
    height = height_above_floor(spec, offer)
    if height > MAX_HEIGHT_ABOVE_FLOOR_M + _EPS:
        raise SpecError(
            f"This design reaches {height:.2f} m above the floor's underside; at most "
            f"{MAX_HEIGHT_ABOVE_FLOOR_M:g} m. Lower the pitch, the walls or the eaves."
        )
    area = _floor_area(offer)
    if area > MAX_FLOOR_AREA_M2 + _EPS:
        raise SpecError(f"Placement {offer.number} is {area:.1f} m² inside; at most 70 m².")
    return offer


def _check_sides(spec: DesignSpec, offer: Offer) -> None:
    sides = offer.sides()
    named = [o.side for o in spec.openings]
    named += [spec.deck.side] if spec.deck else []
    named += [spec.roof.high_side] if spec.roof.high_side else []
    for side in named:
        if side not in sides:
            raise SpecError(
                f"Placement {offer.number} has no side {side}: its walls face {', '.join(sides)}."
            )
    if spec.deck and spec.deck.width_m and spec.deck.width_m > _wall(offer, spec.deck.side) + _EPS:
        raise SpecError(
            f"The deck's width, {spec.deck.width_m:g} m, is more than the "
            f"{_wall(offer, spec.deck.side):g} m wall it is beside."
        )


def height_above_floor(spec: DesignSpec, offer: Offer) -> float:
    """From the floor's underside to the top of the roof."""
    rise = _rise(spec.roof.form, spec.roof.pitch_deg, _run(spec, offer))
    return FLOOR_M + spec.wall_height_m + FASCIA_M + rise


def steepest_pitch(offer: Offer, form: str, wall_height_m: float, eaves_m: float) -> float:
    """The steepest a ``form`` roof can be on ``offer`` within the height limit
    (a skillion high on a long wall), in degrees."""
    room = MAX_HEIGHT_ABOVE_FLOOR_M - FLOOR_M - wall_height_m - FASCIA_M
    half = offer.width_m / 2 + eaves_m
    run = 2 * half if form == "skillion" else half
    return math.degrees(math.atan2(room, run))


def _run(spec: DesignSpec, offer: Offer) -> float:
    """How far the roof slopes up: to the ridge, or (a skillion) across the roof."""
    half = offer.width_m / 2 + spec.eaves_m
    if spec.roof.high_side is None:
        return half
    along, _ = offer.sides()[spec.roof.high_side]
    return 2 * (offer.length_m / 2 + spec.eaves_m) if along else 2 * half


def _rise(form: str, pitch_deg: float, run: float) -> float:
    return 0.0 if form == "flat" else run * math.tan(math.radians(pitch_deg))


def _wall(offer: Offer, side: Side) -> float:
    along, _ = offer.sides()[side]
    return offer.width_m if along else offer.length_m


def _floor_area(offer: Offer) -> float:
    return (offer.length_m - 2 * WALL_M) * (offer.width_m - 2 * WALL_M)


def dwelling(spec: DesignSpec, offer: Offer) -> Dwelling:
    """The Dwelling ``spec`` describes on ``offer`` (assumed ``check``ed)."""
    half_l, half_w = offer.length_m / 2, offer.width_m / 2
    floor, top = spec.floor_z_m, spec.floor_z_m + FLOOR_M + spec.wall_height_m
    walls = _box(-half_l, half_l, -half_w, half_w, floor, top)
    plans = [walls, _roof(spec, offer, top)]
    if spec.deck is not None:
        plans.append(_deck(spec, offer))
    solids = tuple(_hull([_placed(p, offer) for p in plan]) for plan in plans)
    return Dwelling(solids, round(_floor_area(offer), 6))


def _box(s0: float, s1: float, t0: float, t1: float, z0: float, z1: float) -> list[Plan]:
    return [(s, t, z) for s in (s0, s1) for t in (t0, t1) for z in (z0, z1)]


def _roof(spec: DesignSpec, offer: Offer, z0: float) -> list[Plan]:
    """The roof over the walls and eaves: its edge, then its form."""
    big_s, big_t = offer.length_m / 2 + spec.eaves_m, offer.width_m / 2 + spec.eaves_m
    z1 = z0 + FASCIA_M
    base = [(s, t, z0) for s in (-big_s, big_s) for t in (-big_t, big_t)]
    tan = math.tan(math.radians(spec.roof.pitch_deg))
    form = spec.roof.form
    if form == "skillion" and spec.roof.high_side is not None:
        ds, dt = offer.sides()[spec.roof.high_side]
        reach = big_s if ds else big_t  # from the middle to the low edge
        return base + [
            (s, t, z1 + tan * (s * ds + t * dt + reach)) for s, t, _ in base
        ]  # the low edge at z1
    edge = [(s, t, z1) for s, t, _ in base]
    if form == "flat":
        return base + edge
    ridge = big_s if form == "gable" else max(big_s - big_t, 0.0)  # hips at 45° in plan
    return base + edge + [(-ridge, 0.0, z1 + big_t * tan), (ridge, 0.0, z1 + big_t * tan)]


def _deck(spec: DesignSpec, offer: Offer) -> list[Plan]:
    """A slab out from the deck's wall, centred on it, its top level with the floor."""
    assert spec.deck is not None
    ds, dt = offer.sides()[spec.deck.side]
    face = offer.length_m / 2 if ds else offer.width_m / 2
    half = (spec.deck.width_m or _wall(offer, spec.deck.side)) / 2
    out = (face, face + spec.deck.depth_m)
    z1 = spec.floor_z_m + FLOOR_M
    if ds:
        s0, s1 = sorted(ds * v for v in out)
        return _box(s0, s1, -half, half, z1 - DECK_M, z1)
    t0, t1 = sorted(dt * v for v in out)
    return _box(-half, half, t0, t1, z1 - DECK_M, z1)


def _placed(point: Plan, offer: Offer) -> Vertex:
    """A point of the plan's frame in the scene's."""
    s, t, z = point
    a = math.radians(offer.angle_deg)
    x = offer.centre[0] + s * math.cos(a) - t * math.sin(a)
    y = offer.centre[1] + s * math.sin(a) + t * math.cos(a)
    return (x, y, z)


def _hull(points: Sequence[Vertex]) -> Solid:
    """The convex solid ``points`` span: each face is every point on a plane
    with all the others behind it, wound anticlockwise seen from outside."""
    vertices = tuple(dict.fromkeys(points))  # a pyramid's ridge is one point
    centre = _mean(vertices)
    planes: set[frozenset[int]] = set()
    for i, j, k in combinations(range(len(vertices)), 3):
        normal = _cross(_sub(vertices[j], vertices[i]), _sub(vertices[k], vertices[i]))
        size = math.sqrt(_dot(normal, normal))
        if size < _EPS:
            continue
        side = [_dot(normal, _sub(v, vertices[i])) / size for v in vertices]
        if all(d <= _EPS for d in side) or all(d >= -_EPS for d in side):
            planes.add(frozenset(m for m, d in enumerate(side) if abs(d) <= _EPS))
    faces = tuple(_wound(sorted(plane), vertices, centre) for plane in planes)
    return Solid(vertices, tuple(sorted(faces)))


def _wound(face: list[int], vertices: tuple[Vertex, ...], centre: Vertex) -> tuple[int, ...]:
    """``face``'s points in order round it, anticlockwise seen from outside."""
    points = [vertices[i] for i in face]
    middle = _mean(points)
    a, b, c = points[0], points[1], points[2]
    normal = _cross(_sub(b, a), _sub(c, a))
    if _dot(normal, _sub(middle, centre)) < 0:
        normal = (-normal[0], -normal[1], -normal[2])
    first = _sub(a, middle)
    second = _cross(normal, first)
    order = sorted(
        face,
        key=lambda i: math.atan2(
            _dot(_sub(vertices[i], middle), second), _dot(_sub(vertices[i], middle), first)
        ),
    )
    start = order.index(min(order))
    return tuple(order[start:] + order[:start])


def _mean(points: Sequence[Vertex]) -> Vertex:
    n = len(points)
    return (
        sum(p[0] for p in points) / n,
        sum(p[1] for p in points) / n,
        sum(p[2] for p in points) / n,
    )


def _sub(a: Vertex, b: Vertex) -> Vertex:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vertex, b: Vertex) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vertex, b: Vertex) -> Vertex:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


SCRIPT = """# Built by button_nz.agent.build from this design spec:
# {spec}
VERTICES = {vertices}
FACES = {faces}
mesh = bpy.data.meshes.new("Dwelling")
mesh.from_pydata(VERTICES, [], FACES)
mesh.update()
dwelling = bpy.data.objects.new("Dwelling", mesh)
bpy.context.scene.collection.objects.link(dwelling)
dwelling["floor_area_m2"] = {area!r}
dwelling["storeys"] = 1
"""


def spec_to_script(spec: DesignSpec, offer: Offer) -> str:
    """The Blender script that builds ``spec`` on ``offer``, in the design run's
    contract: one mesh named Dwelling, its stated floor area and storeys."""
    built = dwelling(spec, offer)
    vertices: list[Vertex] = []
    faces: list[tuple[int, ...]] = []
    for solid in built.solids:
        faces += [tuple(len(vertices) + i for i in face) for face in solid.faces]
        vertices += solid.vertices
    return SCRIPT.format(
        spec=spec_json(spec), vertices=vertices, faces=faces, area=built.floor_area_m2
    )
