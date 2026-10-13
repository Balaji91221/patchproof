"""Run only these authored, harmless fixture files with explicit local trust."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from patchproof import VerificationRequest, verify_patch
from patchproof.runners import DockerRunner, TrustedLocalRunner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--docker-image")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="patchproof-demo-") as folder:
        root = Path(folder)
        repo = root / "repo"
        repo.mkdir()
        def git(*parts):
            return subprocess.check_output(["git", *parts], cwd=repo, stderr=subprocess.PIPE)
        git("init", "-q")
        (repo / "calculator.py").write_text("def add(a, b):\n    return a - b\n")
        git("add", ".")
        git("-c", "user.name=Demo", "-c", "user.email=demo@example.invalid", "commit", "-qm", "bug")
        (repo / "calculator.py").write_text("def add(a, b):\n    return a + b\n")
        patch = root / "fix.diff"
        patch.write_bytes(git("diff"))
        test = root / "test_regression.py"
        test.write_text('from calculator import add\ndef test_add():\n    assert add(2, 1) == 3, "BUG_ADD"\n')
        runner = DockerRunner(args.docker_image) if args.docker_image else TrustedLocalRunner(trust_confirmed=True)
        result = verify_patch(VerificationRequest(repo, "HEAD", patch, test, "BUG_ADD", args.output), runner=runner)
        print(json.dumps({"verdict": result["verdict"], "reason": result["reason"], "report": str(args.output)}, indent=2))
        return 0 if result["verdict"] == "supported" else 1


if __name__ == "__main__":
    raise SystemExit(main())
