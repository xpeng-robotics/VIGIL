from concurrent.futures import ThreadPoolExecutor
import json
import os
import queue
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from vigil.eval.process import run_episode_process


def test_child_environment_is_used_without_mutating_parent(tmp_path, monkeypatch):
    monkeypatch.setenv("VIGIL_PARENT_ONLY", "private-parent-value")
    script = tmp_path / "env_check.py"
    script.write_text("import os\nassert os.environ['VIGIL_API_KEY'] == 'test-child-key'\nassert 'VIGIL_PARENT_ONLY' not in os.environ\nprint('credential received')\n")
    output = tmp_path / "out"
    assert run_episode_process([sys.executable, str(script)], stdout_path=output,
                               stderr_path=tmp_path / "err", timeout_s=5,
                               env={"VIGIL_API_KEY": "test-child-key"}) == 0
    assert output.read_text().strip() == "credential received"
    assert os.environ["VIGIL_PARENT_ONLY"] == "private-parent-value"


def test_renderer_device_is_child_only_and_released_after_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('VIGIL_GPU_DEVICE', '99')
    devices = queue.Queue()
    devices.put(1)
    env = {'VIGIL_GPU_DEVICE': '99'}
    code = "import os; print(os.environ['VIGIL_GPU_DEVICE']); raise SystemExit(7)"
    assert run_episode_process([sys.executable, '-c', code], stdout_path=tmp_path/'out',
                               stderr_path=tmp_path/'err', timeout_s=5,
                               env=env, device_pool=devices) == 7
    assert (tmp_path/'out').read_text().strip() == '1'
    assert devices.get_nowait() == 1
    assert env['VIGIL_GPU_DEVICE'] == os.environ['VIGIL_GPU_DEVICE'] == '99'


def test_waiting_for_renderer_device_can_be_cancelled(tmp_path):
    from vigil.eval.process import _device_slot
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt('cancelled')
    with pytest.raises(KeyboardInterrupt):
        with _device_slot(queue.Queue(), cancel):
            pytest.fail('empty pool must not grant a renderer device')

CHILD = """import argparse, json, os, time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--startup-ready-file',type=Path)
p.add_argument('--events',type=Path)
p.add_argument('--fail',action='store_true')
a=p.parse_args()
def event(kind):
 fd=os.open(a.events,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
 os.write(fd,(json.dumps({'kind':kind,'time':time.monotonic(),'pid':os.getpid()})+'\\n').encode())
 os.close(fd)
event('start')
if a.fail:
 event('exit_before_ready')
 raise SystemExit(7)
time.sleep(.12)
event('ready')
a.startup_ready_file.touch()
time.sleep(.35)
event('end')
"""


def run_child(tmp_path, script, index, boot, render, *extra, timeout=5):
    return run_episode_process(
        [
            sys.executable,
            str(script),
            "--events",
            str(tmp_path / "events.jsonl"),
            *extra,
        ],
        stdout_path=tmp_path / f"{index}.stdout",
        stderr_path=tmp_path / f"{index}.stderr",
        timeout_s=timeout,
        boot_gate=boot,
        render_gate=render,
    )


@pytest.mark.parametrize("boot_limit,render_limit", [(1, 2), (2, 1), (2, 3)])
def test_real_children_obey_both_limits_and_boot_slots_release_early(
    tmp_path, boot_limit, render_limit
):
    script = tmp_path / "child.py"
    script.write_text(CHILD)
    boot = threading.Semaphore(boot_limit)
    render = threading.Semaphore(render_limit)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda i: run_child(tmp_path, script, i, boot, render), range(4))
        )
    assert results == [0] * 4
    events = sorted(
        (json.loads(s) for s in (tmp_path / "events.jsonl").read_text().splitlines()),
        key=lambda e: e["time"],
    )
    starting = alive = peak_boot = peak_alive = 0
    for e in events:
        if e["kind"] == "start":
            starting += 1
            alive += 1
        elif e["kind"] == "ready":
            starting -= 1
        elif e["kind"] == "end":
            alive -= 1
        peak_boot = max(peak_boot, starting)
        peak_alive = max(peak_alive, alive)
    assert peak_boot <= boot_limit
    assert peak_alive <= render_limit
    assert peak_alive == render_limit
    assert starting == alive == 0


