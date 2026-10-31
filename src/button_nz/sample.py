"""Package an accepted design, and the designs it revises, as sample artifacts:

    uv run python -m button_nz.sample DATA JOB_ID OUT.zip --survey-decided-by "the owner"

``DATA`` is the API's data directory (``button.db``, ``runs/``, the survey).
The archive holds, oldest design first, each attempt's files as the run kept
them (``design-<k>/attempt-<n>/``), the survey with its decisions
(``survey.json``), ``sample.json`` (the designs, their attempts and verdicts)
and a README that says what each file is and whose data it is built from.

Only the files listed in ``FILES`` go in, and only as regular files: a link,
to a file or a folder, is refused, never followed. A design without an
accepted attempt is refused, so a sample is always of what the evaluator
accepted, and so is one whose accepted attempt lacks any file in ``ACCEPTED``.
Nothing is written until everything is found.
"""

import argparse
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from button_nz.api.jobs import SURVEY_USED
from button_nz.api.store import Job, Store
from button_nz.demo_site import DemoSite, load_demo_site
from button_nz.perception.confirm import Survey
from button_nz.perception.survey import SURVEY_FILE

FILES = re.compile(
    r"scene\.json|script/design\.blend|design\.py|design\.glb|design\.png|measurements\.json"
    r"|attempt\.json|observation-[1-9][0-9]*\.png|visual\.png|visual\.json"
)
# What every accepted attempt keeps: without one of them, the sample is partial.
ACCEPTED = (
    "attempt.json",
    "scene.json",
    "design.py",
    "script/design.blend",
    "design.glb",
    "design.png",
    "measurements.json",
)
DESCRIPTIONS = {
    "scene.json": "the georeferenced site scene: terrain, nDSM, parcels, local frame",
    "script/design.blend": "the Blender file the model's script saved",
    "design.py": "the model's Blender Python script",
    "design.glb, design.png": "the measured design, exported and rendered",
    "measurements.json": "what the trusted pass measured",
    "attempt.json": "the agent's trace: observations, script, verdict and feedback",
    "observation-<k>.png": "the LiDAR views the model asked for",
    "visual.png, visual.json": "the AI visual and its silhouette check (accepted designs only)",
}


class SampleError(ValueError):
    """The design can't be packaged as it is."""


@dataclass(frozen=True)
class Packed:
    name: str  # its path in the archive
    path: Path


def pack(data: Path, job_id: str, decided_by: str, out: Path) -> None:
    """Write the sample of design ``job_id`` and the designs it revises to ``out``."""
    store = Store(data / "button.db")
    designs = _lineage(store, job_id)
    files = [
        packed
        for k, job in enumerate(designs, 1)
        for packed in _files(data / "runs" / job.id, job, f"design-{k}")
    ]
    surveyed = _surveyed(data, designs, decided_by)
    site = load_demo_site()
    manifest = {
        "packaged_at": datetime.now(UTC).isoformat(),
        "site": {"name": site.name, "title": site.title},
        "survey": {k: v for k, v in surveyed.items() if k != "features"},
        "designs": [_design(store, job) for job in designs],
        "sources": _sources(site),
    }
    partial = out.with_suffix(out.suffix + ".partial")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
        for packed in files:
            archive.write(packed.path, packed.name)
        archive.writestr("survey.json", json.dumps(surveyed, indent=2))
        archive.writestr("sample.json", json.dumps(manifest, indent=2))
        archive.writestr("README.md", _readme(manifest))
    partial.replace(out)


def _lineage(store: Store, job_id: str) -> list[Job]:
    """Design ``job_id`` after the designs it revises, oldest first, each accepted."""
    designs: list[Job] = []
    next_id: str | None = job_id
    while next_id is not None:
        try:
            job = store.get_job(next_id)
        except KeyError:
            raise SampleError(f"no design {next_id}") from None
        if job.accepted_attempt is None:
            raise SampleError(f"design {job.id} has no accepted attempt")
        designs.insert(0, job)
        next_id = job.parent_id
    return designs


