"""Exercise the shell entrypoint without installing packages or calling an API."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def quickstart(tmp_path):
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['QUICKSTART_TEST_LOG'], 'a') as log:\n"
        "    log.write(json.dumps({'args': args, 'platform': os.getenv('VIGIL_THOR_PLATFORM')}) + '\\n')\n"
        "if args == ['-c', 'import pytest'] or args[:2] == ['-m', 'pytest']:\n"
        "    sys.exit(int(os.environ.get('QUICKSTART_TEST_PYTEST_STATUS', '0')))\n"
        "if args[:3] == ['-m', 'vigil.cli', 'smoke']:\n"
        "    sys.exit(int(os.environ.get('QUICKSTART_TEST_SMOKE_STATUS', '0')))\n"
    )
    python.chmod(0o755)
    uname = bin_dir / "uname"
    uname.write_text('#!/bin/sh\nprintf "%s\\n" "$QUICKSTART_TEST_OS"\n')
    uname.chmod(0o755)
    log = tmp_path / "calls.jsonl"
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("VIGIL_") and key != "DISPLAY"}
    env.update(
        PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        PYTHON_BIN=str(python),
        VIGIL_USE_CONDA="0",
        VIGIL_VENV_DIR=str(bin_dir.parent),
        QUICKSTART_TEST_LOG=str(log),
        QUICKSTART_TEST_OS="Linux",
        QUICKSTART_TEST_PYTEST_STATUS="23",
    )

    def run(mode, *args, **overrides):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/deploy/quickstart.sh"), mode, *args],
            env={**env, **overrides}, capture_output=True, text=True, timeout=10,
        )
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        return result, calls

    return run


@pytest.mark.parametrize("environment, expected", [
    ({}, "cloud"),
    ({"DISPLAY": ":0"}, None),
    ({"QUICKSTART_TEST_OS": "Darwin"}, None),
    ({"VIGIL_THOR_PLATFORM": "default"}, "default"),
    ({"VIGIL_THOR_PLATFORM": ""}, ""),
])
def test_smoke_installs_runtime_only_and_preserves_rendering_choice(quickstart, environment, expected):
    flags = ["--no-config", "--base-url", "http://example.invalid:28080/v1",
             "--model", "my-vlm", "--out-dir", "outputs/first run"]
    result, calls = quickstart("--smoke", *flags, **environment)
    assert result.returncode == 0, result.stderr
    assert ["-m", "pip", "install", "-e", ".[thor]"] in [call["args"] for call in calls]
    assert not any("pytest" in " ".join(call["args"]) for call in calls)
    assert calls[-1]["args"] == ["-m", "vigil.cli", "smoke", "--pack-file", "canonical",
                                  "--out-dir", "outputs/smoke", *flags]
    assert calls[-1]["platform"] == expected


def test_check_keeps_developer_tests_before_dry_run(quickstart):
    result, calls = quickstart("--check", QUICKSTART_TEST_PYTEST_STATUS="0")
    assert result.returncode == 0, result.stderr
    assert ["-m", "pip", "install", "-e", ".[dev]"] in [call["args"] for call in calls]
    assert calls[-2]["args"] == ["-m", "pytest", "-p", "no:cacheprovider"]
    assert calls[-1]["args"][:3] == ["-m", "vigil.cli", "run-pack"]
    assert "--dry-run" in calls[-1]["args"]
    assert all(call["platform"] is None for call in calls)


def test_check_stops_when_pytest_is_missing(quickstart):
    result, calls = quickstart("--check")
    assert result.returncode == 2
    assert "pytest is missing" in result.stderr
    assert not any(call["args"][:2] == ["-m", "vigil.cli"] for call in calls)


def test_prepared_smoke_needs_no_install_or_pytest_and_propagates_failure(quickstart):
    result, calls = quickstart("--smoke", VIGIL_SKIP_INSTALL="1", QUICKSTART_TEST_SMOKE_STATUS="7")
    assert result.returncode == 7
    assert not any(call["args"][:2] in (["-m", "pip"], ["-m", "pytest"])
                   or call["args"] == ["-c", "import pytest"] for call in calls)
    assert calls[-1]["args"][:3] == ["-m", "vigil.cli", "smoke"]
