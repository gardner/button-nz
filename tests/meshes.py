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
