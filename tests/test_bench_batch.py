"""Tests for button_nz.bench.batch: the many-sites design run's pure parts."""

from collections.abc import Iterator
from typing import Any

import httpx

from button_nz.bench.batch import is_rectangle, pick, street_distance
from button_nz.sites.frontages import Frontage


def section(pid: int, size: float, category: str = "clear") -> dict[str, object]:
    ring = [[0, 0], [size, 0], [size, size], [0, size], [0, 0]]
    return {
        "type": "Feature",
        "properties": {"id": pid, "category": category},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def test_sections_with_room_are_picked_across_their_range_of_sizes() -> None:
    sections = [section(i, 1 + i) for i in range(10)] + [section(99, 50, "none")]
    picked = pick(sections, 3)
    assert 99 not in picked  # no room
    assert picked == [0, 4, 9]  # smallest, middle, largest: varied, and the same each run


def test_a_plain_rectangle_is_told_from_a_cut_corner() -> None:
    assert is_rectangle([(0, 0), (8, 0), (8, 5), (0, 5), (0, 0)])
    assert is_rectangle([(0, 0), (8, 0.0001), (8, 5), (0, 5), (0, 0)])  # rounding
    assert not is_rectangle([(0, 0), (8, 0), (8, 3), (6, 5), (0, 5), (0, 0)])  # Dick Street's
    assert not is_rectangle([(0, 0), (8, 0), (9, 5), (0, 5), (0, 0)])  # not square


def test_the_distance_from_the_street_is_from_its_edge_or_none_without_one() -> None:
    walls = [(5.0, 7.0), (10.0, 7.0), (10.0, 12.0), (5.0, 12.0), (5.0, 7.0)]
    street = Frontage("Coal Street", True, (((0.0, 0.0), (40.0, 0.0)),))
    other = Frontage("Curle Street", False, (((0.0, 0.0), (0.0, 30.0)),))
    assert street_distance(walls, (other, street)) == 7.0
    assert street_distance(walls, (other,)) is None


def test_a_visual_still_being_made_is_waited_for_not_counted_as_failed(monkeypatch: Any) -> None:
    from button_nz.bench import batch_run

    monkeypatch.setattr(batch_run, "POLL_S", 0.0)
    making: dict[str, Any] = {"number": 1, "files": {}}  # no visual.json until it's made
    made: dict[str, Any] = {
        "number": 1,
        "files": {"visual.json": "/designs/j/attempts/1/visual.json"},
    }
    polls: Iterator[tuple[bool, dict[str, Any]]] = iter([(True, making), (False, made)])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("visual.json"):
            return httpx.Response(200, json={"accepted": True})
        illustrating, attempt = next(polls)
        body = {
            "id": "j",
            "illustrating": illustrating,
            "attempts": [attempt],
            "accepted_attempt": 1,
        }
        return httpx.Response(200, json=body)

    client = httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))
    job: dict[str, Any] = {
        "id": "j",
        "illustrating": True,
        "attempts": [making],
        "accepted_attempt": 1,
    }
    assert batch_run._visual(client, job) is True  # pyright: ignore[reportPrivateUsage]
