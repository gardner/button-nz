"""Serve the API for the demo site:

    uv run --env-file .env python -m button_nz.api.serve [--data var] [--port 8000] \
        [--daily-designs 30] [--survey-decided-by "the owner, on 31 October 2026"]

Jobs are kept in ``DATA/button.db`` and their files under ``DATA/runs``; the
site survey is read from ``DATA/survey.geojson``. The model key is read per
job, so the server starts without one and a job queued without it fails with
that reason. Each accepted design also gets an AI visual (``perception.visual``),
made here in the server with the same key, never in the Blender sandbox. A
server others can reach should cap its design runs a day (``api.limits``) and
fix the survey as the owner decided it.
"""

import argparse
from pathlib import Path

import uvicorn

from button_nz.agent.demo import demo_site
from button_nz.agent.model import ChatModel
from button_nz.api.aerial import demo_aerial
from button_nz.api.app import create_app
from button_nz.api.jobs import Worker
from button_nz.api.limits import DailyCap
from button_nz.api.store import Store
from button_nz.demo_site import load_demo_site
from button_nz.perception.survey import SURVEY_FILE
from button_nz.perception.visual import illustrate_from_env


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the button-nz API.")
    parser.add_argument("--data", type=Path, default=Path("var"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--daily-designs", type=int, help="start at most this many design runs in any 24 hours"
    )
    parser.add_argument(
        "--survey-decided-by",
        help="fix the survey, as this person decided it (e.g. 'the owner'); empty leaves it open",
    )
    args = parser.parse_args(argv)
    store = Store(args.data / "button.db")
    survey = args.data / SURVEY_FILE
    worker = Worker(
        store,
        site=demo_site,
        model=ChatModel.from_env,
        runs_dir=args.data / "runs",
        survey=survey,
        illustrator=illustrate_from_env,
    )
    site = load_demo_site()
    cap = None if args.daily_designs is None else DailyCap(store, args.daily_designs)
    app = create_app(
        store,
        worker,
        site,
        survey=survey,
        aerial=demo_aerial(site),
        cap=cap,
        survey_decided_by=args.survey_decided_by or None,  # empty: the owner is deciding
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
