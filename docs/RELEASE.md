# Release process

This repository contains the source for local release candidate 0.2.0. Publishing source on GitHub is separate from publishing a PyPI package. No PyPI release, hosted service deployment, or independent maintainer validation is claimed.

## Local gate

1. Use a clean Python virtual environment and install `requirements-test.lock` plus build tools `build`, `wheel` and `setuptools`.
2. Run `python scripts/check_release.py`. It runs authored fixtures, builds a wheel without network resolution, installs that wheel in a fresh environment, imports the installed SDK, checks the CLI and reads a real demo report.
3. Build a reviewed Python/pytest image. Run `PATCHPROOF_DOCKER_IMAGE=image:tag PYTHONPATH=src python -m unittest discover -s tests -v` with Docker available. No container pulls happen during verification.
4. Review the wheel contents, generated reports, changelog and documented limitations. Do not include real source snippets or credentials in public examples.
5. Run the CI matrix on a repository host. The workflow is supplied; a local pass is not proof the hosted matrix passed.

## Decisions before a PyPI release

- Original project code is MIT licensed. Preserve LICENSE in release artifacts and review independent third-party dependency license obligations and contributor terms.
- Verify availability and ownership of the distribution name and command; `patchproof-local` is only a local package identifier.
- Confirm the source repository and private security-reporting URLs in project metadata, and test the reporting route.
- Pin CI actions and reviewed container bases to immutable digests for the release policy.
- Review the optional remote proposal data flow and supported model configuration with real API credentials in an explicitly authorized test.
- Obtain independent pilot feedback. None is claimed by fixture tests.
- Build a signed/tagged package release, record input hashes and lock manifests, then publish to PyPI only through an explicitly authorized release process. Source publication alone does not authorize a registry upload.

## Compatibility and rollback

Report schema 2 adds attempts, case expectations, artifacts and dependency manifests. The CLI still reads schema 1 reports without rewriting them. Pin package version 0.1.0 to roll back software; retain original reports and inspect new schema reports with 0.2.0. Execution adapters remain explicit and no database migration is required. Each run writes a new output directory and never overwrites previous evidence.
