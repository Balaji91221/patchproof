# Contributing

Use Python 3.10+ on Linux or macOS. Keep domain classification independent of process, network and filesystem adapters. Add authored fixture tests for changes that affect verdicts, cleanup or security boundaries; do not execute third-party repositories in test jobs. Run `PYTHONPATH=src python -m unittest discover -s tests -v` and `python scripts/check_release.py` before proposing a release. Live Docker tests are enabled only with `PATCHPROOF_DOCKER_IMAGE`.

Changes to the proposal provider must preserve explicit remote opt-in, bounded input/output, schema validation, credential redaction and non-execution of generated code. Changes to runners must preserve incomplete/inconclusive semantics and clean up their own execution resources. Do not add TLS bypasses to work around local certificate problems.
