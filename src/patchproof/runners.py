from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import signal
import site
import stat
import subprocess
import sys
import tempfile
import time
from typing import Protocol
import uuid
import xml.etree.ElementTree as ET

from .core import CaseOutcome, ExecutionResult

LOG_LIMIT = 256_000
XML_LIMIT = 2_000_000


def read_xml(path: Path) -> str:
    """Do not follow a result-file symlink back into the host filesystem."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > XML_LIMIT:
            raise ValueError("JUnit result must be a regular file of at most 2 MB")
        raw = stream.read(XML_LIMIT + 1)
        if len(raw) > XML_LIMIT:
            raise ValueError("JUnit result exceeded its size limit")
        return raw.decode("utf-8")


def parse_junit(path: Path, return_code: int, elapsed: float = 0) -> ExecutionResult:
    try:
        xml = read_xml(path)
        root = ET.fromstring(xml)
        cases = list(root.iter("testcase"))
        errors = list(root.iter("error"))
        skips = list(root.iter("skipped"))
        failures = ["\n".join((f.get("message", ""), f.text or "")) for f in root.iter("failure")]
        outcomes = []
        for case in cases:
            node_id = f'{case.get("classname", "")}::{case.get("name", "")}'
            failure = case.find("failure")
            category = "failed" if failure is not None else "error" if case.find("error") is not None else "skipped" if case.find("skipped") is not None else "passed"
            message = "\n".join((failure.get("message", ""), failure.text or "")) if failure is not None else ""
            match = re.search(r"(?:^|\n)(?:E\s+)?([A-Za-z_][\w.]*(?:Error|Exception)|AssertionError|Failed):", message)
            exception_type = match.group(1).rsplit(".", 1)[-1] if match else None
            outcomes.append(CaseOutcome(node_id, category, message, exception_type))
        outcomes.sort(key=lambda c: c.node_id)
        extra = {"node_ids": [c.node_id for c in outcomes], "cases": outcomes, "junit_xml": xml}
        if return_code not in (0, 1):
            return ExecutionResult("inconclusive", reason=f"pytest exited {return_code}: collection/setup/runtime failure",
                                   return_code=return_code, elapsed_seconds=elapsed, **extra)
        if not cases or errors or skips:
            return ExecutionResult("inconclusive", len(cases), failures,
                                   "No cases, skipped cases, or setup/collection errors", return_code, elapsed, **extra)
        if (return_code == 0 and failures) or (return_code == 1 and not failures):
            return ExecutionResult("inconclusive", reason="Exit code and JUnit results disagree", return_code=return_code)
        return ExecutionResult("failed" if failures else "passed", len(cases), failures,
                               return_code=return_code, elapsed_seconds=elapsed,
                               **extra)
    except (OSError, ET.ParseError, ValueError, UnicodeError):
        return ExecutionResult("inconclusive", reason="Missing, unsafe, oversized or malformed JUnit report", return_code=return_code,
                               elapsed_seconds=elapsed)


def execute(command: list[str], cwd: Path, env: dict[str, str], timeout: float,
            junit: Path) -> ExecutionResult:
    start = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                                       start_new_session=True)
        except OSError as exc:
            return ExecutionResult("inconclusive", reason=f"Runner could not start: {exc}")
        try:
            return_code = process.wait(timeout=timeout)
            result = parse_junit(junit, return_code, time.monotonic() - start)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            result = ExecutionResult("inconclusive", reason="Execution timed out", elapsed_seconds=time.monotonic() - start)
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
        stdout.seek(0)
        stderr.seek(0)
        result.stdout = stdout.read(LOG_LIMIT).decode("utf-8", "replace")
        result.stderr = stderr.read(LOG_LIMIT).decode("utf-8", "replace")
        result.command = command
        return result


class Runner(Protocol):
    def run(self, workspace: Path, selectors: tuple[str, ...], *, timeout: float,
            regression: bool) -> ExecutionResult: ...
    def describe(self) -> dict: ...


def pytest_arguments(selectors: tuple[str, ...], junit: str, regression: bool) -> list[str]:
    args = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml=" + junit,
            "-o", "junit_family=xunit2"]
    if regression:
        args += ["-c", ".patchproof_regression/pytest.ini", "--confcutdir=.patchproof_regression"]
    return args + list(selectors)


class TrustedLocalRunner:
    """No security isolation. Only caller-owned, reviewed repository/test code."""
    def __init__(self, *, trust_confirmed: bool = False):
        if not trust_confirmed:
            raise ValueError("Local execution requires trust_confirmed=True; a subprocess is not a sandbox")

    def describe(self) -> dict:
        packages = sorted({(d.metadata.get("Name", "unknown").lower().replace("_", "-"), d.version) for d in metadata.distributions()})
        distributions = [f"{name}=={version}" for name, version in packages]
        return {"runner": "trusted-local", "python": sys.version, "executable": sys.executable,
                "python_version": platform.python_version(), "platform": platform.platform(),
                "packages": [{"name": name, "version": version} for name, version in packages],
                "isolation": "none", "pytest_plugin_autoload": "disabled",
                "installed_distributions_sha256": hashlib.sha256("\n".join(distributions).encode()).hexdigest()}

    def run(self, workspace: Path, selectors: tuple[str, ...], *, timeout: float,
            regression: bool) -> ExecutionResult:
        with tempfile.TemporaryDirectory(prefix="patchproof-result-") as folder:
            junit = Path(folder) / "junit.xml"
            env = {"PATH": os.defpath, "HOME": folder, "TMPDIR": folder,
                   "PYTHONPATH": os.pathsep.join((str(workspace), str(workspace / "src"), site.getusersitepackages())),
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                   "PYTHONHASHSEED": "0", "LANG": "C.UTF-8"}
            return execute([sys.executable, *pytest_arguments(selectors, str(junit), regression)],
                           workspace, env, timeout, junit)


@dataclass
class DockerRunner:
    """Opt-in Docker adapter. A hardened container is not a hostile-code VM boundary."""
    image: str
    _resolved_image: str | None = field(default=None, init=False)
    _manifest: dict | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not self.image or self.image.startswith("-"):
            raise ValueError("A locally built Docker image is required")

    def _resolve(self, timeout: float = 10) -> None:
        if self._resolved_image is not None:
            return
        inspect = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", self.image],
                                 capture_output=True, text=True, timeout=min(timeout, 10))
        if inspect.returncode or not inspect.stdout.strip().startswith("sha256:"):
            raise ValueError("Docker image unavailable locally or daemon inaccessible")
        self._resolved_image = inspect.stdout.strip()

    def describe(self) -> dict:
        info = {"runner": "docker", "image": self.image, "network": "none",
                "isolation": "container; not a guarantee against hostile code"}
        try:
            self._resolve()
            if self._manifest is None:
                script = ('import importlib.metadata as m,json,platform;'
                          'print(json.dumps({"python_version":platform.python_version(),'
                          '"platform":platform.platform(),"packages":[{"name":n,"version":v} '
                          'for n,v in sorted({(d.metadata.get("Name","unknown").lower().replace("_","-"),d.version) '
                          'for d in m.distributions()})]}))')
                name = "patchproof-manifest-" + uuid.uuid4().hex
                try:
                    process = subprocess.run(["docker", "run", "--rm", "--name", name, "--pull=never", "--network=none", "--read-only",
                                              "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
                                              "--pids-limit=64", "--memory=256m", "--cpus=1", "--entrypoint=python",
                                              self._resolved_image, "-c", script], capture_output=True, text=True, timeout=15)
                finally:
                    try:
                        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                if process.returncode:
                    raise ValueError("Docker environment manifest could not be collected")
                self._manifest = json.loads(process.stdout)
                if not isinstance(self._manifest, dict) or not isinstance(self._manifest.get("packages"), list):
                    raise ValueError("Invalid Docker dependency manifest")
            info.update(self._manifest)
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            info["manifest_error"] = str(exc)
        info["image_id"] = self._resolved_image or "unresolved"
        return info

    def run(self, workspace: Path, selectors: tuple[str, ...], *, timeout: float,
            regression: bool) -> ExecutionResult:
        if self._resolved_image is None:
            try:
                self._resolve(timeout)
            except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                return ExecutionResult("inconclusive", reason=f"Docker preflight failed: {exc}")
        name = "patchproof-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory(prefix="patchproof-result-") as folder:
            Path(folder).chmod(0o777)
            junit = Path(folder) / "junit.xml"
            command = ["docker", "run", "--rm", "--pull=never", "--name", name,
                       "--network=none", "--read-only", "--cap-drop=ALL",
                       "--security-opt=no-new-privileges", "--pids-limit=64", "--memory=512m",
                       "--cpus=1", "--ulimit", "fsize=10485760:10485760", "--user=65534:65534",
                       "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--workdir=/work",
                       "-v", f"{workspace}:/work:ro", "-v", f"{folder}:/results:rw",
                       "-e", "PYTHONPATH=/work:/work/src", "-e", "PYTHONDONTWRITEBYTECODE=1",
                       "-e", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1", "-e", "PYTHONHASHSEED=0",
                       "--entrypoint=python", self._resolved_image,
                       *pytest_arguments(selectors, "/results/junit.xml", regression)]
            try:
                # These configure the host Docker client, never the container test environment.
                client_env = {key: os.environ[key] for key in
                              ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
                               "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY") if key in os.environ}
                return execute(command, workspace, client_env,
                               timeout, junit)
            finally:
                try:
                    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    pass
