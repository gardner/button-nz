"""The bubblewrap sandbox for Blender runs that touch model-written code or data.

Inside it: only the system's files, read-only (/usr, /etc, /opt, /sys; no
/home, /var or /srv); a private /dev with only the GPU's nodes
(no host terminals, webcam or microphone); fresh, size-limited tmpfs for the
home directory, /tmp, /run (so no host Unix sockets such as the user's D-Bus
or Docker) and /dev/shm (no host shared memory); its own IPC, PID and network
namespaces; a cleared environment (no API keys or other secrets); the GPU
device nodes. Only Blender, the worker scripts and a pass's input files are
mounted back, read-only. A host directory is writable only for a trusted pass;
the untrusted pass instead gets a size-limited tmpfs at ``SCRATCH`` and an
address-space limit, so it can't fill the host's disk or memory. Each sandbox
runs in a systemd user scope capping its processes and their total memory.
"""

import glob
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
RENDER_MEMORY_BYTES = 16 << 30
TOTAL_MEMORY_BYTES = 24 << 30  # all of a sandbox's processes together
MAX_TASKS = 512
SYSTEM_DIRS = ("/usr", "/etc", "/opt", "/sys")
SYSTEM_LINKS = (
    ("/bin", "usr/bin"),
    ("/sbin", "usr/sbin"),
    ("/lib", "usr/lib"),
    ("/lib64", "usr/lib64"),
)  # pass 2's heap: the model's geometry, evaluated


@dataclass(frozen=True)
class Sandbox:
    inputs: Sequence[Path]  # files the pass reads, mounted read-only
    writable: Path | None = None  # a host directory: trusted passes only
    renders: bool = False  # mount Cycles' kernel cache read-write
    untrusted: bool = False  # model code runs: tmpfs scratch and a memory limit

    def wrap(self, command: list[str], env: Mapping[str, str]) -> list[str]:
        """``command`` in the sandbox, under its resource limits."""
        args = ["bwrap", *self._mounts(command[0])]
        args += ["--unshare-net", "--unshare-ipc", "--unshare-pid", "--die-with-parent"]
        args += ["--new-session", "--clearenv", "--setenv", "PYTHONDONTWRITEBYTECODE", "1"]
        for name in SANDBOX_ENV:
            if name in env:
                args += ["--setenv", name, env[name]]
        if self.untrusted:
            limit = f"--as={UNTRUSTED_MEMORY_BYTES}"
        else:  # CUDA reserves address space it never uses: cap the data segment instead
            limit = f"--data={RENDER_MEMORY_BYTES}"
        # A systemd user scope caps the whole sandbox, however many processes it forks.
        scope = ["systemd-run", "--user", "--scope", "--quiet", "--collect"]
        scope += ["-p", f"TasksMax={MAX_TASKS}", "-p", f"MemoryMax={TOTAL_MEMORY_BYTES}"]
        return [*scope, "--", "prlimit", limit, "--", *args, "--", *command]

    def _mounts(self, blender: str) -> list[str]:
        args = ["--dev", "/dev", "--proc", "/proc"]
        for path in SYSTEM_DIRS:  # the system, not the host's data: no /home, /var or /srv
            args += ["--ro-bind-try", path, path]
        for link, target in SYSTEM_LINKS:
            args += ["--symlink", target, link]
        for node in _gpu_nodes():  # a private /dev, with only these bound back
            args += ["--dev-bind-try", node, node]
        for path in ("/dev/shm", "/tmp", "/run", str(Path.home())):
            args += ["--size", str(TMPFS_BYTES), "--tmpfs", path]
        for path in [*_read_paths(blender), *(p.resolve() for p in self.inputs)]:
            args += ["--ro-bind", str(path), str(path)]
        writable = [CYCLES_CACHE] if self.renders else []
        writable += [] if self.writable is None else [self.writable.resolve()]
        for path in writable:
            path.mkdir(parents=True, exist_ok=True)
            args += ["--bind", str(path), str(path)]
        if self.untrusted:
            args += ["--size", str(SCRATCH_BYTES), "--tmpfs", SCRATCH]
        return args


def _gpu_nodes() -> list[str]:
    return [*sorted(glob.glob("/dev/nvidia*")), "/dev/dri"]


def _read_paths(blender: str) -> list[Path]:
    """The worker scripts, Blender's directory, and the user-level install
    (``~/.local/bin`` launcher and ``~/.local/opt`` build) if they exist."""
    paths = [WORKER_DIR.resolve()]
    found = shutil.which(blender)
    if found:
        paths.append(Path(found).resolve().parent)
    paths += [p for p in BLENDER_INSTALL_PATHS if p.is_dir()]
    return list(dict.fromkeys(paths))
