---
name: vigil-release
description: Prepare and verify a VIGIL source export or wheel, including public assets, curated recordings, documentation and release gates.
---

Read [contributing](../../../docs/development/CONTRIBUTING.md) and
[release checks](../../../docs/development/RELEASE_CHECKLIST.md). Work from the release root.

Use `scripts/release/export_public_release.py` to export to a new directory. Test that
exact copy with the complete offline suite, `validate-pack` and bundled-demo
`verify-run --require-frames`. Verify all six curated cases when their files change.
Build and test the installed wheel outside the checkout when package assets or
layout change. Check source launchers without installing the package.

Keep new root documents/scripts and project skills in the exporter's explicit
allowlists. Curated recordings are constrained by their reviewed SHA256 manifest;
never broaden export to include an entire experiment folder. Check that local
config, keys, process logs and machine paths are absent. Preserve provenance and
experimental-profile labels when selecting historical recordings.

Report tested commands, exact artifact paths and validation limits. Export/test
success does not resolve missing project licensing or publication checks. Do not
publish or mark a candidate ready until those gates are resolved; private review
updates follow the user's actual authorization.
