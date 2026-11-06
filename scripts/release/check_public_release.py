#!/usr/bin/env python3
"""Check an exported directory, ZIP or wheel for private material without printing it.

This offline gate scans text, decoded JSON and printable binary metadata. It is
not OCR, a license audit or a guarantee that arbitrary secrets can be recognized.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sys
import zipfile
import zlib
from urllib.parse import quote, quote_plus, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from vigil.security import credential_values, secret_field

TOKEN = re.compile(r"\b(?:sk-|ah-|glpat-|gh[pousr]_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{16,}|\bAKIA[A-Z0-9]{16}\b|\bAIza[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
PERSONAL_PATH = re.compile(r"/(?:Users|home|workspace|dataset_rc)/[^\s\"'<>]+|[A-Za-z]:\\Users\\[^\s\"'<>]+")
PRIVATE_HOST = re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+(?:internal|corp|local)\b")
# Split organization identifiers so the policy itself is not a published endpoint.
PRIVATE_TERMS = ("xiao" + "peng", "x-" + "peng", "fu" + "yao", "lu" + "ban",
                 "infra" + "-registry", "rc-" + "llmrl", "rc-" + "embodied", "peng" + "-us.com")
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
PACKAGE_PIN = re.compile(r"(?m)^[ \t]*[A-Za-z0-9][A-Za-z0-9_.-]*[ \t]*==[ \t]*(\d+(?:\.\d+){3})[ \t]*$")
IPV6 = re.compile(r"(?<![\w:])[a-fA-F0-9]{1,4}:(?:[a-fA-F0-9]{0,4}:)+[a-fA-F0-9:.%]*(?![\w:])")
AUTH_LITERAL = re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization)[\"']?\s*[:=]\s*[\"']([^\"'\n]{16,})[\"']")
ENV_SECRET = re.compile(r"(?m)^\s*(?:export\s+)?[A-Z_]*(?:API_KEY|ACCESS_TOKEN|SECRET|PASSWORD)\s*=\s*[\"']?[A-Za-z0-9_+/=.-]{16,}[\"']?\s*(?:#.*)?$")
AUTH_URL = re.compile(r"(?i)https?://[^\s/]+@|[?&](?:api[_-]?key|key|access[_-]?token|token|signature|x-amz-signature)=[A-Za-z0-9_%][^\s&\"'<>]*")
SAFE_NETWORKS = tuple(ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32"))
MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".pdf"}


def text_findings(text, *, binary_strings=False, decode=True, package_constraints=False):
    """Return categories and line numbers only; never return matched values."""
    hits = set()
    version_spans = {m.span(1) for m in PACKAGE_PIN.finditer(text)} if package_constraints else set()
    def hit(category, offset):
        hits.add((category, text.count("\n", 0, offset) + 1))
    for category, pattern in (("credential", TOKEN), ("personal_path", PERSONAL_PATH),
                              ("private_host", PRIVATE_HOST), ("credential_literal", AUTH_LITERAL),
                              ("credential_environment", ENV_SECRET),
                              ("credential_url", AUTH_URL)):
        for match in pattern.finditer(text):
            if category == "credential_literal" and (
                match.group(1).startswith(("${", "{"))
                or match.group(1) in {"private-test-key", "sample-private-value"}
            ):
                continue
            if category == "credential_url" and "={" in match.group():
                continue  # A source template, not a resolved request URL.
            hit(category, match.start())
    lowered = text.lower()
    for term in PRIVATE_TERMS:
        if term in lowered:
            hit("private_platform", lowered.index(term))
    for pattern in (IPV4, IPV6):
        for match in pattern.finditer(text):
            if pattern is IPV4 and match.span() in version_spans:
                continue  # A complete package==version line in a constraints file.
            if pattern is IPV6 and binary_strings and len(match.group()) < 7:
                continue  # Short IPv6-like runs occur in compressed pixel bytes.
            try:
                address = ipaddress.ip_address(match.group())
            except ValueError:
                continue
            if address.is_loopback or address.is_unspecified or any(address in network for network in SAFE_NETWORKS):
                continue
            hit("ip_address", match.start())
    if decode and re.search(r"%[0-9a-fA-F]{2}", text):
        decoded = unquote(unquote(text))
        if decoded != text:
            hits.update(("encoded_" + category, 0) for category, _ in
                        text_findings(decoded, binary_strings=binary_strings, decode=False))
    return sorted(hits)


def known_private_values(config_paths):
    """Read only explicitly supplied private JSON; never return values in reports."""
    values = set()
    public_hosts = {"localhost", "api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com"}
    def endpoints(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if re.sub(r"[^a-z]", "", key.lower()) in {"baseurl", "baseurls", "endpoint", "endpoints"}:
                    for url in child if isinstance(child, list) else [child]:
                        if not isinstance(url, str):
                            continue
                        host = urlsplit(url).hostname
                        if not host or host in public_hosts or host.endswith((".example", ".invalid")):
                            continue
                        try:
                            address = ipaddress.ip_address(host)
                            if address.is_loopback or address.is_unspecified:
                                continue
                        except ValueError:
                            pass
                        values.update((url, host))
                endpoints(child)
        elif isinstance(item, list):
            for child in item:
                endpoints(child)
    for path in config_paths:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            values.update(value for value in credential_values(payload) if len(value) >= 8)
            endpoints(payload)
        except (OSError, ValueError, UnicodeError):
            raise ValueError("Unable to read private JSON configuration; values were not displayed.") from None
    variants = set()
    for value in values:
        variants.update(form.encode() for form in (value, quote(value, safe=""), quote_plus(value),
                                                   json.dumps(value)[1:-1]))
        variants.update((base64.b64encode(value.encode()), base64.urlsafe_b64encode(value.encode())))
    return tuple(variants)


def _png_text(raw):
    """Decode PNG text chunks, including compressed metadata, without Pillow."""
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return
    offset = 8
    while offset + 12 <= len(raw):
        size = int.from_bytes(raw[offset:offset+4], "big")
        kind = raw[offset+4:offset+8]
        chunk = raw[offset+8:offset+8+size]
        if len(chunk) != size:
            raise ValueError("Truncated PNG metadata")
        if kind == b"tEXt":
            yield chunk.decode("latin1")
        elif kind == b"zTXt":
            keyword, payload = chunk.split(b"\0", 1)
            yield keyword.decode("latin1") + " " + _inflate(payload[1:]).decode("latin1")
        elif kind == b"iTXt":
            keyword, payload = chunk.split(b"\0", 1)
            flag = payload[0]
            _, _, content = payload[2:].split(b"\0", 2)
            yield keyword.decode("latin1") + " " + (_inflate(content) if flag else content).decode("utf8")
        offset += size + 12


def _inflate(raw):
    decoder = zlib.decompressobj()
    value = decoder.decompress(raw, 2_000_001)
    if len(value) > 2_000_000 or not decoder.eof:
        raise ValueError("Compressed metadata exceeds scan limit or is incomplete")
    return value


def safe_display_name(name, *, known_values=()):
    name = str(name)
    if text_findings(name) or any(value in name.encode() for value in known_values):
        return "[redacted-path-" + hashlib.sha256(name.encode()).hexdigest()[:12] + "]"
    return name


def scan_bytes(name, raw, *, known_values=()):
    original_name = name
    known_name = any(value in name.encode() for value in known_values)
    name = safe_display_name(name, known_values=known_values)
    basename = Path(original_name).name
    if (basename == ".env" or (basename.startswith(".env.") and basename != ".env.example")
            or basename == "vigil.json" or (basename.startswith("vigil.") and basename.endswith(".json"))
            or Path(original_name).suffix in {".pem", ".key"}
            or basename in {".npmrc", ".pypirc", "id_rsa", "id_ed25519"}
            or basename.startswith("credentials") and basename.endswith(".json")
            or any(part in {".git", ".local", ".aws", ".ssh", ".codex", "outputs", "results", "__pycache__"} for part in Path(original_name).parts)):
        return [{"path": name, "category": "private_file", "line": 0}]
    suffix = Path(original_name).suffix.lower()
    texts = [original_name]
    binary_hits = []
    if suffix in MEDIA:
        strings = "\n".join(s.decode("ascii") for s in re.findall(rb"[\x20-\x7e]{6,}", raw))
        binary_hits = text_findings(strings, binary_strings=True)
        if suffix == ".png":
            try:
                texts.extend(_png_text(raw))
            except (ValueError, IndexError, zlib.error, UnicodeError):
                return [{"path": name, "category": "unreadable_metadata", "line": 0}]
    else:
        try:
            texts.append(raw.decode("utf8"))
        except UnicodeError:
            return [{"path": name, "category": "unreviewed_binary", "line": 0}]
    if suffix == ".json":
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            return [{"path": name, "category": "invalid_json", "line": 0}]
        texts.append(json.dumps(value, ensure_ascii=False))
        def visit(item):
            if isinstance(item, dict):
                for key, child in item.items():
                    if secret_field(key) and child not in (None, "", False, [], {}):
                        yield {"path": name, "category": "credential_field", "line": 0}
                    yield from visit(child)
            elif isinstance(item, list):
                for child in item:
                    yield from visit(child)
        structured = list(visit(value))
    else:
        structured = []
    constraints = suffix == ".txt" and basename.startswith(("requirements", "constraints"))
    matches = binary_hits + [hit for text in texts for hit in text_findings(text, package_constraints=constraints)]
    known = any(value in raw for value in known_values) or known_name or any(
        value in text.encode() for value in known_values for text in texts)
    if known:
        structured.append({"path": name, "category": "known_private_value", "line": 0})
    return structured + [{"path": name, "category": category, "line": line}
                         for category, line in matches]


def scan_files(root, files, *, known_values=()):
    hits = []
    for relative in files:
        path = root / relative
        if any(p.is_symlink() for p in (path, *path.parents)):
            hits.append({"path": safe_display_name(relative, known_values=known_values), "category": "symlink", "line": 0})
        else:
            hits.extend(scan_bytes(str(relative), path.read_bytes(), known_values=known_values))
    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="Exported source directory, source ZIP or built wheel")
    parser.add_argument("--private-config", action="append", type=Path, default=[], help="Also match secrets and endpoints from this private JSON config; repeatable, never copied or displayed.")
    args = parser.parse_args()
    path = args.candidate.resolve()
    try:
        known = known_private_values(args.private_config)
    except ValueError as exc:
        parser.error(str(exc))
    if path.is_file() and path.suffix in {".whl", ".zip"}:
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
            hits = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if (Path(name).is_absolute() or ".." in Path(name).parts or "\\" in name
                        or re.match(r"^[A-Za-z]:", name) or names.count(name) != 1
                        or (info.external_attr >> 16) & 0o170000 == 0o120000):
                    hits.append({"path": "[unsafe-archive-entry]", "category": "unsafe_archive", "line": 0})
                else:
                    hits.extend(scan_bytes(name, archive.read(info), known_values=known))
    elif path.is_dir():
        names = sorted(p.relative_to(path) for p in path.rglob("*") if p.is_file() or p.is_symlink())
        hits = scan_files(path, names, known_values=known)
    else:
        parser.error("Expected an exported source directory, ZIP or wheel.")
    print(json.dumps({"files_checked": len(names), "findings": hits, "known_private_variants_checked": len(known),
                      "visual_review_required": [safe_display_name(n, known_values=known) for n in names if Path(n).suffix.lower() in MEDIA]}, indent=2))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
