from __future__ import annotations

from collections.abc import Iterable
from typing import Any

BLACK_FRAME_MEAN_THRESHOLD = 5.0
BLACK_PIXEL_RATIO_THRESHOLD = 0.98


def _shape_of(image: Any) -> str:
    shape = getattr(image, "shape", None)
    if shape is not None:
        return str(tuple(int(item) for item in shape))
    try:
        return str((len(image), len(image[0])))
    except Exception:
        return "unknown"


def _flatten_values(value: Any) -> Iterable[float]:
    if isinstance(value, (str, bytes)):
        return
    if isinstance(value, Iterable):
        for item in value:
            yield from _flatten_values(item)
        return
    try:
        yield float(value)
    except (TypeError, ValueError):
        return


def black_frame_stats(image: Any) -> dict[str, Any] | None:
    if image is None:
        return None
    try:
        import numpy as np

        arr = np.asarray(image)
        if arr.ndim < 2 or arr.size == 0:
            return None
        black_values = int((arr <= 1).sum())
        return {
            "mean_pixel": float(arr.mean()),
            "black_pixel_ratio": float(black_values) / float(arr.size),
            "shape": _shape_of(arr),
        }
    except Exception:
        values = list(_flatten_values(image))
        if not values:
            return None
        black_values = sum(1 for item in values if item <= 1.0)
        return {
            "mean_pixel": sum(values) / float(len(values)),
            "black_pixel_ratio": float(black_values) / float(len(values)),
            "shape": _shape_of(image),
        }


def is_black_frame(
    image: Any,
    *,
    threshold_mean: float = BLACK_FRAME_MEAN_THRESHOLD,
    threshold_ratio: float = BLACK_PIXEL_RATIO_THRESHOLD,
) -> bool:
    stats = black_frame_stats(image)
    if stats is None:
        return False
    return float(stats["mean_pixel"]) < threshold_mean or float(stats["black_pixel_ratio"]) >= threshold_ratio
