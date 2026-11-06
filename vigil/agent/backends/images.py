"""Lossless image transport; provider adapters must preserve the same bytes."""
from __future__ import annotations

import base64
import binascii
import hashlib
import struct


def data_image(url: object) -> tuple[str, str]:
    if not isinstance(url, str) or not url.startswith("data:") or "," not in url:
        raise ValueError("Model images must be inline base64 data URLs; refusing to drop an image.")
    header, encoded = url.split(",", 1)
    mime = header[5:].removesuffix(";base64")
    if not header.endswith(";base64") or mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        raise ValueError("Unsupported inline image format.")
    try:
        if not base64.b64decode(encoded, validate=True):
            raise ValueError("Empty image.")
    except (ValueError, binascii.Error):
        raise ValueError("Invalid base64 image.") from None
    return mime, encoded


def image_evidence(messages: list[dict]) -> dict | None:
    """Record input bytes and dimensions, never credentials or the image itself."""
    for message in reversed(messages):
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") != "image_url":
                continue
            info = part["image_url"]
            mime, encoded = data_image(info.get("url"))
            raw = base64.b64decode(encoded)
            result = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                      "mime_type": mime, "transform": "none", "detail": info.get("detail", "default")}
            if raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) >= 24:
                result["width"], result["height"] = struct.unpack(">II", raw[16:24])
            return result
    return None
