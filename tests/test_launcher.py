"""The source launcher must open without installation or a fixed free port."""
import json
import os
from pathlib import Path
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]


def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith("VIGIL_") and k not in {"PYTHON_BIN", "PYTHONPATH", "VIRTUAL_ENV",
                "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"}}


@pytest.mark.parametrize("launcher", ["start.sh", "start.command"])
def test_source_launcher_from_another_directory_without_configuration(tmp_path, launcher):
    env = {**clean_env(), "PYTHON_BIN": sys.executable, "VIGIL_DATA_ROOT": str(tmp_path / "no-data")}
    output = tmp_path / "no-output"
    config = tmp_path / "no-config.json"
    process = subprocess.Popen(["bash", str(ROOT / launcher), "--no-open", "--config", str(config),
                                "--results-dir", str(output)], cwd=tmp_path, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               start_new_session=True)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(15), "Launcher did not print a URL."
        line = process.stdout.readline().strip()
        assert line.startswith("VIGIL workbench: http://127.0.0.1:"), line
        url = line.split(": ", 1)[1]
        with urllib.request.urlopen(url + "/api/bootstrap", timeout=10) as response:
            payload = json.load(response)
        assert not payload["episodes"]
        assert any(row["demo"] for row in payload["runs"])
        assert "api_key" not in payload["config"]
        assert not output.exists() and not config.exists()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def test_launcher_finds_supported_python_when_system_python_is_old(tmp_path):
    release = tmp_path / "release with spaces"
    release.mkdir()
    shutil.copy2(ROOT / "start.sh", release / "start.sh")
    (release / "vigil").symlink_to(ROOT / "vigil", target_is_directory=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").write_text("#!/bin/sh\nexit 1\n")
    (bin_dir / "python3.10").write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n")
    for path in bin_dir.iterdir():
        path.chmod(0o755)
    env = {**clean_env(), "PATH": f"{bin_dir}:/usr/bin:/bin"}
    result = subprocess.run(["bash", str(release / "start.sh"), "--help"], env=env,
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "--results-dir" in result.stdout


def test_explicit_missing_python_produces_a_useful_message(tmp_path):
    env = {**clean_env(), "PYTHON_BIN": str(tmp_path / "missing-python")}
    result = subprocess.run(["bash", str(ROOT / "start.sh"), "--no-open"], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "Python 3.10+" in result.stderr and "PYTHON_BIN" in result.stderr
