import argparse
import json
from pathlib import Path
import sys
import subprocess

from .core import FailureExpectation, VerificationRequest
from .proposals import AnthropicProposalAdapter, write_proposal
from .runners import DockerRunner, TrustedLocalRunner
from .service import verify_patch


def load_expectations(path: Path | None) -> tuple[FailureExpectation, ...]:
    if path is None:
        return ()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"schema_version", "cases"} or value["schema_version"] != 1:
        raise ValueError("Expected a version-1 case expectation document")
    if not isinstance(value["cases"], list) or not 1 <= len(value["cases"]) <= 1000:
        raise ValueError("Expectations need 1-1000 cases")
    result = []
    for case in value["cases"]:
        if not isinstance(case, dict) or set(case) - {"node_id", "message_contains", "exception_type"}:
            raise ValueError("Invalid case expectation fields")
        if any(not isinstance(case.get(key), str) or not case[key].strip() for key in ("node_id", "message_contains")):
            raise ValueError("Case expectations need non-empty node_id and message_contains")
        if case.get("exception_type") is not None and (not isinstance(case["exception_type"], str) or not case["exception_type"].strip()):
            raise ValueError("exception_type must be null or a non-empty string")
        result.append(FailureExpectation(**case))
    return tuple(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Python patch regression evidence in disposable snapshots")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--repo", type=Path, default=Path.cwd())
    run.add_argument("--base", required=True)
    run.add_argument("--patch", type=Path, required=True)
    run.add_argument("--test", type=Path, required=True)
    run.add_argument("--expect", default="", help="Required substring of every base regression failure")
    run.add_argument("--expectations", type=Path, help="Per-case JSON failure contracts, stronger than a shared marker")
    run.add_argument("--repeat", type=int, default=1, help="Fresh-snapshot repetitions, 1-20")
    run.add_argument("--dependency-manifest", type=Path, help="Exact Python/package requirements JSON")
    run.add_argument("--output", type=Path, required=True, help="New directory outside source checkout")
    run.add_argument("--timeout", type=float, default=30)
    run.add_argument("--existing", action="append", default=[], help="Relative pytest selector; repeatable")
    runners = run.add_mutually_exclusive_group(required=True)
    runners.add_argument("--trusted-local", action="store_true", help="Explicitly authorize running your reviewed code without sandboxing")
    runners.add_argument("--docker-image", help="Prebuilt local Python/pytest image; execution has no network")
    report = sub.add_parser("report")
    report.add_argument("path", type=Path)
    environment = sub.add_parser("environment", help="Export the execution environment without running repository code")
    environment.add_argument("--docker-image")
    environment.add_argument("--output", type=Path, required=True)
    environment.add_argument("--requirements-only", action="store_true")
    proposal = sub.add_parser("propose", help="Generate an untrusted review-only regression-test proposal")
    proposal.add_argument("--issue", type=Path, required=True)
    proposal.add_argument("--patch", type=Path, required=True)
    proposal.add_argument("--source", type=Path, action="append", default=[])
    proposal.add_argument("--output", type=Path, required=True)
    proposal.add_argument("--model", required=True)
    proposal.add_argument("--allow-remote", action="store_true", help="Authorize sending only selected inputs to Anthropic")
    proposal.add_argument("--max-tokens", type=int, default=2048)
    proposal.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            path = args.path / "report.json" if args.path.is_dir() else args.path
            result = json.loads(path.read_text())
            if not isinstance(result, dict) or result.get("schema_version") not in (1, 2) or result.get("verdict") not in (
                "supported", "not_reproduced", "fix_failed", "regression_detected", "inconclusive", "flaky", "inconsistent"
            ):
                raise ValueError("Unsupported or malformed report schema")
        elif args.command == "environment":
            runner = DockerRunner(args.docker_image) if args.docker_image else TrustedLocalRunner(trust_confirmed=True)
            result = runner.describe()
            if result.get("manifest_error"):
                raise ValueError(result["manifest_error"])
            if args.requirements_only:
                result = {"schema_version": 1, "python_version": result["python_version"],
                          "packages": {p["name"]: p["version"] for p in result["packages"]}}
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2)
            print(json.dumps({"output": str(args.output)}))
            return 0
        elif args.command == "propose":
            result = write_proposal(issue=args.issue, patch=args.patch, sources=tuple(args.source), output=args.output,
                adapter=AnthropicProposalAdapter(args.model, args.allow_remote, args.max_tokens, args.timeout))
            print(json.dumps(result, indent=2))
            return 0
        else:
            runner = TrustedLocalRunner(trust_confirmed=True) if args.trusted_local else DockerRunner(args.docker_image)
            result = verify_patch(VerificationRequest(args.repo, args.base, args.patch, args.test,
                args.expect, args.output, args.timeout, tuple(args.existing), args.repeat,
                load_expectations(args.expectations), args.dependency_manifest), runner=runner)
        print(json.dumps(result, indent=2))
        return 0 if result["verdict"] == "supported" else 2 if result["verdict"] in ("inconclusive", "flaky", "inconsistent") else 1
    except (ValueError, OSError, TimeoutError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"verdict": "inconclusive", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
