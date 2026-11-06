"""Bound episode subprocess lifetimes and simulator startup concurrency."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager, nullcontext
import os
import queue
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import Any


def _stop_process_tree(process: subprocess.Popen, grace_s: float = 2.0) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            process.wait()
            return
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        pass
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.kill()
    process.wait()


@contextmanager
def _device_slot(pool, check_cancelled):
    if pool is None:
        yield None
        return
    while True:
        check_cancelled()
        try:
            device = pool.get(timeout=0.1)
            break
        except queue.Empty:
            continue
    try:
        yield device
    finally:
        pool.put(device)


def run_episode_process(
    cmd: list[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
    timeout_s: float,
    boot_gate: Any = None,
    render_gate: Any = None,
    device_pool: Any = None,
    cancel_event: Any = None,
    env: dict[str, str] | None = None,
) -> int:
    """Hold a render slot for the process and a boot slot until reset completes.

    Queueing for a slot is excluded from the episode timeout. The child signals
    readiness through a fresh temporary file, so resumed runs cannot reuse a
    previous startup signal. Logs go directly to files while the child runs.
    """
    def check_cancelled():
        if cancel_event is not None and cancel_event.is_set():
            raise KeyboardInterrupt("Evaluation cancelled.")

    check_cancelled()
    with (render_gate if render_gate is not None else nullcontext(),
          _device_slot(device_pool, check_cancelled) as device):
        check_cancelled()
        child_env = dict(os.environ if env is None else env)
        if device is not None:
            child_env["VIGIL_GPU_DEVICE"] = str(device)
        with tempfile.TemporaryDirectory(prefix="vigil-episode-") as tmp:
            ready_path = Path(tmp) / "ready"
            child_cmd = [*cmd, "--startup-ready-file", str(ready_path)]
            process = None
            with (
                stdout_path.open("w", encoding="utf-8") as stdout,
                stderr_path.open("w", encoding="utf-8") as stderr,
                ExitStack() as startup_slot,
            ):
                startup_slot.enter_context(
                    boot_gate if boot_gate is not None else nullcontext()
                )
                try:
                    check_cancelled()
                    deadline = time.monotonic() + timeout_s if timeout_s > 0 else None
                    process = subprocess.Popen(
                        child_cmd,
                        stdout=stdout,
                        stderr=stderr,
                        env=child_env,
                        start_new_session=os.name == "posix",
                    )
                    while process.poll() is None and not ready_path.exists():
                        check_cancelled()
                        if deadline is not None and time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(cmd, timeout_s)
                        time.sleep(0.02)
                    if ready_path.exists():
                        startup_slot.close()
                    # A failed startup keeps its slot through process-tree cleanup.
                    remaining = (
                        max(0.0, deadline - time.monotonic())
                        if deadline is not None
                        else None
                    )
                    if cancel_event is None:
                        return process.wait(timeout=remaining)
                    while process.poll() is None:
                        check_cancelled()
                        if deadline is not None and time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(cmd, timeout_s)
                        time.sleep(0.05)
                    check_cancelled()
                    return process.returncode
                except subprocess.TimeoutExpired as exc:
                    raise subprocess.TimeoutExpired(cmd, timeout_s) from exc
                finally:
                    if process is not None:
                        _stop_process_tree(process)
