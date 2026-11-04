"""scripts/deploy/install.sh, run on a copy of the repo with every tool stubbed:
what it writes into deploy.env and the API's systemd unit."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

INSTALL = Path(__file__).resolve().parents[1] / "scripts" / "deploy" / "install.sh"
STUBS = {
    "uv": "",
    "node": "",
    "pnpm": "",
    "blender": "",
    "systemctl": 'echo "● button-api.service"; echo "   Active: active (running)"',
    "loginctl": "echo yes",
}


class Install:
    """install.sh in a fresh tree: its own repo copy, config dir and PATH."""

    def __init__(self, root: Path) -> None:
        self.repo = root / "repo"
        script = self.repo / "scripts" / "deploy" / "install.sh"
        script.parent.mkdir(parents=True)
        shutil.copy(INSTALL, script)
        (self.repo / "apps" / "web").mkdir(parents=True)
        (self.repo / ".env").write_text("META_API_KEY=test\n")
        (self.repo / "var").mkdir()
        (self.repo / "var" / "survey.geojson").write_text("{}")
        bin_dir = root / "bin"
        bin_dir.mkdir()
        for name, body in STUBS.items():
            stub = bin_dir / name
            stub.write_text(f"#!/bin/sh\n{body}\n")
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.config = root / "config"
        self.settings = self.config / "button-nz" / "deploy.env"
        self.env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(root),
            "USER": os.environ.get("USER", "test"),
            "XDG_CONFIG_HOME": str(self.config),
        }

    def run(self) -> None:
        script = self.repo / "scripts" / "deploy" / "install.sh"
        subprocess.run(["bash", str(script)], env=self.env, check=True, capture_output=True)

    def set(self, name: str, value: str) -> None:
        lines = self.settings.read_text().splitlines()
        lines = [f'{name}="{value}"' if line.startswith(f"{name}=") else line for line in lines]
        self.settings.write_text("\n".join(lines) + "\n")

    def exec_start(self) -> list[str]:
        unit = (self.config / "systemd" / "user" / "button-api.service").read_text()
        line = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
        return line.removeprefix("ExecStart=").split()


@pytest.fixture
def install(tmp_path: Path) -> Install:
    installed = Install(tmp_path)
    installed.run()  # the first run writes deploy.env and stops
    return installed


def test_a_new_deploy_env_leaves_design_runs_uncapped(install: Install) -> None:
    assert 'BUTTON_DAILY_DESIGNS=""' in install.settings.read_text().splitlines()


def test_no_daily_designs_passes_no_flag(install: Install) -> None:
    install.run()
    assert "--daily-designs" not in install.exec_start()


def test_an_unset_daily_designs_passes_no_flag(install: Install) -> None:
    text = install.settings.read_text().splitlines()
    install.settings.write_text(
        "\n".join(line for line in text if not line.startswith("BUTTON_DAILY_DESIGNS=")) + "\n"
    )
    install.run()
    assert "--daily-designs" not in install.exec_start()


def test_a_daily_designs_value_passes_the_cap(install: Install) -> None:
    install.set("BUTTON_DAILY_DESIGNS", "30")
    install.run()
    args = install.exec_start()
    assert args[args.index("--daily-designs") + 1] == "${BUTTON_DAILY_DESIGNS}"
