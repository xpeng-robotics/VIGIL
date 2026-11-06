[Documentation](../README.md) / Development

# Credentials and public artifacts

Use `vigil init` or the workbench to configure your model. Put authentication in
`api_key` (or the provider environment variable); use `api_key_header` when your
gateway needs a different header. Credential-bearing URLs and credentials nested
in `extra_body` are rejected before execution because those fields become saved
experiment metadata and worker arguments. Normal endpoint routing parameters and
generation options remain supported. Existing run fingerprints are not rewritten.

Model configuration files are private. The workbench redacts credential fields
and known raw or encoded keys in responses. Local experiment outputs can still
contain endpoint addresses, machine paths, model-generated text and observations.
Do not upload the whole working directory, configuration files, raw outputs or
screenshots of a configured service. An ignore file only prevents ordinary Git
additions; it does not remove already tracked material or clean Git history.

Create a public copy with the allowlisted exporter:

```bash
python scripts/release/export_public_release.py /path/to/new-release
python scripts/release/check_public_release.py /path/to/new-release
```

The exporter scans selected files before creating the destination and rejects
suspected credentials, internal hosts, non-example IPs and personal paths. The
standalone checker scans every file in an exported directory, or every member of
a ZIP or wheel. Reports contain categories and locations, never matched values. Keep
audit reports outside the public copy. Loopback addresses, wildcard bind
addresses and documentation-only IP ranges are intentional portable examples.

When a maintainer has private model configurations, compare against their actual
credentials and endpoint addresses as well as generic patterns:

```bash
python scripts/release/export_public_release.py /path/to/new-release --private-config /path/to/private-config.json
python scripts/release/check_public_release.py /path/to/release.zip --private-config /path/to/private-config.json
python scripts/release/check_public_release.py /path/to/package.whl --private-config /path/to/private-config.json
```

Repeat `--private-config` for each JSON configuration. Values and common encoded
forms are matched in memory; the configuration is never copied or printed.
Keep these files outside the exported directory. An unreadable configuration
fails the check. Archive checks also reject parent paths, duplicate entries and
symlinks. A zero-finding report is evidence for the inspected bytes and supplied
configuration values, not a guarantee that every possible secret was recognized.

Recorded example export also rejects transport fields, private text and detected
frame metadata before copying. It preserves original evidence; it does not
silently redact actions, frames, scores or provenance. Choose a different source
case when evidence itself contains private material.

The automated check covers UTF-8 files, decoded JSON, recognizable token formats,
printable binary strings and PNG text metadata (including compressed text).
It cannot recognize every arbitrary secret, decode all binary formats or inspect
visible pixels. Before publication, also extract PDF text and metadata, inspect
image metadata, and review images and video for visible endpoints or credentials.
OCR can assist that review but can miss small or briefly visible text. Do not
upload private material to an external scanner or OCR service.

Review Git commits, author/committer identities, tags and historical blobs
separately. A clean current tree does not make its history public-safe. The
exporter produces a directory without Git history; start the public repository
from that inspected copy when the development history contains private material.
Do not mirror development history merely because the latest scan passes.

This is a technical disclosure check. Project licensing, scene provenance,
upstream permissions and publication approval remain separate gates in the
[release checklist](RELEASE_CHECKLIST.md).
