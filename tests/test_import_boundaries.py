"""Verify actual cold imports, not only textual import statements."""
import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]

GUARD = '''
import importlib.abc, sys
class ForbidOptionalRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = ("ai2thor", "prior", "numpy", "torch", "PIL", "requests")
        if fullname.split(".")[0] in forbidden:
            raise AssertionError("Unexpected optional runtime import: " + fullname)
sys.meta_path.insert(0, ForbidOptionalRuntime())
'''


def cold_run(code, tmp_path):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("VIGIL_") and k not in {"OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"}}
    env.update(PYTHONPATH=str(ROOT), PYTHONNOUSERSITE="1")
    result = subprocess.run([sys.executable, "-c", GUARD + code], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("code", [
    "import vigil\nassert 'vigil.agent' not in sys.modules and 'vigil.eval' not in sys.modules",
    "from vigil import AgentObservation, ActionCall\nassert 'vigil.eval' not in sys.modules and 'vigil.envs' not in sys.modules",
    "from vigil.agent.model import OpenAIModelAgent\nassert 'vigil.eval' not in sys.modules and 'vigil.envs' not in sys.modules",
    "from vigil.eval.state import prepare_run\nassert 'vigil.eval.runner' not in sys.modules and 'vigil.envs.thor' not in sys.modules",
    "from vigil.data.conditions import evaluate_episode\nassert 'vigil.eval' not in sys.modules and 'vigil.envs' not in sys.modules",
    "from vigil.envs.thor import PublicThorEnv\nassert 'vigil.eval' not in sys.modules",
    "from vigil.cli import main\nassert main(['--help']) == 0",
])
def test_cold_imports_do_not_load_unrelated_runtime(code, tmp_path):
    cold_run(code, tmp_path)


@pytest.mark.parametrize("arguments", [
    ["validate-pack"],
    ["catalog", "--task-family", "PG", "--max-episodes", "1"],
    ["list-episodes", "--task-family", "SV", "--max-episodes", "1"],
    ["verify-run", str(ROOT / "vigil/web/demo"), "--require-frames"],
    ["run", "--dry-run", "--max-episodes", "1", "--out-dir", "selection"],
])
def test_offline_cli_never_imports_simulator_or_episode_runtime(arguments, tmp_path):
    code = f'''
from vigil.cli import main
assert main({["--no-config", *arguments]!r}) == 0
assert "vigil.envs.thor" not in sys.modules
assert "vigil.eval.runner" not in sys.modules
'''
    cold_run(code, tmp_path)


def test_recorded_workbench_can_load_when_simulator_import_is_broken(tmp_path):
    cold_run('''
from pathlib import Path
from vigil.web.app import Workbench
app = Workbench(config=Path("absent.json"), results=Path("read"), out_dir=Path("write"))
app.discover_runs()
assert len(app.run_detail("demo")["episodes"]) == 2
assert app.process is None
assert "vigil.eval.runner" not in sys.modules and "vigil.envs.thor" not in sys.modules
''', tmp_path)


def test_lower_layers_never_depend_on_execution_or_ui():
    # Check imports inside functions too; a local import must not hide a cycle.
    forbidden = {
        "agent": ("vigil.eval", "vigil.envs", "vigil.web", "vigil.cli", "vigil.data.conditions"),
        "data": ("vigil.eval", "vigil.envs", "vigil.web", "vigil.cli", "vigil.agent"),
        "envs": ("vigil.eval", "vigil.web", "vigil.cli", "vigil.agent"),
        "eval": ("vigil.web", "vigil.cli"),
    }
    for layer, prefixes in forbidden.items():
        for path in (ROOT / "vigil" / layer).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                modules = [node.module or ""] if isinstance(node, ast.ImportFrom) else [x.name for x in node.names] if isinstance(node, ast.Import) else []
                assert all(not name.startswith(prefixes) for name in modules), (path, modules)


def test_source_layout_has_one_explicit_package():
    assert (ROOT / "vigil/agent/model.py").is_file()
    assert not (ROOT / "src").exists()
    assert not (ROOT / "vigil/_compat.py").exists()