def test_early_child_failure_releases_startup_and_render_slots(tmp_path):
    script = tmp_path / "child.py"
    script.write_text(CHILD)
    boot = threading.Semaphore(1)
    render = threading.Semaphore(1)
    assert run_child(tmp_path, script, 0, boot, render, "--fail") == 7
    assert run_child(tmp_path, script, 1, boot, render) == 0


def test_cancelled_queue_never_starts_a_child(tmp_path, monkeypatch):
    cancelled = threading.Event()
    cancelled.set()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("cancelled work started a process"))
    with pytest.raises(KeyboardInterrupt):
        run_episode_process([sys.executable, "-c", "pass"], stdout_path=tmp_path / "out",
                            stderr_path=tmp_path / "err", timeout_s=60, cancel_event=cancelled)


@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX")
def test_cancellation_stops_the_live_child_and_releases_slots(tmp_path):
    import time
    script = tmp_path / "cancellable.py"
    script.write_text(CHILD.replace("time.sleep(.35)", "time.sleep(60)"))
    cancel = threading.Event()
    boot, render = threading.Semaphore(1), threading.Semaphore(1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run_episode_process, [sys.executable, str(script), "--events", str(tmp_path / "events.jsonl")],
                             stdout_path=tmp_path / "out", stderr_path=tmp_path / "err", timeout_s=120,
                             boot_gate=boot, render_gate=render, cancel_event=cancel)
        deadline = time.monotonic() + 5
        events = tmp_path / "events.jsonl"
        while not events.exists() or '"ready"' not in events.read_text():
            assert time.monotonic() < deadline
            time.sleep(.02)
        pid = json.loads(events.read_text().splitlines()[0])["pid"]
        cancel.set()
        with pytest.raises(KeyboardInterrupt):
            future.result(timeout=5)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert boot.acquire(blocking=False) and render.acquire(blocking=False)


@pytest.mark.skipif(os.name != "posix", reason="process-group cleanup requires POSIX")
@pytest.mark.parametrize("render_limit", [1, 2])
def test_timeout_kills_descendants_and_queue_wait_does_not_consume_timeout(
    tmp_path, render_limit
):
    import time

    script = tmp_path / "stubborn.py"
    script.write_text("""import os, signal, time, json
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=os.fork()
if child:
 Path(__file__).with_suffix('.pids').write_text(json.dumps([os.getpid(),child]))
 print('startup began',flush=True)
while True:time.sleep(1)
""")
    normal = tmp_path / "normal.py"
    normal.write_text(
        "from pathlib import Path\nimport json\n"
        f"for pid in json.loads(Path({str(script.with_suffix('.pids'))!r}).read_text()):\n"
        " stat = Path(f'/proc/{pid}/stat')\n"
        " assert not stat.exists() or stat.read_text().split()[2] == 'Z', 'startup slot released before cleanup'\n"
        + CHILD
    )
    boot = threading.Semaphore(1)
    render = threading.Semaphore(render_limit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        stuck = pool.submit(run_child, tmp_path, script, 0, boot, render, timeout=0.5)
        deadline = time.monotonic() + 5
        while not script.with_suffix(".pids").exists():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        queued = pool.submit(run_child, tmp_path, normal, 1, boot, render, timeout=1)
        with pytest.raises(subprocess.TimeoutExpired):
            stuck.result(timeout=6)
        assert queued.result(timeout=6) == 0
    assert "startup began" in (tmp_path / "0.stdout").read_text()
    for pid in json.loads(script.with_suffix(".pids").read_text()):
        stat = Path(f"/proc/{pid}/stat")
        assert not stat.exists() or stat.read_text().split()[2] == "Z"
