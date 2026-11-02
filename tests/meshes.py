"""Triangle meshes for tests, as design_measure.py reports a Dwelling."""

type Triangle = list[list[float]]


def box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> list[Triangle]:
    """A closed axis-aligned box as 12 triangles."""
    corners = [[x, y, z] for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    quads = [
        (0, 1, 3, 2),  # bottom
        (4, 6, 7, 5),  # top
        (0, 4, 5, 1),  # south
        (2, 3, 7, 6),  # north
        (0, 2, 6, 4),  # west
        (1, 5, 7, 3),  # east
    ]
    return [
        [corners[a], corners[b], corners[c]]
        for q in quads
        for a, b, c in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))
    ]


def hollow_house(
    door: bool, slab: bool = True, door_x: float = 5.5, door_width: float = 1.0
) -> list[Triangle]:
    """A 12 m x 10 m house the usual bpy way: slab, four 0.2 m walls, roof; the
    door is a ``door_width`` gap in the south wall from ``door_x``."""
    floor = box(0, 0, 0, 12, 10, 0.2) if slab else []
    north, east, west = (
        box(0, 9.8, 0.2, 12, 10, 3),
        box(11.8, 0, 0.2, 12, 10, 3),
        box(0, 0, 0.2, 0.2, 10, 3),
    )
    south = (
        box(0.2, 0, 0.2, door_x, 0.2, 3) + box(door_x + door_width, 0, 0.2, 11.8, 0.2, 3)
        if door
        else box(0.2, 0, 0.2, 11.8, 0.2, 3)
    )
    lintel = box(door_x, 0, 2.1, door_x + door_width, 0.2, 3) if door else []
    roof = box(0, 0, 3, 12, 10, 3.2)
    return floor + north + east + west + south + lintel + roof


def a_frame(width: float, length: float, ridge: float) -> list[Triangle]:
    """A triangular prism along y: two roof slopes from the floor to the ridge."""
    a, b, c = [0.0, 0.0, 0.0], [width, 0.0, 0.0], [width / 2, 0.0, ridge]
    d, e, f = [0.0, length, 0.0], [width, length, 0.0], [width / 2, length, ridge]
    return [
        [a, b, c],
        [d, f, e],  # gable ends
        [a, d, e],
        [a, e, b],  # floor
        [a, c, f],
        [a, f, d],  # west slope
        [b, e, f],
        [b, f, c],  # east slope
    ]
