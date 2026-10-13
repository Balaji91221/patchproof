import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from patchproof import ExecutionResult, VerificationRequest, classify, verify_patch
from patchproof.cli import main
from patchproof.runners import DockerRunner, TrustedLocalRunner, parse_junit
from patchproof.workspace import safe_path, validate_patch


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.failed = ExecutionResult("failed", 1, ["AssertionError: BUG_ADD"])
        self.passed = ExecutionResult("passed", 1)

    def test_supported(self):
        self.assertEqual(classify(self.failed, self.passed, "BUG_ADD")[0], "supported")

    def test_not_reproduced(self):
        self.assertEqual(classify(self.passed, self.passed, "BUG_ADD")[0], "not_reproduced")

    def test_fix_failed(self):
        self.assertEqual(classify(self.failed, self.failed, "BUG_ADD")[0], "fix_failed")

    def test_wrong_failure_reason(self):
        self.assertEqual(classify(self.failed, self.passed, "OTHER_BUG")[0], "inconclusive")

    def test_incomplete_is_not_evidence(self):
        self.assertEqual(classify(ExecutionResult("inconclusive"), self.passed, "BUG_ADD")[0], "inconclusive")

    def test_collection_count_must_match(self):
        self.assertEqual(classify(self.failed, ExecutionResult("passed", 2), "BUG_ADD")[0], "inconclusive")

    def test_existing_regression(self):
        self.assertEqual(classify(self.failed, self.passed, "BUG_ADD", self.passed, self.failed)[0], "regression_detected")

    def test_existing_baseline_failure_inconclusive(self):
        self.assertEqual(classify(self.failed, self.passed, "BUG_ADD", self.failed, self.failed)[0], "inconclusive")

    def test_empty_expectation(self):
        self.assertEqual(classify(self.failed, self.passed, "")[0], "inconclusive")

    def test_zero_case_results_are_inconclusive(self):
        self.failed.tests = 0
        self.passed.tests = 0
        self.assertEqual(classify(self.failed, self.passed, "BUG_ADD")[0], "inconclusive")

    def test_same_count_different_case_id_is_inconclusive(self):
        self.failed.node_ids = ["test::before"]
        self.passed.node_ids = ["test::after"]
        self.assertEqual(classify(self.failed, self.passed, "BUG_ADD")[0], "inconclusive")


