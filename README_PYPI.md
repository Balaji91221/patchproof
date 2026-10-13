# PatchProof

**A passing test is useful. A test that fails before the fix is evidence.**

PatchProof checks whether the same supplied regression test fails for an expected
reason on a base Git commit and passes after a patch. It creates disposable
snapshots and saves JSON, HTML, original JUnit reports, and execution evidence.

The distribution name is **`patchproof-ai`**. The Python import and command are
both **`patchproof`**. Python 3.10+, Git, and Linux or macOS are required for
verification. No model account is needed.

## Install

```bash
python -m pip install 'patchproof-ai[runner]'
patchproof --help
```

The `runner` extra installs pytest. The base package has no runtime dependencies.
Target-project dependencies must already exist in your reviewed environment or
container image; PatchProof does not install them automatically.

## Verify reviewed code

```bash
patchproof run \
  --repo /path/to/reviewed-project --base HEAD \
  --patch /path/to/fix.diff --test /path/to/test_regression.py \
  --expect 'BUG_ADD' --repeat 3 \
  --output /tmp/patchproof-run-001 --trusted-local
```

Use a fresh output directory outside the source repository. The regression test
must contain a meaningful assertion whose failure message includes `BUG_ADD`.
An unrelated failure does not count as reproduction. Existing test suites and
per-case expectations can also be compared.

**Trusted-local execution is not a sandbox.** It runs reviewed Python code as
your current user. For an explicitly prepared local Docker image, select
`--docker-image IMAGE` instead. Docker restrictions reduce exposure but are not
a hostile-code VM boundary. Read the
[execution guide](https://github.com/Balaji91221/patchproof/blob/main/docs/usage.md#execution-boundary)
before running unfamiliar code.

## Python SDK

```python
from pathlib import Path
from patchproof import VerificationRequest, verify_patch
from patchproof.runners import TrustedLocalRunner

# Only for repository and test code you own and have reviewed.
result = verify_patch(
    VerificationRequest(
        repo=Path('/path/to/reviewed-project'),
        base='HEAD',
        patch=Path('/path/to/fix.diff'),
        test=Path('/path/to/test_regression.py'),
        expected_failure='BUG_ADD',
        output=Path('/tmp/patchproof-sdk-001'),
    ),
    runner=TrustedLocalRunner(trust_confirmed=True),
)
print(result['verdict'], result['reason'])
```

## Interpret the evidence

| Exit | Verdicts | Meaning |
|---|---|---|
| 0 | `supported` | Expected fail-before/pass-after evidence observed |
| 1 | `not_reproduced`, `fix_failed`, `regression_detected` | Checks do not support accepting the change |
| 2 | `inconclusive`, `flaky`, `inconsistent` | Evidence is incomplete or unstable |

Input and runner errors also exit 2. Setup/collection errors, missing reports,
skips, timeouts, and unexpected base failures never count as successful
reproduction. Repeated runs preserve every attempt.

![Actual report from the included controlled fixture](https://raw.githubusercontent.com/Balaji91221/patchproof/main/docs/assets/demo.png)

## Scope and optional proposals

PatchProof supplies regression evidence, not a proof of complete correctness.
Snapshot preparation leaves the source checkout intact, but trusted-local test
code can access host resources. Windows process cleanup, binary/rename/copy
patches, symlink/submodule snapshots, and arbitrary project fixtures in the
injected regression test are not supported.

Optional Claude test proposals require explicit remote opt-in. Selected files
are sent to the configured provider; schema/syntax-checked outputs remain
untrusted `.proposed` files. They are never executed automatically. Verification
still requires human review and an explicit execution adapter.

## Documentation and source

- [Quick start and authored demo](https://github.com/Balaji91221/patchproof#quick-start)
- [CLI, Docker, and SDK recipes](https://github.com/Balaji91221/patchproof/blob/main/docs/usage.md)
- [Architecture](https://github.com/Balaji91221/patchproof/blob/main/docs/architecture.md)
- [Verification status](https://github.com/Balaji91221/patchproof/blob/main/IMPLEMENTATION_STATUS.md)
- [Security boundaries](https://github.com/Balaji91221/patchproof/blob/main/SECURITY.md)
- [Report a bug](https://github.com/Balaji91221/patchproof/issues)

Original project code is [MIT licensed](https://github.com/Balaji91221/patchproof/blob/main/LICENSE).
Third-party dependencies retain their own licenses.
