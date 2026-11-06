"""Credential handling shared by configuration, errors and the local workbench."""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, quote, quote_plus, urlsplit


def secret_field(name: str) -> bool:
    name = re.sub(r"[^a-z0-9]", "", name.lower())
    return name in {
        "apikey", "apitoken", "accesstoken", "refreshtoken", "clientsecret",
        "password", "passwd", "secret", "token", "authorization",
        "proxyauthorization", "cookie", "setcookie", "privatekey", "credentials",
        "xapikey", "xgoogapikey", "xamzcredential", "xamzsignature",
    }


def credential_values(value):
    """Collect structured credentials without displaying or persisting them."""
    if isinstance(value, dict):
        for key, child in value.items():
            if secret_field(str(key)) and isinstance(child, str) and child:
                yield child
            yield from credential_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from credential_values(child)
    elif isinstance(value, str):
        for match in re.finditer(r"https?://[^\s\"'<>]+", value):
            try:
                parts = urlsplit(match.group())
                if parts.password:
                    yield parts.password
                if parts.username:
                    yield parts.username
                for key, child in parse_qsl(parts.query):
                    if secret_field(key) or key.lower() in {"key", "sig", "signature"}:
                        yield child
            except ValueError:
                continue


def redact(value, secrets=()):
    forms = set()
    for key in (*secrets, *credential_values(value)):
        if key:
            forms.update((key, quote(key, safe=""), quote_plus(key), json.dumps(key)[1:-1]))
    ordered = sorted(forms, key=len, reverse=True)

    def clean(item):
        if isinstance(item, str):
            for form in ordered:
                item = item.replace(form, "[REDACTED]")
            return item
        if isinstance(item, list):
            return [clean(child) for child in item]
        if isinstance(item, dict):
            return {key: "[REDACTED]" if secret_field(str(key)) else clean(child)
                    for key, child in item.items()}
        return item
    return clean(value)


def validate_auth_placement(urls, extra_body):
    """Reject credentials in fields persisted as experiment metadata or argv."""
    for url in urls:
        try:
            parts = urlsplit(url)
        except ValueError:
            raise ValueError("Invalid model endpoint URL.") from None
        if parts.username is not None or parts.password is not None or any(
            secret_field(key) or key.lower() in {"key", "sig", "signature"}
            for key, _ in parse_qsl(parts.query, keep_blank_values=True)
        ) or parts.fragment:
            raise ValueError("Credentials and fragments are not allowed in model endpoint URLs. Use api_key and api_key_header.")

    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if secret_field(str(key)):
                    raise ValueError("Credentials are not allowed in extra_body. Use api_key and api_key_header.")
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(extra_body)
