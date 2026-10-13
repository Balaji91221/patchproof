# Plan-to-implementation matrix

| Planned capability | Implementation | Evidence / boundary |
|---|---|---|
| Known bug fixtures | Calculator fixtures, correct fix, unrelated/not-reproduced classifier, still-failing and existing-regression cases | Unit and real pytest integration tests |
| Isolated variants | Git archive into disposable snapshots; validated text patch; same test bytes in both variants | Checkout hash/preservation test includes tracked, untracked and Git files |
| Input safety | Relative path checks, reserved test path, no links/submodules/binary/rename patches | Traversal, symlink patch and override tests |
| Execution | Explicit trusted-local and Docker adapters; timeouts, allowlisted local environment, non-root container, read-only source, network disabled, limits | Live local Docker suite passed using an offline-built test image |
| Pytest normalization | Case outcomes, exception inference, setup/collection/skip/error checks, bounded no-follow XML reading | XML boundary tests and import-error/timeout fixtures |
| Failure expectations | Shared marker or exact per-case identities/messages/optional exception types | Correct and wrong exception cases; real pytest contract fixture |
| Existing behavior | Run selected existing tests against fresh base/patched snapshots | Real new-regression detection fixture |
| Flaky/inconsistent evidence | 1–20 fresh-snapshot repetitions, separate flaky/inconsistent verdicts | Stable real repeats, controlled outcome/collection/infrastructure variations |
| Evidence retention | Per-attempt XML/stdout/stderr artifacts and hashes, JSON/HTML reports | Artifact bytes/hash verification; stdout/stderr capped at 256 KB |
| Environment/dependencies | Exact Python and package inventory; pinned Docker image ID; requirements validation before execution | Dependency mismatch blocks runner; live Docker manifest capture |
| Public SDK/CLI | Versioned manifest, explicit runner protocol, run/report/environment/propose commands | Wheel construction and clean-installed CLI/SDK checks |
| Optional model test proposal | Explicit remote opt-in Claude adapter; schema-defined tool response, local validation, non-executable proposal outputs, source hashes | Provider request/response fixtures; no live credentialed/model-quality evaluation claimed |
| CI/release | Linux/macOS Python matrix, Docker job, local package gate, changelog, contribution/security/release docs | Workflow authored; local gate executed; hosted CI not run |
| PyPI publication and pilots | Remain external gates, separate from GitHub source publication | No PyPI release or independent pilot feedback claimed; original project code is MIT licensed |

## Deliberate boundaries

No automatic merging, universal language support, Windows process cleanup, arbitrary public-repository execution without a suitable sandbox, formal correctness proof, auto-installed target dependencies or hosted service. Git snapshots follow Git archive/export attributes. Python regression tests are self-contained and do not load project conftest fixtures; existing-suite execution honors reviewed project configuration. A container reduces exposure but does not provide a hostile-code VM guarantee. Code and LLM output can lie about behavior; tests provide evidence, not adversarial attestation.
