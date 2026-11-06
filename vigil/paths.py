"""Locate this package and its optional source-release assets."""
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent


def source_root() -> Path | None:
    root = PACKAGE_ROOT.parent
    if (root / "pyproject.toml").is_file() and (root / "start.sh").is_file():
        return root
    return None
