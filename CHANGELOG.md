# Changelog

## 0.2.0 — initial public distribution

- Distribution name is `patchproof-ai`; imports and the command remain `patchproof`.
- Added PEP 639 MIT metadata, PyPI documentation, complete authored source archives, and fresh installed-package release checks.

- Repeat verification in fresh snapshots and report flaky or inconsistent evidence.
- Match failures by case identity, message and optional exception type.
- Retain original JUnit XML plus stdout/stderr artifacts with hashes.
- Export Python/package manifests and verify exact dependency requirements before execution.
- Add an explicitly authorized Claude proposal adapter with schema validation, bounded requests, no execution and `.proposed` outputs.
- Verify Docker runtime, isolated network, read-only source, non-root identity and timeout cleanup.
- Refuse result-file symlinks and oversized JUnit artifacts.
- Add CI workflows and clean package-install verification.

## 0.1.0 — local prototype

- Disposable Git snapshots, fail-before/pass-after classifier, CLI/SDK, explicit execution adapters and static reports.
