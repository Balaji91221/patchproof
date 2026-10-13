# PatchProof

PatchProof checks whether the **same supplied regression test fails for an expected reason on a base Git commit and passes after a patch**. It also optionally compares existing tests on both revisions. It creates disposable snapshots and produces JSON and self-contained HTML evidence.

This is a working local release candidate, not a published package or a proof that a patch is correct. No LLM or API key is required. Original project code is licensed under the [MIT License](LICENSE). Third-party dependencies retain their own licenses. Public package naming remains a release decision.

## Quick start

Requires Python 3.10+, Git, and macOS/Linux. Windows process cleanup is not implemented.

```bash
git clone https://github.com/Balaji91221/patchproof.git
cd patchproof
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[runner]'
python examples/demo.py --output /tmp/patchproof-demo-001
python -m patchproof report /tmp/patchproof-demo-001
```

Choose a fresh output directory for each run. The demo executes only its own small, authored fixture using the explicit trusted-local adapter. The expected verdict is `supported`; open `/tmp/patchproof-demo-001/report.html` for the evidence.

To run from the checkout without installation, prefix commands with `PYTHONPATH=src`. The execution environment must already contain pytest and the dependencies of the project under test; PatchProof never automatically installs project dependencies or runs setup scripts.

## Verify a patch

```bash
patchproof run \
  --repo /path/to/reviewed-project \
  --base HEAD \
  --patch /path/to/fix.diff \
  --test /path/to/test_regression.py \
  --expect 'BUG_123: total must include shipping' \
  --existing tests/test_checkout.py \
  --timeout 30 \
  --output /tmp/patchproof-run-001 \
  --trusted-local
```

The regression test should have an explicit meaningful assertion message matching `--expect`. Every failing base regression case must include that marker. A failed assertion with an unrelated reason does not count as bug reproduction. The marker is user-defined evidence, not automatic validation of the bug's semantics.

`--existing` accepts repeatable relative pytest selectors. Uncommitted user changes are not included: both variants come from the resolved base commit, and only the supplied patch is applied to the patched snapshot. The supplied regression test is injected byte-for-byte into both; patch attempts to change that reserved location are rejected. Snapshots containing symlinks, submodules or special files are rejected. Text patches using ordinary `a/` and `b/` headers are supported; renames, copies, binary patches and quoted filenames are not.

## Execution boundary

**`--trusted-local` is deliberately not a sandbox.** It authorizes running reviewed Python repository and test code as your current user in subprocesses. Environment variables are allowlisted and HOME is temporary, but code can still read or change host files, use the network, and launch processes. Do not use it for downloaded or otherwise untrusted code. Snapshot preparation does not alter the source checkout; trusted-local test code can violate that boundary if it deliberately accesses outside its workspace.

For container execution, build a reviewed image containing Python, pytest and required project dependencies:

```bash
docker build -t patchproof-python:local -f examples/Dockerfile .
patchproof run --repo /path/to/project --base HEAD \
  --patch /path/to/fix.diff --test /path/to/test_regression.py \
  --expect 'BUG_123' --output /tmp/patchproof-container-001 \
  --docker-image patchproof-python:local
```

Image construction uses network access for dependency installation. Actual test execution disables network, uses a read-only root filesystem and source mount, drops capabilities, uses a non-root user, limits CPU/memory/processes/file size, and only mounts a writable result directory. The image is resolved once to its local immutable ID for all variants; no image is pulled during a run. Docker must already be running and accessible. The adapter always attempts to remove its named container after completion or timeout.

Containers are not sufficient for deliberately hostile code or defense against kernel escapes. Such inputs require a separately hardened execution service or VM boundary. Tests can also deliberately falsify their own results; this tool is not an adversarial attestation mechanism.

Only the authored demo and fixtures should be run while evaluating the tool. The regression run disables project `conftest.py` discovery and third-party plugin autoload, using an empty pytest configuration. This avoids different collection settings across variants; tests requiring project fixtures/plugins are unsupported by the initial regression runner. Existing-suite runs honor project pytest configuration and conftest files but keep plugin autoload disabled. Project plugins can be explicitly configured by reviewed code.

## SDK

```python
from pathlib import Path
from patchproof import VerificationRequest, verify_patch
from patchproof.runners import DockerRunner

result = verify_patch(
    VerificationRequest(
        repo=Path('/path/to/project'),
        base='HEAD',
        patch=Path('/path/to/fix.diff'),
        test=Path('/path/to/test_regression.py'),
        expected_failure='BUG_123',
        output=Path('/tmp/patchproof-sdk-001'),
        existing_tests=('tests/test_checkout.py',),
    ),
    runner=DockerRunner('patchproof-python:local'),
)
print(result['verdict'])
```

`verify_patch` returns a schema-versioned manifest dictionary. `Runner` is a small protocol with `run()` and `describe()`; adapters must return `inconclusive` for incomplete execution, not manufacture a pass. `classify()` is independently usable for normalized results. Output must be a new directory outside the source repository, so previous evidence and source files cannot be overwritten by report generation.

## Verdicts and exit codes

| Verdict | Meaning | CLI code |
|---|---|---|
| `supported` | Expected base failure, patched pass, same case identities/counts, and requested existing tests remain clean | 0 |
| `not_reproduced` | Base regression test already passed | 1 |
| `fix_failed` | Expected bug reproduced, but patched regression still failed | 1 |
| `regression_detected` | Regression fixed, but an existing test that passed on base now fails | 1 |
| `inconclusive` | Timeout, setup/collection failure, skip, missing report, unexpected base failure, changed test set, or dirty existing-suite baseline | 2 |
| `flaky` | Repetitions produced different case outcomes | 2 |
| `inconsistent` | Repetitions changed collection, completion, or verdict evidence | 2 |

