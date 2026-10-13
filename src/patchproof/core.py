from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FailureExpectation:
    node_id: str
    message_contains: str
    exception_type: str | None = None


@dataclass(frozen=True)
class VerificationRequest:
    repo: Path
    base: str
    patch: Path
    test: Path
    expected_failure: str
    output: Path
    timeout_seconds: float = 30
    existing_tests: tuple[str, ...] = ()
    repeat_count: int = 1
    expectations: tuple[FailureExpectation, ...] = ()
    dependency_manifest: Path | None = None


@dataclass
class CaseOutcome:
    node_id: str
    status: str
    message: str = ""
    exception_type: str | None = None


@dataclass
class ExecutionResult:
    status: str  # passed, failed, inconclusive
    tests: int = 0
    failures: list[str] = field(default_factory=list)
    reason: str = ""
    return_code: int | None = None
    elapsed_seconds: float = 0
    stdout: str = ""
    stderr: str = ""
    node_ids: list[str] = field(default_factory=list)
    cases: list[CaseOutcome] = field(default_factory=list)
    junit_xml: str = ""
    command: list[str] = field(default_factory=list)


def classify(base: ExecutionResult, patched: ExecutionResult, expected: str,
             existing_base: ExecutionResult | None = None,
             existing_patched: ExecutionResult | None = None,
             expectations: tuple[FailureExpectation, ...] = ()) -> tuple[str, str]:
    """Conservative evidence classifier; infrastructure errors never reproduce bugs."""
    if not expected.strip() and not expectations:
        return "inconclusive", "An explicit expected failure marker is required."
    if base.status == "inconclusive" or patched.status == "inconclusive":
        return "inconclusive", "Regression execution was incomplete or had setup/collection errors."
    if any(r.status not in ("passed", "failed") or r.tests < 1 for r in (base, patched)):
        return "inconclusive", "Invalid normalized regression result."
    if base.status == "passed":
        return "not_reproduced", "The supplied regression test already passes on the base revision."
    if expectations:
        wanted = {e.node_id: e for e in expectations}
        actual = {c.node_id: c for c in base.cases if c.status == "failed"}
        if len(wanted) != len(expectations) or set(actual) != set(wanted):
            return "inconclusive", "Base failing case identities do not match the explicit expectations."
        for node_id, contract in wanted.items():
            case = actual[node_id]
            if not contract.message_contains or contract.message_contains not in case.message:
                return "inconclusive", f"Expected failure message did not match case {node_id}."
            if contract.exception_type and contract.exception_type != case.exception_type:
                return "inconclusive", f"Expected exception type did not match case {node_id}."
    elif not base.failures or any(expected not in failure for failure in base.failures):
        return "inconclusive", "Base failures do not all match the expected failure marker."
    if patched.status == "failed":
        return "fix_failed", "The regression test still fails on the patched revision."
    if base.tests != patched.tests:
        return "inconclusive", "The two variants collected different numbers of regression cases."
    if base.node_ids != patched.node_ids:
        return "inconclusive", "The two variants collected different regression case identities."
    if existing_base is not None or existing_patched is not None:
        if existing_base is None or existing_patched is None:
            return "inconclusive", "Only one existing-suite result was supplied."
        if existing_base.status != "passed" or existing_patched.status == "inconclusive":
            return "inconclusive", "Existing-suite baseline or patched execution was not clean."
        if existing_patched.status == "failed":
            return "regression_detected", "Existing tests pass on base but fail after the patch."
        if existing_base.tests != existing_patched.tests:
            return "inconclusive", "Existing-suite collection count changed."
        if existing_base.node_ids != existing_patched.node_ids:
            return "inconclusive", "Existing-suite case identities changed."
    return "supported", "Expected fail-before/pass-after evidence observed; this is not a proof of correctness."


def aggregate_attempts(attempts: list[dict]) -> tuple[str, str]:
    """Different test outcomes imply flakiness; infrastructure/evidence drift is inconsistent."""
    if not attempts:
        return "inconclusive", "No repetitions completed."
    for phase in ("base", "patched", "existing_base", "existing_patched"):
        results = [a["results"].get(phase) for a in attempts]
        available = [r for r in results if r is not None]
        if not available:
            continue
        if any(r.status == "inconclusive" for r in available):
            if any(r.status != "inconclusive" for r in available):
                return "inconsistent", f"{phase} alternated between complete and incomplete execution."
            continue
        if any(r.node_ids != available[0].node_ids for r in available):
            return "inconsistent", f"{phase} collected different case identities across repetitions."
        signatures = {tuple((c.node_id, c.status) for c in r.cases) or (("suite", r.status),) for r in available}
        if len(signatures) > 1:
            return "flaky", f"{phase} produced different case outcomes across equivalent repetitions."
    verdicts = {a["verdict"] for a in attempts}
    if len(verdicts) != 1:
        return "inconsistent", "Repeated evidence produced different verdicts or failure reasons."
    return attempts[0]["verdict"], attempts[0]["reason"]
