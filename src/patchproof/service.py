from __future__ import annotations

from dataclasses import asdict
import hashlib
import html
import json
from pathlib import Path
import tempfile

from .core import ExecutionResult, VerificationRequest, aggregate_attempts, classify
from .runners import Runner
from .workspace import RESERVED, apply_patch, safe_path, snapshot, validate_patch


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_dependencies(required: dict, actual: dict) -> None:
    if not isinstance(required, dict) or required.get("schema_version") != 1:
        raise ValueError("Dependency manifest must have schema_version 1")
    if set(required) - {"schema_version", "python_version", "packages"}:
        raise ValueError("Unknown dependency manifest fields")
    if actual.get("manifest_error"):
        raise ValueError(actual["manifest_error"])
    if required.get("python_version") and required["python_version"] != actual.get("python_version"):
        raise ValueError("Execution Python version does not match the dependency manifest")
    packages = required.get("packages", {})
    if not isinstance(packages, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in packages.items()):
        raise ValueError("Dependency packages must map names to exact version strings")
    installed = {p["name"].lower().replace("_", "-"): p["version"] for p in actual.get("packages", [])}
    for name, version in packages.items():
        if installed.get(name.lower().replace("_", "-")) != version:
            raise ValueError(f"Dependency version mismatch: {name} requires {version}")


def write_reports(output: Path, result: dict, artifacts: dict[str, bytes] | None = None) -> None:
    output.mkdir(parents=True, exist_ok=False)
    for relative, content in (artifacts or {}).items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (output / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output / "environment.json").write_text(json.dumps(result["environment"], indent=2), encoding="utf-8")
    links = "".join(f'<li><a href="{html.escape(name, quote=True)}">{html.escape(name)}</a></li>' for name in (artifacts or {}))
    content = html.escape(json.dumps(result, indent=2))
    (output / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>PatchProof report</title>'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px}'
        'pre{white-space:pre-wrap;background:#f3f5f8;padding:20px;border-radius:8px}li{margin:8px 0}</style>'
        f'<h1>PatchProof: {html.escape(result["verdict"])}</h1>'
        f'<p>{html.escape(result["reason"])}</p><h2>Original artifacts</h2><ul>{links}</ul>'
        '<p><a href="environment.json">Execution environment and dependencies</a></p>'
        f'<details><summary>Complete execution evidence</summary><pre>{content}</pre></details></html>', encoding="utf-8")


def serialize_execution(result: ExecutionResult, prefix: str, artifacts: dict[str, bytes]) -> dict:
    value = asdict(result)
    xml = value.pop("junit_xml")
    references = {}
    for filename, content in (("junit.xml", xml), ("stdout.txt", result.stdout), ("stderr.txt", result.stderr)):
        if filename == "junit.xml" and not xml:
            continue
        path = f"artifacts/{prefix}/{filename}"
        data = content.encode("utf-8")
        artifacts[path] = data
        references[filename] = {"path": path, "sha256": digest(data)}
    value["artifacts"] = references
    return value


def verify_patch(request: VerificationRequest, *, runner: Runner) -> dict:
    repo = Path(request.repo).resolve()
    output = Path(request.output).resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Report output must be outside the source checkout")
    if output.exists():
        raise ValueError("Report output already exists; choose a new path")
    if not request.expected_failure.strip() and not request.expectations:
        raise ValueError("Expected failure marker or per-case expectations are required")
    if not (0 < request.timeout_seconds <= 3600):
        raise ValueError("Timeout must be between 0 and 3600 seconds")
    if isinstance(request.repeat_count, bool) or not isinstance(request.repeat_count, int) or not 1 <= request.repeat_count <= 20:
        raise ValueError("Repeat count must be an integer between 1 and 20")
    if not request.base or request.base.startswith("-"):
        raise ValueError("Invalid base revision")
    if Path(request.test).suffix != ".py":
        raise ValueError("A reviewed .py test is required; proposed files must be reviewed and renamed explicitly")
    if len({c.node_id for c in request.expectations}) != len(request.expectations):
        raise ValueError("Per-case failure expectations must have unique node IDs")
    for case in request.expectations:
        if not case.node_id.strip() or not case.message_contains.strip():
            raise ValueError("Per-case expectations need a node ID and non-empty message")
    for selector in request.existing_tests:
        path = selector.split("::", 1)[0]
        if selector.startswith("-"):
            raise ValueError("Test selectors must be paths, not pytest options")
        safe_path(path)
    patch = Path(request.patch).read_bytes()
    test = Path(request.test).read_bytes()
    validate_patch(patch)
    environment = runner.describe()
    if environment.get("manifest_error"):
        raise ValueError(environment["manifest_error"])
    required = None
    if request.dependency_manifest is not None:
        required = json.loads(Path(request.dependency_manifest).read_text(encoding="utf-8"))
        validate_dependencies(required, environment)
    attempts = []
    artifacts: dict[str, bytes] = {}
    serialized = []
    with tempfile.TemporaryDirectory(prefix="patchproof-workspaces-") as root:
        pair = Path(root)
        sha = None
        for index in range(request.repeat_count):
            attempt_root = pair / f"attempt-{index + 1:03}"
            attempt_root.mkdir()
            base, patched = attempt_root / "base", attempt_root / "patched"
            sha = snapshot(repo, sha or request.base, base)
            snapshot(repo, sha, patched)
            apply_patch(patched, patch)
            for folder in (base, patched):
                injected = folder / RESERVED
                injected.mkdir()
                (injected / "test_regression.py").write_bytes(test)
                (injected / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            selector = (f"{RESERVED}/test_regression.py",)
            results = {
                "base": runner.run(base, selector, timeout=request.timeout_seconds, regression=True),
                "patched": runner.run(patched, selector, timeout=request.timeout_seconds, regression=True),
            }
            if request.existing_tests:
                for label, patched_variant in (("existing_base", False), ("existing_patched", True)):
                    folder = attempt_root / label
                    snapshot(repo, sha, folder)
                    if patched_variant:
                        apply_patch(folder, patch)
                    results[label] = runner.run(folder, request.existing_tests,
                                                timeout=request.timeout_seconds, regression=False)
            verdict, reason = classify(results["base"], results["patched"], request.expected_failure,
                                       results.get("existing_base"), results.get("existing_patched"), request.expectations)
            attempts.append({"verdict": verdict, "reason": reason, "results": results})
            serialized.append({"number": index + 1, "verdict": verdict, "reason": reason,
                               "executions": {label: serialize_execution(value, f"attempt-{index + 1:03}/{label}", artifacts)
                                              for label, value in results.items()}})
        verdict, reason = aggregate_attempts(attempts)
        result = {"schema_version": 2, "verdict": verdict, "reason": reason,
                  "base_sha": sha, "patch_sha256": digest(patch), "test_sha256": digest(test),
                  "environment": environment,
                  "environment_sha256": digest(json.dumps(environment, sort_keys=True).encode()),
                  "dependency_requirements": required,
                  "expected_failure": request.expected_failure,
                  "case_expectations": [asdict(e) for e in request.expectations],
                  "executions": {k: v for k, v in serialized[0]["executions"].items() if k in ("base", "patched")},
                  "existing_suite": "not requested", "repeat_count": request.repeat_count,
                  "attempts": serialized}
        if request.existing_tests:
            result["existing_suite"] = {"base": serialized[0]["executions"]["existing_base"],
                                        "patched": serialized[0]["executions"]["existing_patched"]}
    write_reports(output, result, artifacts)
    return result
