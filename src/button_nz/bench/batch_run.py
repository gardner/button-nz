"""The batch run against a live API and LINZ (``bench.batch``'s I/O).

Results are appended to ``results.jsonl`` as each design ends, so a run that
stops (the daily cap, a restart) goes on where it left off when run again.
``report.md`` is rewritten from them each time.
"""

import json
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from statistics import median
from typing import Any

import httpx
from pyproj import Transformer

from button_nz.bench.batch import (
    is_rectangle,
    planned,
    repeat_of,
    road_distances,
    street_distance,
)
from button_nz.geo.arcgis import ArcGISError
from button_nz.geo.geometry import Point
from button_nz.geo.property import find_address
from button_nz.sites.build import SiteError
from button_nz.sites.frontages import fetch_frontages
from button_nz.sites.live import LiveLayers
from button_nz.sites.search import NoSuchSection, address_on_section

POLL_S = 5.0
SITE_TIMEOUT_S = 15 * 60
DESIGN_TIMEOUT_S = 30 * 60
VISUAL_TIMEOUT_S = 10 * 60
TO_NZTM = Transformer.from_crs(4326, 2193, always_xy=True)


class CapReached(RuntimeError):
    """The server refused another design today (429)."""


class SectionDataError(RuntimeError):
    """Something about one section's own data: LINZ has no title, address or
    road for it. Recorded as that section's outcome; the run goes on."""


def _lookup[T](found: Callable[[], T]) -> T:
    """A LINZ lookup about the section, its own "not there" made a
    ``SectionDataError``. Network failures (``ArcGISError``) and anything
    else, a ``KeyError`` from a changed response say, pass through."""
    try:
        return found()
    except (SiteError, NoSuchSection) as error:
        raise SectionDataError(str(error)) from error
    except LookupError as error:
        if type(error) is not LookupError:  # KeyError, IndexError: not "not there"
            raise
        raise SectionDataError(str(error)) from error


def run_batch(api: str, town: str, count: int, out: Path, repeat: Path | None = None) -> None:
    client = httpx.Client(base_url=api, timeout=60.0)
    layers = LiveLayers(httpx.Client(timeout=60.0, follow_redirects=True))
    if repeat is None:
        sections = client.get(f"/town/{town}").raise_for_status().json()["features"]
        designs = planned(sections, count)
    else:
        designs = repeat_of(repeat)
    done = {r["parcel_id"] for r in _results(out)}
    for parcel_id, brief in designs:
        if parcel_id in done:
            continue
        try:
            result = _one(client, layers, parcel_id, brief)
        except (CapReached, httpx.HTTPError, TimeoutError, ArcGISError) as error:
            # The cap, or the API, LINZ or the network failing: stop with
            # nothing written for this section, so running again retries it.
            print(f"stopped: {error}")
            break
        except SectionDataError as error:  # this section's own data: recorded
            result = {"parcel_id": parcel_id, "brief": brief, "outcome": f"error: {error}"}
        _write(out, result)
        print(f"{parcel_id}: {result.get('outcome')}")
    _report(out)


def _one(client: httpx.Client, layers: LiveLayers, parcel_id: int, brief: str) -> dict[str, Any]:
    result: dict[str, Any] = {"parcel_id": parcel_id, "brief": brief}
    address_id = _lookup(lambda: address_on_section(layers.addresses, layers.parcels, parcel_id))
    if address_id is None:
        return result | {"outcome": "no address on the section"}
    asked_site = client.post("/sites", json={"address_id": address_id})
    if asked_site.status_code == 429:  # the site-build cap: stop, as for designs
        raise CapReached(asked_site.json().get("detail", "the daily site cap"))
    site = asked_site.raise_for_status().json()
    site = _poll(client, f"/sites/{site['id']}", {"ready", "failed", "no_lidar"}, SITE_TIMEOUT_S)
    result |= {"site_id": site["id"], "address": site["address"]}
    if site["status"] != "ready":
        return result | {"outcome": f"site {site['status']}: {site.get('error')}"}
    road_id = _lookup(lambda: find_address(layers.addresses, address_id).value.road_id)
    rings = [_ring(f["geometry"]) for f in site["parcels"]["features"]]
    found = (
        ()
        if road_id is None
        else _lookup(lambda: fetch_frontages(layers.parcels, layers.roads, rings, road_id))
    )
    started = time.monotonic()
    asked = client.post("/designs", json={"brief": brief, "site_id": site["id"]})
    if asked.status_code == 429:
        raise CapReached(asked.json().get("detail", "the daily cap"))
    job = _poll(
        client,
        f"/designs/{asked.raise_for_status().json()['id']}",
        {"done", "failed"},
        DESIGN_TIMEOUT_S,
    )
    result |= _verdicts(job) | {
        "design_id": job["id"],
        "seconds": round(time.monotonic() - started),
    }
    if job.get("accepted_attempt") is None:
        return result | {
            "outcome": "not accepted" if job["status"] == "done" else f"failed: {job['error']}"
        }
    walls = _walls(client, job["id"])
    return result | {
        "outcome": "accepted",
        "rectangle": is_rectangle(walls),
        "street_m": street_distance(walls, found),
        "roads_m": road_distances(walls, found),
        "visual": _visual(client, job),
    }


