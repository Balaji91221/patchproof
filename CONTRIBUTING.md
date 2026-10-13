# Contributing

Use Python 3.10+ on Linux or macOS. Keep domain classification independent of process, network and filesystem adapters. Add authored fixture tests for changes that affect verdicts, cleanup or security boundaries; do not execute third-party repositories in test jobs. Run `PYTHONPATH=src python -m unittest discover -s tests -v` and `python scripts/check_release.py` before proposing a release. Live Docker tests are enabled only with `PATCHPROOF_DOCKER_IMAGE`.

Changes to the proposal provider must preserve explicit remote opt-in, bounded input/output, schema validation, credential redaction and non-execution of generated code. Changes to runners must preserve incomplete/inconclusive semantics and clean up their own execution resources. Do not add TLS bypasses to work around local certificate problems.

Build metadata uses PEP 639 with setuptools 77 or newer. Install `requirements-test.lock` and the `build`, `wheel`, and `twine` tools before running the release gate. The distribution is `patchproof-ai`; Python imports and the CLI remain `patchproof`. The gate builds an sdist and then a wheel from that sdist, checks both, and runs tests and the demo against a fresh installed package. It does not publish.
