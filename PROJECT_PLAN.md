# PatchProof project plan

Regression evidence for generated code fixes.

**Status:** Local 0.2.0 roadmap implemented and verified, including live Docker checks. See [feature matrix](docs/FEATURE_MATRIX.md), [implementation status](IMPLEMENTATION_STATUS.md), and [actual usage](README.md). Live model quality, hosted CI, PyPI publication and independent pilots remain external gates. **Planning date:** 13 October 2026. Package names and interfaces below are illustrative and must be checked before publication.

## Goal and target users

Maintainers, software engineers, and coding-agent builders reviewing proposed bug fixes.

A new test passing on patched code does not show that it detects the original bug. PatchProof runs the same regression test against base and patched revisions, then checks relevant existing tests.

## Product hypothesis and validation

An auditable fail-before/pass-after workflow with explicit failure-reason checks and isolated execution. It increases confidence but does not prove full correctness.

Before expanding the implementation, interview three to five target developers. Ask for a recent concrete failure, current workaround, and a repository or sanitized fixture they can share. A successful pilot means someone other than the author can install the tool, reproduce a useful finding, and explain why it belongs in their workflow. These are validation goals, not established demand.

## First release scope

Python/pytest only, local Git repositories, explicit base revision and patch, a supplied regression test, isolated disposable execution, structured results, and an HTML report. LLM-generated tests are a later optional input.

**Out of scope:** No arbitrary public-repository execution without sandboxing, automatic merging, universal language support, full formal verification, or claims that every passing patch is correct.

## Representative workflow

User supplies base commit, patch, and regression test → coordinator snapshots inputs → builds isolated base and patched environments → runs the same regression test in both → classifies failures → runs relevant existing tests → emits evidence.

## High level design

```text
CLI -> Input validator -> Workspace manager
Workspace manager -> Base sandbox -> Test result
Workspace manager -> Patched sandbox -> Test result
Results + Failure expectations -> Evidence classifier -> Report
```

**Implementation stack:** Python, pytest, Git subprocess adapter, an explicit sandbox runner, JSON manifests and logs; CLI first and static HTML viewer next. Pin environment inputs and keep network disabled during test execution where practical.

**Architecture choice:** Two local checkouts are convenient but do not isolate untrusted code. Choose disposable sandbox execution with restricted mounts and resources. A hosted sandbox service simplifies some isolation but adds expense and source-upload concerns.

Keep the core as a local library with thin interface adapters. Process boundaries shown above are deliberate; do not split every module into a deployed service. A dashboard is a consumer of the core results, not the owner of domain rules.

## Low level design

| Component | Contract | Responsibility and state |
|---|---|---|
| `InputValidator` | `validate(request) -> RunPlan` | Checks revisions, patch applicability, and test paths. |
| `WorkspaceManager` | `prepare(plan) -> WorkspacePair` | Owns disposable checkouts; never modifies the user checkout. |
| `SandboxRunner` | `run(spec) -> ExecutionResult` | Owns resource limits, environment, and cleanup. |
| `PytestAdapter` | `parse(report) -> TestResults` | Normalizes outcomes and infrastructure errors. |
| `EvidenceClassifier` | `classify(base, patched, expectations) -> Verdict` | Checks fail-before/pass-after and failure category. |
| `ReportBuilder` | `build(manifest, results) -> Report` | Links logs, hashes, and verdict reasons. |

### Data and state ownership

Run(baseSHA, patchHash, testHash, environmentHash, status); Execution(revisionKind, command, exitCode, timeout, resultRefs); TestOutcome(nodeId, category, message); Verdict(status, evidence). Verdicts: supported, not_reproduced, fix_failed, regression_detected, inconclusive.

### Invariants

Both variants use identical regression-test content and equivalent environments. A collection/import error is not accepted as expected bug reproduction unless the bug itself explicitly concerns that behavior. User checkout remains untouched. Test modifications from the patch must not silently replace the supplied regression test.

### Failure and concurrency behavior

Timeouts and environment setup failures are inconclusive. Reject patches escaping allowed paths. Do not inherit secrets into test processes. Restrict network, mounts, CPU, memory, and runtime. A container is not an absolute security boundary; choose the runner according to the trust level of the code.

## SOLID decisions

- **Single responsibility:** InputValidator owns input interpretation; ReportBuilder owns its separate output or integration concern. Domain evaluation does not move into CLI handlers.
- **Open closed:** introduce a new supported adapter behind an existing contract; add new domain behavior explicitly rather than adding hidden project-name switches.
- **Liskov substitution:** adapters must preserve documented result, error, cancellation, and completeness semantics. Run the same contract fixtures against every implementation; unsupported behavior must be explicit.
- **Interface segregation:** separate inspection from mutation and execution from reporting. Consumers receive only the operations they use.
- **Dependency inversion:** domain logic consumes typed contracts; the CLI or composition root wires concrete filesystem, transport, and provider implementations. Pure transformations stay functions instead of gaining unnecessary interfaces.

## LLM system design