class BoundaryTests(unittest.TestCase):
    def test_unsafe_paths(self):
        for path in ("../escape", "/tmp/escape", ".git/config", "x/../../escape", "x\\escape", ".patchproof_regression/x"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(path)

    def test_reject_malicious_patch_path(self):
        with self.assertRaises(ValueError):
            validate_patch(b"diff --git a/../escape b/../escape\n")

    def test_reject_symlink_patch(self):
        with self.assertRaises(ValueError):
            validate_patch(b"diff --git a/x b/x\nnew file mode 120000\n")

    def test_reject_regression_test_override(self):
        with self.assertRaises(ValueError):
            validate_patch(b"diff --git a/.patchproof_regression/test_regression.py b/.patchproof_regression/test_regression.py\n")

    def test_local_requires_opt_in(self):
        with self.assertRaises(ValueError):
            TrustedLocalRunner()

    def test_junit_collection_error(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "junit.xml"
            report.write_text('<testsuites><testsuite><testcase><error message="ImportError"/></testcase></testsuite></testsuites>')
            self.assertEqual(parse_junit(report, 1).status, "inconclusive")

    def test_skipped_is_not_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "junit.xml"
            report.write_text('<testsuite><testcase><skipped/></testcase></testsuite>')
            self.assertEqual(parse_junit(report, 0).status, "inconclusive")

    def test_missing_report(self):
        self.assertEqual(parse_junit(Path("/does/not/exist"), 0).status, "inconclusive")

    def test_docker_missing_image_is_inconclusive(self):
        with patch("patchproof.runners.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "unavailable")):
            result = DockerRunner("fixture:local").run(Path("/tmp"), ("test.py",), timeout=3, regression=False)
        self.assertEqual(result.status, "inconclusive")

    def test_docker_constraints_and_image_pinning(self):
        runner = DockerRunner("fixture:local")
        with patch("patchproof.runners.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "sha256:fixture\n", "")) as process, \
             patch("patchproof.runners.execute", return_value=ExecutionResult("passed", 1)) as execute:
            runner.run(Path("/tmp"), ("test.py",), timeout=3, regression=False)
            runner.run(Path("/tmp"), ("test.py",), timeout=3, regression=False)
        command = execute.call_args.args[0]
        for required in ("--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534", "--pull=never", "sha256:fixture"):
            self.assertIn(required, command)
        self.assertEqual(sum(call.args[0][1:3] == ["image", "inspect"] for call in process.call_args_list), 1)
        self.assertEqual(sum(call.args[0][1:3] == ["rm", "-f"] for call in process.call_args_list), 2)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        (self.repo / "calculator.py").write_text("def add(a, b):\n    return a - b\n")
        (self.repo / "test_existing.py").write_text("from calculator import add\ndef test_zero():\n    assert add(0, 0) == 0\n")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "base")
        (self.repo / "calculator.py").write_text("def add(a, b):\n    return a + b\n")
        self.patch = self.root / "fix.diff"
        self.patch.write_bytes(self.git("diff", "--", "calculator.py"))
        # User's dirty checkout intentionally differs from both analyzed snapshots.
        (self.repo / "calculator.py").write_text("USER_UNCOMMITTED_WORK = True\n")
        (self.repo / "personal.txt").write_text("preserve this untracked file\n")
        self.test = self.root / "regression.py"
        self.test.write_text('from calculator import add\ndef test_add():\n    assert add(2, 1) == 3, "BUG_ADD"\n')
        self.runner = TrustedLocalRunner(trust_confirmed=True)
        self.output_count = 0

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.PIPE)

    def request(self, **changes):
        self.output_count += 1
        values = dict(repo=self.repo, base="HEAD", patch=self.patch, test=self.test,
                      expected_failure="BUG_ADD", output=self.root / f"report-{self.output_count}", timeout_seconds=10)
        values.update(changes)
        return VerificationRequest(**values)

    def test_end_to_end_and_checkout_preservation(self):
        before = {str(p.relative_to(self.repo)): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}
        request = self.request(existing_tests=("test_existing.py",))
        result = verify_patch(request, runner=self.runner)
        after = {str(p.relative_to(self.repo)): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}
        self.assertEqual(result["verdict"], "supported")
        self.assertEqual(before, after)
        self.assertEqual(result["executions"]["base"]["status"], "failed")
        self.assertEqual(result["executions"]["patched"]["status"], "passed")
        self.assertEqual(json.loads((request.output / "report.json").read_text())["test_sha256"], result["test_sha256"])
        self.assertIn("PatchProof: supported", (request.output / "report.html").read_text())

    def test_collection_error_is_inconclusive(self):
        self.test.write_text("import module_that_does_not_exist_938247\n")
        result = verify_patch(self.request(), runner=self.runner)
        self.assertEqual(result["verdict"], "inconclusive")

    def test_timeout_is_inconclusive(self):
        self.test.write_text("import time\ndef test_wait():\n    time.sleep(20)\n")
        result = verify_patch(self.request(timeout_seconds=0.2), runner=self.runner)
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertEqual(result["executions"]["base"]["reason"], "Execution timed out")

    def test_report_cannot_write_into_checkout(self):
        with self.assertRaises(ValueError):
            verify_patch(self.request(output=self.repo / "reports"), runner=self.runner)

    def test_existing_evidence_not_overwritten(self):
        output = self.root / "existing-report"
        output.mkdir()
        (output / "report.json").write_text("keep")
        with self.assertRaises(ValueError):
            verify_patch(self.request(output=output), runner=self.runner)
        self.assertEqual((output / "report.json").read_text(), "keep")

    def test_invalid_patch_does_not_touch_source(self):
        self.patch.write_text("diff --git a/../outside b/../outside\n")
        with self.assertRaises(ValueError):
            verify_patch(self.request(), runner=self.runner)
        self.assertFalse((self.root / "outside").exists())

    def test_revision_options_rejected(self):
        with self.assertRaises(ValueError):
            verify_patch(self.request(base="--help"), runner=self.runner)

    def test_pytest_options_not_accepted_as_selectors(self):
        with self.assertRaises(ValueError):
            verify_patch(self.request(existing_tests=("--pyargs",)), runner=self.runner)

    def test_host_secret_environment_is_not_inherited(self):
        self.test.write_text('import os\ndef test_environment():\n    assert "PATCHPROOF_TEST_SECRET" not in os.environ\n')
        with patch.dict(os.environ, {"PATCHPROOF_TEST_SECRET": "fixture-only-not-a-real-secret"}):
            result = verify_patch(self.request(), runner=self.runner)
        self.assertEqual(result["executions"]["base"]["status"], "passed")
        self.assertEqual(result["executions"]["patched"]["status"], "passed")

    def test_real_existing_regression_detected(self):
        # Fix the target addition case while introducing a separate zero-input defect.
        (self.repo / "calculator.py").write_text("def add(a, b):\n    return a + b if a else 99\n")
        self.patch.write_bytes(self.git("diff", "--", "calculator.py"))
        result = verify_patch(self.request(existing_tests=("test_existing.py",)), runner=self.runner)
        self.assertEqual(result["verdict"], "regression_detected")


if __name__ == "__main__":
    unittest.main()
