"""The bubblewrap sandbox for Blender runs that touch model-written code or data.

Inside it: read-only system files; fresh, size-limited tmpfs for the home
directory, /tmp, /run (so no host Unix sockets such as the user's D-Bus or
Docker) and /dev/shm (no host shared memory); its own IPC, PID and network
namespaces; a cleared environment (no API keys or other secrets); the GPU
device nodes. Only Blender, the worker scripts and a pass's input files are
mounted back, read-only. A host directory is writable only for a trusted pass;
the untrusted pass instead gets a size-limited tmpfs at ``SCRATCH`` and an
address-space limit, so it can't fill the host's disk or memory.
"""

import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

CYCLES_CACHE = Path.home() / ".cache" / "cycles"  # compiled GPU kernels, kept across runs
# A user-level Blender install (see README): the launcher and the build it runs.
BLENDER_INSTALL_PATHS = (Path.home() / ".local" / "bin", Path.home() / ".local" / "opt")
WORKER_DIR = Path(__file__).parent
SANDBOX_ENV = ("PATH", "HOME", "LANG", "CUDA_VISIBLE_DEVICES")  # all the sandbox gets
SCRATCH = "/tmp/scratch"  # nested in the sandbox's own /tmp
SCRATCH_BYTES = 1 << 30
TMPFS_BYTES = 512 << 20
UNTRUSTED_MEMORY_BYTES = 16 << 30


@dataclass(frozen=True)
class Sandbox:
    inputs: Sequence[Path]  # files the pass reads, mounted read-only
    writable: Path | None = None  # a host directory: trusted passes only
    renders: bool = False  # mount Cycles' kernel cache read-write
    untrusted: bool = False  # model code runs: tmpfs scratch and a memory limit

    def wrap(self, command: list[str], env: Mapping[str, str]) -> list[str]:
        """``command`` under bubblewrap (and, if ``untrusted``, prlimit)."""
        home = str(Path.home())
        args = ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev", "--proc", "/proc"]
        for path in ("/dev/shm", "/tmp", "/run", home):
            args += ["--size", str(TMPFS_BYTES), "--tmpfs", path]
        for path in [*_read_paths(command[0]), *(p.resolve() for p in self.inputs)]:
            args += ["--ro-bind", str(path), str(path)]
        if self.renders:
            CYCLES_CACHE.mkdir(parents=True, exist_ok=True)
            args += ["--bind", str(CYCLES_CACHE), str(CYCLES_CACHE)]
        if self.writable is not None:
            args += ["--bind", str(self.writable.resolve()), str(self.writable.resolve())]
        if self.untrusted:
            args += ["--size", str(SCRATCH_BYTES), "--tmpfs", SCRATCH]
        args += ["--unshare-net", "--unshare-ipc", "--unshare-pid", "--die-with-parent"]
        args += ["--new-session", "--clearenv", "--setenv", "PYTHONDONTWRITEBYTECODE", "1"]
        for name in SANDBOX_ENV:
            if name in env:
                args += ["--setenv", name, env[name]]
        args += ["--", *command]
        if self.untrusted:
            args = ["prlimit", f"--as={UNTRUSTED_MEMORY_BYTES}", "--", *args]
        return args


def _read_paths(blender: str) -> list[Path]:
    """The worker scripts, Blender's directory, and the user-level install
    (``~/.local/bin`` launcher and ``~/.local/opt`` build) if they exist."""
    paths = [WORKER_DIR.resolve()]
    found = shutil.which(blender)
    if found:
        paths.append(Path(found).resolve().parent)
    paths += [p for p in BLENDER_INSTALL_PATHS if p.is_dir()]
    return list(dict.fromkeys(paths))
