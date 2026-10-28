"""Serve the API for the demo site:

    uv run --env-file .env python -m button_nz.api.serve [--data var] [--port 8000]

Jobs are kept in ``DATA/button.db`` and their files under ``DATA/runs``; the
site survey is read from ``DATA/survey.geojson``. The model key is read per
job, so the server starts without one and a job queued without it fails with
that reason.
"""

import argparse
from pathlib import Path

import uvicorn

from button_nz.agent.demo import demo_site
from button_nz.agent.model import ChatModel
from button_nz.api.app import create_app
from button_nz.api.jobs import Worker
from button_nz.api.store import Store
from button_nz.demo_site import load_demo_site


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the button-nz API.")
    parser.add_argument("--data", type=Path, default=Path("var"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    store = Store(args.data / "button.db")
    survey = args.data / "survey.geojson"
    worker = Worker(
        store,
        site=demo_site,
        model=ChatModel.from_env,
        runs_dir=args.data / "runs",
        survey=survey,
    )
    app = create_app(store, worker, load_demo_site(), survey=survey)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
