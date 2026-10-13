# Release process

The distribution is **`patchproof-ai`**, version **0.2.0**. Python imports and the
CLI remain `patchproof`. The unrelated `patchproof` PyPI name is not this project.
Building and checking artifacts does not upload them.

## Verification gate

```bash
python -m pip install -r requirements-test.lock build wheel 'setuptools>=77' twine
python scripts/check_release.py
```

The gate runs source tests, builds a fresh sdist, then builds the wheel **from that
sdist**. It checks exact distribution/version metadata, the PEP 639 MIT license,
archive contents, and PyPI README rendering with `twine check --strict`. It installs
the wheel with its runner extra in a fresh virtual environment, clears PYTHONPATH,
and runs installed SDK/CLI checks, the tests included in the sdist, and the authored
fail-before/pass-after demo. Tests and the demo use the installed package.

The fresh output artifacts are copied to `dist/`; older files are never selected
as inputs. Upload only the two artifacts named in the gate's final result, not an
unchecked wildcard over old releases. The result includes SHA-256 digests.

Options: `--output-dir PATH` selects an artifact directory; `--wheelhouse PATH`
uses an existing offline dependency wheelhouse; `--installer uv` selects `uv`
with system certificate validation. Without a wheelhouse, installing runner
dependencies may contact the configured package index. No TLS bypass is used.

For live Docker checks, build a reviewed Python/pytest image and run:

```bash
PATCHPROOF_DOCKER_IMAGE=image:tag PYTHONPATH=src python -m unittest discover -s tests -v
```

No container pulls occur during test verification. Container construction may
fetch the base image and dependencies. Hosted CI results are available in
[GitHub Actions](https://github.com/Balaji91221/patchproof/actions/workflows/ci.yml).

## Artifact contents

The wheel includes the `patchproof` Python modules, entry point, metadata, and MIT
license. The sdist additionally includes authored tests, demo/Docker recipes,
requirements lock, release script, documentation, and sanitized README visuals.
`MANIFEST.in` explicitly excludes local `examples/evidence` inventories, run
outputs, credentials, caches, prior builds, and old distributions.

`README_PYPI.md` is the registry description; its links and PNG image use absolute
public URLs. Keep it consistent with the GitHub README and actual interfaces.
The base package has no runtime dependencies; `runner` pins pytest 9.1.1.

## Registry release

Confirm account ownership, the final artifact names and hashes, release notes,
and explicit upload authorization. Do not upload a stale local-name wheel.
Preserve third-party dependency licenses. Publication and tags are deliberate
operations performed separately from the verification script.

Independent pilots and live model-quality evaluation are not established by
fixture tests. The optional provider remains opt-in and generated tests are never
automatically executed. See [verification status](../IMPLEMENTATION_STATUS.md)
and [security boundaries](../SECURITY.md).

## Compatibility and rollback

Report schema 2 adds attempts, per-case expectations, artifacts and dependency
manifests. Schema-1 reports remain readable. Keep the exact previous reviewed wheel
and reports before upgrading; this initial `patchproof-ai` release does not imply
an earlier version exists on PyPI. Each verification writes a new output directory.