Input/runner errors also exit 2. Base passing takes precedence over other checks: that run provides no regression evidence. Missing existing-suite checks are explicitly recorded as `not requested`. Use `--repeat N` (1–20) to rerun every variant in fresh snapshots. Different case outcomes are `flaky`; collection or infrastructure drift is `inconsistent`. Both exit 2 and preserve every attempt. Repetition detects observed instability; it cannot establish that a test is never flaky.

## Architecture and implementation

```text
CLI / SDK request
  -> validate inputs + snapshot Git base
  -> apply patch to second disposable snapshot
  -> inject identical regression bytes
  -> Runner(base), Runner(patched)
  -> optional existing-suite runs in fresh snapshots
  -> deterministic classifier
  -> JSON + escaped static HTML report
```

`core.py` owns domain types and verdicts. `workspace.py` owns Git and filesystem operations. `runners.py` owns execution and JUnit normalization. `service.py` orchestrates these boundaries; `cli.py` only parses input and maps results to exit codes. A different runner can be added without changing classification. The report captures base SHA, patch/test hashes, environment description/hash, case identities, logs, and reasons. The environment hash covers the recorded manifest, exact Python version and installed package versions. Docker runs also record the immutable image ID. This inventory does not prove OS-level reproducibility or hash every installed package file. Reports may contain source fragments and test output; review before sharing. Logs are truncated at 256 KB per stream. Original UTF-8 JUnit XML is retained separately with SHA-256 references; unsafe, oversized (over 2 MB), or symlink result files are rejected.

## Verify this implementation

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Tests execute authored fixtures only. They cover real fail-before/pass-after behavior, existing-test regressions, collection failures, timeouts, preserved tracked/untracked/Git files, path traversal, reserved-test overrides, symlink patches, invalid selectors, environment stripping, and verdict semantics. See `IMPLEMENTATION_STATUS.md` for verification and remaining work.

## Repeated evidence and per-case contracts

```bash
patchproof run --repo /path/to/project --base HEAD \
  --patch /path/to/fix.diff --test /path/to/test_regression.py \
  --expectations examples/expectations.json --repeat 3 \
  --dependency-manifest examples/dependencies.json \
  --output /tmp/patchproof-repeated-001 --docker-image patchproof-python:local
```

Per-case contracts replace the shared marker and require exactly the declared failing case set on the base revision. Each contract matches a JUnit case identity, a non-empty failure message substring and an optional exact exception type. Additional passing guard cases are allowed. See `examples/expectations.json`; case IDs can be read from the first report. An unexpected error does not count as reproduction. Dependency mismatches are rejected before any repository test executes.

A schema-2 report contains `attempts` and artifact paths under `artifacts/attempt-001/base/`, `patched/`, and optional existing-suite phases. The compatibility `executions` fields show the first attempt; always read the top-level verdict and `attempts` for repeated runs. Schema-1 reports remain readable without rewriting.

## Environment manifests

```bash
patchproof environment --docker-image patchproof-python:local \
  --requirements-only --output /tmp/patchproof-requirements.json
```

Without `--docker-image`, this inventories the current Python environment without running repository code. Without `--requirements-only`, it exports the full environment description. The requirements form accepts exact Python and/or package versions, with packages treated as a required subset. It never installs or upgrades dependencies. `requirements-test.lock` pins this project's authored fixture dependencies; target projects supply their own reviewed image and dependency manifest.

## Optional Claude regression-test proposals

The opt-in adapter implements the [Claude Messages API](https://platform.claude.com/docs/en/api/messages/create) and uses a forced [schema-described tool response](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools) as data. Use an explicit model that supports forced tool use. No tool function or model-produced Python code is executed.

```bash
# Configure ANTHROPIC_API_KEY in your shell; do not put it in source control.
patchproof propose --issue issue.txt --patch fix.diff --source src/calculator.py \
  --model YOUR_SUPPORTED_MODEL_ID --allow-remote --output /tmp/patchproof-proposal-001
```

Only the selected issue, patch and source files leave the machine. The adapter requires explicit remote opt-in, uses HTTPS certificate validation, refuses redirects, caps selected input at 64 KB, output at 8192 tokens and response at 256 KB, and makes one request with no automatic retry. It validates the response shape, case expectations and Python syntax, then saves `test_regression.py.proposed`, `expectations.json.proposed` and a manifest marked `trusted: false`. Provider token usage and source hashes are recorded; credentials are not.

Read the proposal and its assumptions before copying it to a reviewed `.py` file. Verification rejects `.proposed` files and still requires an explicit execution adapter. Syntax validation does not establish safety or semantic correctness. The remote provider path has contract-fixture coverage but no live paid-model quality claim; no API credentials were used in verification.

## Release checks and remaining external gates

Run `python scripts/check_release.py` for tests, wheel construction, a clean installation and CLI/SDK smoke checks. `.github/workflows/ci.yml` includes Linux/macOS Python matrix checks and live Docker fixtures; it is supplied, not claimed to have run on GitHub. See `docs/FEATURE_MATRIX.md` and `docs/RELEASE.md` for implementation evidence, release decisions and deliberately excluded scope. Publication, pilot feedback and a hosted service are separate steps.
