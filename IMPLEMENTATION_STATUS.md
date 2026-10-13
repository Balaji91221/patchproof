# Implementation status

Date: 13 October 2026. Version: 0.2.0. The public distribution name is `patchproof-ai`; imports and CLI
remain `patchproof`. Package verification and registry upload are separate release steps.

## Implemented and verified

- Python SDK and CLI; disposable Git snapshots with path validation and preserved source checkout.
- Pytest case normalization, identical injected regression tests, shared or per-case expected failures, and existing-suite comparisons.
- Repeat runs in fresh snapshots with supported/not-reproduced/fix-failed/regression-detected/inconclusive/flaky/inconsistent verdicts.
- Original JUnit XML, bounded logs, per-artifact hashes, JSON and static HTML reports.
- Explicit trusted-local runner and live-tested Docker adapter with immutable image pinning, environment inventory, restricted network/filesystem/user identity and timeout cleanup.
- Exact dependency requirement checking before repository execution; full Python/package manifests.
- Optional Claude proposal adapter with explicit remote opt-in, bounded request/response, schema and syntax validation, no automatic execution, and `.proposed` output files requiring review/rename.
- CI workflow, fixture dependency lock, wheel gate, changelog and release/contribution/security documentation.
- MIT license for original project code and package license metadata; third-party dependencies retain their own licenses.

## Verification evidence

- Default suite: 56 tests total; 53 passed, 3 Docker integration tests explicitly skipped unless enabled.
- Full suite with `PATCHPROOF_DOCKER_IMAGE=patchproof-verified-local:0.2`: **56 tests passed**, including live container fail-before/pass-after, package manifest capture, network denial, read-only source, non-root identity, host-secret exclusion and timeout/container cleanup.
- Live controlled Docker demo produced `supported` with original XML and dependency artifacts.
- Release gate builds a wheel, installs it in a fresh virtual environment, imports the installed SDK, checks installed CLI help and reads a real demo report.
- Local test host: macOS, Python 3.10.10, pytest 9.1.1. Verified container: Python 3.13.16, pytest 9.1.1. The tested image was built offline from existing local Python/pytest dependencies after TLS downloads failed. TLS validation was never disabled.
- The supplied public Dockerfile is a separate Python 3.12 image recipe; it is not claimed identical to the locally tested image. Pin a reviewed base digest for releases.

Repeat the checks from this repository's root:

```bash
python -m pip install -r requirements-test.lock build wheel 'setuptools>=77' twine
python scripts/check_release.py
# With Docker running, build the authored image recipe, then enable all three Docker tests:
docker build -t patchproof-check:local -f examples/Dockerfile .
PYTHONPATH=src PATCHPROOF_DOCKER_IMAGE=patchproof-check:local python -m unittest discover -s tests -v
```

The Docker build may download its base image and dependencies. Test execution uses
an already local image. The earlier 56-test result used the separately described
local image, not a claim that this recipe or hosted CI has since run.

## Remaining validation and external decisions

- No live Anthropic API call or model quality evaluation was performed; transport/schema/input-safety behavior is verified with controlled provider fixtures. Users must supply credentials and a supported model for an explicitly authorized live check.
- The GitHub CI matrix is authored but has not run on a hosted repository. Linux test execution was exercised inside Docker; separate host-level Python matrix evidence remains a CI gate.
- Registry upload and independent pilot feedback are separate from local verification. GitHub source publication does not constitute a package release or independent validation. Use SECURITY.md for the repository reporting route.
- Docker restrictions are exercised but not an exhaustive security certification or VM-level hostile-code boundary. Trusted-local remains explicitly unsandboxed.
- Scope exclusions and a complete plan mapping are in `docs/FEATURE_MATRIX.md`. Repetition detects observed instability, not proof of non-flakiness or full patch correctness.
