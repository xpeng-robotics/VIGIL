from __future__ import annotations

import json
from pathlib import Path
import struct
from urllib.parse import quote
import zlib

import pytest

from scripts.release.check_public_release import scan_bytes, text_findings
from scripts.release.export_recorded_example import check_public
from vigil.agent.backends.base import ModelBackendConfig
from vigil.security import redact
from vigil.web.app import Workbench


def fake_key():
    return "sk-" + "synthetic0123456789" * 2


@pytest.mark.parametrize("value", [
    lambda: fake_key(),
    lambda: ".".join(("10", "24", "36", "48")),
    lambda: ":".join(("fd00", "", "42")),
    lambda: "worker." + "internal",
    lambda: "/".join(("", "Users", "someone", "private.json")),
])
def test_release_scan_detects_sensitive_text_without_echoing_it(value):
    value = value()
    findings = scan_bytes("example.txt", value.encode())
    assert findings
    assert value not in json.dumps(findings)
    with pytest.raises(ValueError, match="Possible private") as error:
        check_public({"model_output": value})
    assert value not in str(error.value)


def test_local_and_documentation_addresses_are_portable():
    assert not text_findings("http://localhost:8000 http://127.0.0.1:8000 0.0.0.0 192.0.2.10 2001:db8::1")


@pytest.mark.parametrize("name", ["apiKey", "accessToken", "Authorization", "client-secret", "baseUrls"])
def test_recorded_export_rejects_transport_field_variants(name):
    with pytest.raises(ValueError, match="Private transport field"):
        check_public({"nested": [{name: "value"}]})


def test_json_escapes_do_not_hide_credentials():
    raw = json.dumps({"apiKey": "".join(chr(97+i) for i in range(24))}).replace("apiKey", "api\\u004bey")
    assert any(h["category"] == "credential_field" for h in scan_bytes("example.json", raw.encode()))


def test_private_files_and_unquoted_environment_keys_are_rejected():
    assert scan_bytes(".env.production", b"")[0]["category"] == "private_file"
    assert scan_bytes("local.txt", ("VIGIL_API_KEY=" + "a1b2c3d4" * 5).encode())
    findings = scan_bytes(fake_key() + ".txt", b"")
    assert findings and fake_key() not in json.dumps(findings)


def test_compressed_png_metadata_is_checked():
    payload = b"Comment\0\0" + zlib.compress(fake_key().encode())
    chunk = b"zTXt" + payload
    raw = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(payload)) + chunk + struct.pack(">I", zlib.crc32(chunk))
    findings = scan_bytes("frame.png", raw)
    assert any(h["category"] == "credential" for h in findings)
    assert fake_key() not in json.dumps(findings)


@pytest.mark.parametrize("source", ["userinfo", "query", "pool", "nested_body"])
def test_credentials_cannot_reach_metadata_or_worker_arguments(source):
    key = fake_key()
    settings = {"base_url": "https://gateway.example/v1", "model": "m"}
    if source == "userinfo":
        settings["base_url"] = "https://user:" + key + "@gateway.example/v1"
    elif source in {"query", "pool"}:
        url = settings["base_url"] + "?api_key=" + key
        settings["base_url" if source == "query" else "base_urls"] = url if source == "query" else (url,)
    else:
        settings["extra_body"] = {"options": [{"accessToken": key}]}
    with pytest.raises(ValueError, match="Use api_key") as error:
        ModelBackendConfig(**settings)
    assert key not in str(error.value)


def test_config_repr_and_workbench_hide_nested_and_encoded_secrets(tmp_path):
    key = fake_key() + "/a b"
    secondary = "second-" + "credential0123456789"
    cfg = ModelBackendConfig(base_url="https://gateway.example/v1", model="m", api_key=key)
    assert key not in repr(cfg)
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"api_key": key, "extra_body": {"nested": {"accessToken": secondary}},
                                "base_url": "https://gateway.example/v1?key=" + quote(secondary)}))
    app = Workbench(config=path, results=tmp_path / "results")
    result = json.dumps(app.public_config())
    for secret in (key, secondary):
        assert secret not in result and quote(secret, safe="") not in result
    assert key not in app.redact(quote(key, safe=""))
    assert redact({"accessToken": secondary, "echo": secondary}) == {
        "accessToken": "[REDACTED]", "echo": "[REDACTED]"}
