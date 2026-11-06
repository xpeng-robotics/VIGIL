"""Small JSON model configuration shared by the CLI entry points."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from vigil.agent.backends.base import ModelBackendConfig
from vigil.security import validate_auth_placement

DEFAULT_CONFIG = "vigil.json"
MODEL_ARGUMENTS = {
    "backend": "backend", "base_url": "base_url", "model": "model",
    "api_key": "api_key", "api_key_header": "api_key_header", "timeout": "timeout_s",
    "temperature": "temperature", "top_p": "top_p", "top_k": "top_k",
    "max_tokens": "max_tokens", "coord_mode": "coord_mode", "coord_prompt_mode": "coord_prompt_mode",
    "request_extra_body_json": "extra_body", "supports_json_mode": "supports_json_mode",
    "max_tokens_field": "max_tokens_field", "image_detail": "image_detail",
    "request_max_retries": "request_max_retries", "request_retry_delay_s": "request_retry_delay_s",
    "protocol_retry_limit": "protocol_retry_limit", "observation_echo_retry_limit": "observation_echo_retry_limit",
}


def create_config(path: Path, backend: str = "openai-compatible", *, model: str | None = None,
                  base_url: str | None = None) -> Path:
    """Create a local template without replacing any existing settings."""
    template = {"backend": backend, "model": "", "api_key": ""}
    if backend in {"openai-compatible", "vllm"}:
        template = {"backend": backend, "base_url": "http://127.0.0.1:8000/v1", "model": "", "api_key": ""}
    if model is not None:
        if not model.strip():
            raise ValueError("Model must not be empty. Use your provider's model identifier.")
        template["model"] = model.strip()
    if base_url is not None:
        validate_auth_placement((base_url,), {})
        try:
            url = urlsplit(base_url.strip())
            valid = url.scheme in {"http", "https"} and bool(url.hostname) and not url.fragment
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("Base URL must be an HTTP or HTTPS endpoint without a fragment.")
        template["base_url"] = base_url.strip()
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"Configuration already exists: {path}. Edit it or choose another path with vigil init PATH.") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(template, indent=2) + "\n")
    return path


def apply_model_config(args) -> None:
    """Apply file values below explicit CLI options and above environment values."""
    if getattr(args, "no_config", False):
        return
    explicit_path = getattr(args, "config", None)
    path = Path(explicit_path or DEFAULT_CONFIG).expanduser().resolve()
    if not path.exists() and explicit_path is None:
        return
    if not path.is_file():
        raise ValueError(f"Configuration file not found: {path}. Create it with vigil init PATH.")
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path.name}, line {exc.lineno}, column {exc.colno}: {exc.msg}.") from exc
    apply_config_values(args, values, path.name)
    args.config = path


def apply_config_values(args, values: dict, label: str = "Model settings") -> None:
    """Validate and apply file or UI settings through the same configuration path."""
    if not isinstance(values, dict):
        raise ValueError(f"{label} must contain a JSON object with model settings.")
    names = {key: key for key in MODEL_ARGUMENTS}
    names["extra_body"] = "request_extra_body_json"
    unknown = sorted(set(values) - set(names))
    if unknown:
        raise ValueError(f"Unknown setting in {label}: {', '.join(unknown)}. Supported settings: {', '.join(sorted(names))}.")
    if "extra_body" in values and "request_extra_body_json" in values:
        raise ValueError(f"Use only extra_body in {label}, not both extra body spellings.")
    integer_fields = {"timeout", "max_tokens", "top_k", "request_max_retries", "protocol_retry_limit", "observation_echo_retry_limit"}
    float_fields = {"temperature", "top_p", "request_retry_delay_s"}
    for key, value in values.items():
        name = names[key]
        if name == "api_key" and value in (None, ""):
            continue  # An empty template key may use a provider key from the environment.
        if name in integer_fields:
            valid = type(value) is int or (name == "top_k" and value is None)
            expected = "an integer" + (" or null" if name == "top_k" else "")
        elif name in float_fields:
            valid = type(value) in (int, float) or (value is None and name != "request_retry_delay_s")
            expected = "a number or null"
        elif name == "request_extra_body_json":
            valid, expected = isinstance(value, dict), "a JSON object"
        elif name == "supports_json_mode":
            valid = type(value) is bool or (type(value) is int and value in (0, 1))
            expected = "true or false"
        else:
            valid, expected = isinstance(value, str), "a string"
        if not valid:
            raise ValueError(f"{label}: {key} must be {expected}.")
        if not hasattr(args, name):
            setattr(args, name, value)
    # A file selecting a native provider can use its default URL even if the
    # shell previously configured a different provider's endpoint.
    if "backend" in values and getattr(args, "backend", "") in {"openai", "gemini", "anthropic", "claude"}:
        if not hasattr(args, "base_url"):
            args.base_url = ""


def _model_config_metadata(config: ModelBackendConfig) -> dict[str, Any]:
    return {
        "backend": config.backend,
        "base_url": config.base_url,
        "base_urls": list(config.base_urls),
        "model": config.model,
        "api_key_header": config.api_key_header,
        "timeout_s": config.timeout_s,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "top_k": config.top_k,
        "max_tokens": config.max_tokens,
        "max_tokens_field": config.max_tokens_field,
        "image_detail": config.image_detail,
        "request_max_retries": config.request_max_retries,
        "request_retry_delay_s": config.request_retry_delay_s,
        "coord_mode": config.coord_mode,
        "coord_prompt_mode": config.coord_prompt_mode,
        "supports_json_mode": config.supports_json_mode,
        "extra_body": dict(config.extra_body),
        "protocol_retry_limit": config.protocol_retry_limit,
        "observation_echo_retry_limit": config.observation_echo_retry_limit,
    }


def _model_config_from_args(args: argparse.Namespace) -> ModelBackendConfig:
    return ModelBackendConfig.from_env(**{field: getattr(args, name) for name, field in MODEL_ARGUMENTS.items() if hasattr(args, name)})