def _files(run: Path, job: Job, folder: str) -> list[Packed]:
    """The listed files of every attempt of ``job``, refusing any link and an
    accepted attempt without every file in ``ACCEPTED``."""
    accepted = run / f"attempt-{job.accepted_attempt}"
    if accepted.is_symlink() or not accepted.is_dir():
        raise SampleError(f"design {job.id}'s accepted {accepted.name} isn't in {run}")
    found: list[Packed] = []
    for attempt in sorted(run.glob("attempt-*")):
        for path in sorted([attempt, *attempt.rglob("*")]):
            if path.is_symlink():
                raise SampleError(f"{path} is a link: not followed")
            name = path.relative_to(attempt).as_posix()
            if path.is_file() and FILES.fullmatch(name):
                found.append(Packed(f"{folder}/{attempt.name}/{name}", path))
    kept = {p.name for p in found}
    missing = [n for n in ACCEPTED if f"{folder}/{accepted.name}/{n}" not in kept]
    if missing:
        raise SampleError(f"design {job.id}'s {accepted.name} lacks {', '.join(missing)}")
    return found


def _surveyed(data: Path, designs: list[Job], decided_by: str) -> dict[str, Any]:
    """The survey with the decisions every design was checked against, as the
    worker recorded them when each ran. Designs checked against different ones,
    or a survey replaced since, are refused."""
    used = [_used(data / "runs" / job.id, job) for job in designs]
    if any(u != used[0] for u in used):
        raise SampleError("the designs were checked against different survey decisions")
    if used[0]["survey_id"] is None:
        raise SampleError("the designs ran without a survey: there is no site record to pack")
    survey = Survey.read(data / SURVEY_FILE)
    if survey is None or survey.id != used[0]["survey_id"]:
        raise SampleError(f"the survey in {data} has changed since the designs ran")
    decisions: dict[str, str] = used[0]["decisions"]
    features = [
        {**f, "properties": {**f["properties"], "decision": decisions.get(str(f["id"]))}}
        for f in survey.collection["features"]
    ]
    return {
        **survey.collection,
        "survey_id": survey.id,
        "decided_by": decided_by,
        "buildings_complete": used[0]["buildings_complete"],
        "features": features,
    }


def _used(run: Path, job: Job) -> dict[str, Any]:
    record = run / SURVEY_USED
    if record.is_symlink() or not record.is_file():
        raise SampleError(f"design {job.id} has no record of the survey it was checked against")
    return json.loads(record.read_text(encoding="utf-8"))


def _design(store: Store, job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "brief": job.brief,
        "instruction": job.instruction,
        "parent_id": job.parent_id,
        "created_at": job.created_at.isoformat(),
        "finished_at": None if job.finished_at is None else job.finished_at.isoformat(),
        "accepted_attempt": job.accepted_attempt,
        "attempts": [
            {"number": a.number, "status": a.status, "feedback": a.feedback}
            for a in store.attempts(job.id)
        ],
    }


def _sources(site: DemoSite) -> dict[str, dict[str, str]]:
    return {
        name: {"title": s.title, "licence": s.licence, "attribution": s.attribution}
        for name, s in {**site.rasters, **site.vectors}.items()
    }


def _readme(manifest: dict[str, Any]) -> str:
    designs = "\n".join(
        f"- `design-{k}/`: {d['instruction'] or d['brief']} (accepted attempt "
        f"{d['accepted_attempt']} of {len(d['attempts'])})"
        for k, d in enumerate(manifest["designs"], 1)
    )
    files = "\n".join(f"| `{name}` | {what} |" for name, what in DESCRIPTIONS.items())
    sources = "\n".join(
        f"- {s['title']}: {s['licence']}, {s['attribution']}" for s in manifest["sources"].values()
    )
    return f"""# Button NZ sample: {manifest["site"]["name"]}

Designed by Muse Spark in Blender and checked by the evaluator, from one live
run. The original design comes first; each revision follows the design it
changed.

{designs}

The survey (`survey.json`) is as {manifest["survey"]["decided_by"]} decided it.
`sample.json` lists every attempt with its verdict and feedback.

| File in each `attempt-<n>/` | What it is |
|---|---|
{files}

## Data

Built from these sources:

{sources}
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Package a design as sample artifacts.")
    parser.add_argument("data", type=Path, help="the API's data directory")
    parser.add_argument("job_id", help="the newest design of the chain to pack")
    parser.add_argument("out", type=Path, help="the archive to write, a .zip")
    parser.add_argument("--survey-decided-by", required=True, help="who decided the survey")
    args = parser.parse_args(argv)
    pack(args.data, args.job_id, args.survey_decided_by, args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