def _verdicts(job: dict[str, Any]) -> dict[str, Any]:
    attempts = job["attempts"]
    last = next(
        (a for a in attempts if a["number"] == job.get("accepted_attempt")),
        attempts[-1] if attempts else None,
    )
    checks = (
        {}
        if last is None or last["checks"] is None
        else {c["name"]: c["status"] for c in last["checks"]}
    )
    first = (
        {}
        if not attempts or attempts[0]["checks"] is None
        else {c["name"]: c["status"] for c in attempts[0]["checks"]}
    )
    return {
        "attempts": len(attempts),
        "accepted_attempt": job.get("accepted_attempt"),
        "checks": checks,
        "first_checks": first,
    }


def _walls(client: httpx.Client, job_id: str) -> list[Point]:
    layers = client.get(f"/designs/{job_id}/map").raise_for_status().json()
    (feature,) = layers["walls"]["features"]
    ring = feature["geometry"]["coordinates"][0]
    return [tuple(float(v) for v in TO_NZTM.transform(x, y)) for x, y, *_ in ring]  # pyright: ignore[reportReturnType]


def _visual(client: httpx.Client, job: dict[str, Any]) -> str:
    """The AI visual's verdict: "passed" or "failed" its SAM check, or "not
    made" (none made, its making or checking failed, or it isn't done in
    time). The visual is made after the design is done (``illustrating``):
    it's waited for, never counted as failed while still coming."""
    deadline = time.monotonic() + VISUAL_TIMEOUT_S
    while job.get("illustrating"):
        if time.monotonic() > deadline:
            return "not made"  # the design is kept either way
        time.sleep(POLL_S)
        job = client.get(f"/designs/{job['id']}").raise_for_status().json()
    accepted = next(a for a in job["attempts"] if a["number"] == job["accepted_attempt"])
    url = accepted["files"].get("visual.json")
    if url is None:
        return "not made"
    record = client.get(url).raise_for_status().json()
    if record.get("iou") is None:  # made or checked by nothing: no silhouette verdict
        return "not made"
    return "passed" if record["accepted"] else "failed"


def _ring(geometry: dict[str, Any]) -> tuple[Point, ...]:
    return tuple((float(x), float(y)) for x, y, *_ in geometry["coordinates"][0])


def _poll(client: httpx.Client, url: str, done: set[str], timeout_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        body: dict[str, Any] = client.get(url).raise_for_status().json()
        if body["status"] in done:
            return body
        if time.monotonic() > deadline:
            raise TimeoutError(f"{url} still {body['status']} after {timeout_s:.0f} s")
        time.sleep(POLL_S)


def _results(out: Path) -> list[dict[str, Any]]:
    path = out / "results.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write(out: Path, result: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")


def _report(out: Path) -> None:
    rows = _results(out)
    designed = [r for r in rows if "attempts" in r]
    accepted = [r for r in designed if r["outcome"] == "accepted"]
    first = [r for r in designed if r.get("accepted_attempt") == 1]
    lines = [
        "# Batch run",
        "",
        f"- sections tried: {len(rows)}; designed: {len(designed)}; accepted: {len(accepted)}",
        f"- accepted on the first attempt: {len(first)} of {len(designed)}",
        f"- plain rectangles: {sum(1 for r in accepted if r['rectangle'])} of {len(accepted)}",
        f"- AI visual passed its SAM check: {sum(1 for r in accepted if r['visual'] == 'passed')}"
        f"; failed it: {sum(1 for r in accepted if r['visual'] == 'failed')}"
        f"; not made or not checked: {sum(1 for r in accepted if r['visual'] == 'not made')}",
        f"- median design time: {median(r['seconds'] for r in designed):.0f} s" if designed else "",
        "",
        "## First attempts' failing checks",
        "",
    ]
    fails = Counter(n for r in designed for n, s in r["first_checks"].items() if s == "fail")
    lines += [f"- {name}: {n}" for name, n in fails.most_common()] or ["- none"]
    lines += [
        "",
        "## Each design",
        "",
        "| section | brief | outcome | attempts | rectangle | from the street (m) |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.get('address', r['parcel_id'])} | {r['brief']} | {r['outcome']} "
            f"| {r.get('attempts', '')} "
            f"| {r.get('rectangle', '')} | {r.get('street_m', '')} |"
        )
    out.mkdir(parents=True, exist_ok=True)  # a run stopped before its first row
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
