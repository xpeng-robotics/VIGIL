"""Exercise disclosure detection through the public artifact-checking entry point."""
import base64
import json
import sys
import warnings
import zipfile
from urllib.parse import quote

import pytest

from scripts.release.check_public_release import known_private_values, main, scan_bytes


@pytest.mark.parametrize("name,allowed", [("requirements.txt", True),
                                         ("constraints-macos-x86_64.txt", True), ("settings.txt", False)])
def test_four_part_package_version_is_not_an_endpoint(name, allowed):
    version = ".".join(("4", "13", "0", "92"))
    findings = scan_bytes(name, ("opencv-python==" + version + "\n").encode())
    assert bool(findings) is not allowed


@pytest.mark.parametrize("line", ["# endpoint: http://{ip}/api", "index-url=https://{ip}/simple"])
def test_constraints_file_still_rejects_addresses_in_comments_and_urls(line):
    address = ".".join(("10", "24", "36", "48"))
    findings = scan_bytes("constraints.txt", line.format(ip=address).encode())
    assert any(hit["category"] == "ip_address" for hit in findings)


def test_version_context_never_suppresses_a_known_private_value():
    value = ".".join(("10", "24", "36", "48")).encode()
    findings = scan_bytes("requirements.txt", b"package==" + value, known_values=(value,))
    assert any(hit["category"] == "known_private_value" for hit in findings)


def private_config(tmp_path):
    key = "opaque-" + "credential0123456789" + "/a b"
    endpoint = "https://" + "company-gateway.test" + "/model/v1"
    path = tmp_path / "private.json"
    path.write_text(json.dumps({"api_key": key, "base_url": endpoint}))
    return path, key, endpoint


@pytest.mark.parametrize("encoding", ["plain", "percent", "base64", "json_escape"])
def test_actual_configuration_values_are_matched_without_disclosing_them(tmp_path, encoding):
    path, key, endpoint = private_config(tmp_path)
    for value in (key, endpoint):
        raw = {
            "plain": value,
            "percent": quote(value, safe=""),
            "base64": base64.b64encode(value.encode()).decode(),
            "json_escape": '"' + "".join("\\u%04x" % ord(c) for c in value) + '"',
        }[encoding].encode()
        name = "evidence.json" if encoding == "json_escape" else "evidence.txt"
        findings = scan_bytes(name, raw, known_values=known_private_values([path]))
        assert any(hit["category"] == "known_private_value" for hit in findings)
        assert value not in json.dumps(findings)


@pytest.mark.parametrize("kind", ["quoted_env", "access_token", "encoded_address", "double_encoded_address"])
def test_patterns_detect_additional_disclosure_forms(kind):
    address = ".".join(("10", "24", "36", "48"))
    encoded = "".join("%%%02X" % ord(c) for c in address)
    raw = {
        "quoted_env": "VIGIL_API_KEY='" + "opaque0123456789" * 2 + "' # private",
        "access_token": "glpat-" + "synthetic0123456789" * 2,
        "encoded_address": encoded,
        "double_encoded_address": quote(encoded, safe=""),
    }[kind]
    findings = scan_bytes("settings.txt", raw.encode())
    assert findings
    assert raw not in json.dumps(findings)


def test_cli_media_list_and_symlinks_do_not_echo_sensitive_filenames(tmp_path, monkeypatch, capsys):
    config, _, endpoint = private_config(tmp_path)
    # An arbitrary credential without a recognizable provider prefix.
    key = "opaque" + "0123456789" * 2
    config.write_text(json.dumps({"api_key": key, "base_url": endpoint}))
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / (key + ".jpg")).write_bytes(b"placeholder image")
    (candidate / (key + ".txt")).symlink_to("missing")
    monkeypatch.setattr(sys, "argv", ["check", str(candidate), "--private-config", str(config)])
    assert main() == 1
    output = capsys.readouterr().out
    report = json.loads(output)
    assert key not in output
    assert report["visual_review_required"][0].startswith("[redacted-path-")
    assert {hit["category"] for hit in report["findings"]} >= {"known_private_value", "symlink"}


@pytest.mark.parametrize("kind", ["parent", "absolute", "windows", "symlink", "duplicate"])
def test_cli_rejects_unsafe_zip_entries(tmp_path, monkeypatch, capsys, kind):
    archive = tmp_path / "release.zip"
    name = {"parent": "../private.txt", "absolute": "/private.txt", "windows": "C:\\private.txt"}.get(kind, "entry.txt")
    with zipfile.ZipFile(archive, "w") as handle:
        info = zipfile.ZipInfo(name)
        if kind == "symlink":
            info.create_system = 3
            info.external_attr = 0o120777 << 16
        handle.writestr(info, b"content")
        if kind == "duplicate":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                handle.writestr(name, b"duplicate")
    monkeypatch.setattr(sys, "argv", ["check", str(archive)])
    assert main() == 1
    report = json.loads(capsys.readouterr().out)
    assert all(hit["category"] == "unsafe_archive" for hit in report["findings"])


def test_cli_matches_known_credentials_inside_zip(tmp_path, monkeypatch, capsys):
    config, key, _ = private_config(tmp_path)
    archive = tmp_path / "release.zip"
    encoded = base64.b64encode(key.encode())
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("release/readme.txt", encoded)
    monkeypatch.setattr(sys, "argv", ["check", str(archive), "--private-config", str(config)])
    assert main() == 1
    output = capsys.readouterr().out
    assert key not in output and encoded.decode() not in output
    assert json.loads(output)["findings"][0]["category"] == "known_private_value"


def test_unreadable_private_config_fails_without_echoing_filename(tmp_path, monkeypatch, capsys):
    sensitive_name = "sk-" + "synthetic0123456789" * 2
    monkeypatch.setattr(sys, "argv", ["check", str(tmp_path), "--private-config", str(tmp_path / sensitive_name)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr().err
    assert sensitive_name not in output
    assert "Unable to read private JSON" in output