Core verification requires no LLM. Later, an assistant may propose a regression test from an issue and patch. Store that proposal separately and evaluate it via execution; reject tests that merely mirror implementation or pass on both revisions.

When optional model calls are introduced, version prompts and output schemas, validate every response, bound tokens/time/cost, and store source references. Treat retrieved files and tool output as data. Keep model output out of authorization and deterministic pass/fail decisions. Document which content leaves the machine.

## Installation and integration design

The following command names are proposed interfaces for this project; they are not claims that published packages exist. Original project code uses the MIT License; third-party dependencies retain their own licenses. Reserve a package name and publish only after the clean-install gate passes.

```text
patchproof run --base BASE_SHA --patch fix.diff --test tests/test_regression.py
patchproof report runs/latest
```

**Public SDK contract:**

```text
verify_patch(request: VerificationRequest) -> VerificationResult
```

Provide one end-to-end example with pinned supported dependencies. Keep the CLI a wrapper over the public SDK. Document configuration discovery, schema version, error categories, supported platforms, and exit codes. For check-oriented commands, distinguish success, failed checks, and incomplete/infrastructure failure. MCP integrations should expose narrow tools and validate configured roots; a plugin packages instructions and connection configuration rather than duplicating the engine.

## Repository structure

```text
src/
  core/             # Domain types, state, and evaluation
  adapters/         # External protocols, analyzers, runners, or storage
  cli/              # User commands and composition
tests/
  unit/
  integration/
  fixtures/
examples/
docs/
  decisions/
  api/
```

Add a report UI or server directory only when that milestone begins. Keep runtime artifacts and any credential files out of version control. Do not create a shared framework spanning these seven independent projects.

## Implementation roadmap

| Phase | Working deliverable | Verification gate |
|---|---|---|
| 1. Create known bug fixtures | Prepare several tiny repositories with expected results. | Each has an independently documented failure reason. |
| 2. Prepare isolated variants | Apply patches to disposable snapshots. | User files remain unchanged, including uncommitted work. |
| 3. Execute and normalize tests | Implement sandbox and pytest report parsing. | Limits and setup failures produce explicit outcomes. |
| 4. Classify evidence | Compare identical tests across variants. | All fixture verdicts match expectations. |
| 5. Check existing behavior | Run configured relevant test suites. | Regression failures appear separately from fix evidence. |
| 6. Publish integration | Ship CLI, reports, and CI example; add optional test generation later. | A maintainer can inspect a complete run from artifacts. |

Proceed in order. Each phase should finish with a runnable example and its verification evidence. Size the next phase after measuring the current one; no fixed delivery date is assumed.

## Testing and evaluation

Fixtures: correct fix, unrelated patch, test passing on both revisions, test failing on both, syntax error, dependency mismatch, flaky test, timeout, malicious path patch, and attempted secret/network access.

Release gate: all fixture verdicts are correct; original working tree hashes are unchanged; logs identify environment failures separately. Track flaky outcomes through repeated execution and report uncertainty instead of forcing a verdict.

Use unit tests for pure rules and integration tests at external boundaries. Maintain a held-out set for model-dependent behavior. Record run counts, versions, and incomplete cases. Do not call a system production-ready based only on seeded fixtures.

## Operations and release

- Start local-first. Log structured event IDs, durations, completeness, and errors without secrets; make detailed source capture explicit.
- Version configuration and stored artifact schemas. Validate compatibility before loading older artifacts; migrate a copy and retain the original.
- Pin supported integration versions in examples and test the documented minimum/current range before releases.
- Build distributable artifacts in CI and test installation in a clean environment. Publish release notes, a changelog, contribution instructions, and a security-reporting route.
- Roll back by pinning the previous package version. Keep baseline artifacts readable; do not overwrite them during a failed upgrade.
- A future hosted dashboard requires authentication, tenant isolation, retention/deletion controls, job quotas, and tested backups. Those are a separate release, not implicit MVP features.

## Learning outcomes

Build the deterministic core to practice data modeling and LLD. Trace the process and storage boundaries to practice HLD. Package the CLI/SDK to learn API stability and developer experience. Add model evaluation only where the product needs it. Use the optional report UI to learn full-stack integration around meaningful domain results.

## Open decisions and risks

Flaky tests and environmental changes can imitate fail-before/pass-after evidence. Re-run suspicious cases and retain environment hashes. Installation and sandbox support differ by host; document supported platforms before release.

Before a public release: confirm supported platforms and dependency versions, review third-party license obligations alongside the selected MIT License for original project code, check naming conflicts, and find pilot users. These are release inputs rather than reasons to expand the initial scope.

## Delivery checklist

- [ ] Product hypothesis tested with target developers
- [x] First vertical slice implemented
- [x] Local domain and integration verification gates passed, including Docker
- [ ] Model-dependent behavior evaluated, if present
- [x] Clean-install example verified
- [x] Local documentation and package artifacts reviewed
- [ ] PyPI package release published
- [ ] Independent pilot completed
