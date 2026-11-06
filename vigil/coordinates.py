"""The historical image-coordinate contract shared by prompts and execution."""
from __future__ import annotations

from vigil.actions import coerce_numeric_argument


def coordinate_mode(value: str | None) -> str:
    mode = str(value or "pixel").strip().lower() or "pixel"
    if mode not in {"pixel", "normalized_1000"}:
        raise ValueError("coord_mode must be pixel or normalized_1000 (empty means pixel).")
    return mode


def coordinate_prompt_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if mode not in {"", "explicit", "none", "off", "disabled"}:
        raise ValueError("coord_prompt_mode must be explicit or none (empty uses the historical default).")
    return mode


def scale_normalized_1000(value: int, size: int) -> int:
    if size <= 1:
        return 0
    return int(round((float(value) / 1000.0) * float(size - 1)))


def adapt_pixel_arguments(arguments: dict, *, mode: str | None, width: int, height: int) -> tuple[dict, dict | None]:
    """Round the model value first, then scale once; never clamp or guess units."""
    executed = dict(arguments)
    if arguments.get("intent") == "drop":
        return executed, None
    x = int(round(coerce_numeric_argument(arguments["x"])))
    y = int(round(coerce_numeric_argument(arguments["y"])))
    executed.update(x=x, y=y)
    if coordinate_mode(mode) == "pixel":
        return executed, None
    executed.update(x=scale_normalized_1000(x, width), y=scale_normalized_1000(y, height))
    return executed, {
        "adapter": "normalized_1000_to_pixel", "coord_mode": "normalized_1000",
        "input": {"x": x, "y": y}, "output": {"x": executed["x"], "y": executed["y"]},
        "image_size": {"width": width, "height": height},
    }
