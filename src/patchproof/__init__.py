"""Local-first regression evidence. Execution always requires an explicit runner."""
from .core import CaseOutcome, ExecutionResult, FailureExpectation, VerificationRequest, aggregate_attempts, classify
from .service import verify_patch

__all__ = ["CaseOutcome", "ExecutionResult", "FailureExpectation", "VerificationRequest", "aggregate_attempts", "classify", "verify_patch"]
