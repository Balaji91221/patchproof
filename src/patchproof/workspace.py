from __future__ import annotations

import io
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import tarfile


RESERVED = ".patchproof_regression"


def safe_path(value: str) -> str:
    p = PurePosixPath(value)
    if not value or p.is_absolute() or ".." in p.parts or "\\" in value:
        raise ValueError(f"Unsafe relative path: {value!r}")
    if any(part.casefold() in (".git", RESERVED) for part in p.parts):
        raise ValueError(f"Reserved path: {value!r}")
    return value


def validate_patch(data: bytes) -> None:
    """Accept ordinary text Git patches; reject links, submodules and ambiguous paths."""
    text = data.decode("utf-8")
    found = False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            parts = shlex.split(line)
            if len(parts) != 4:
                raise ValueError("Unsupported diff header")
            for value, prefix in zip(parts[2:], ("a/", "b/")):
                if not value.startswith(prefix):
                    raise ValueError("Patch paths must use a/ and b/ prefixes")
                safe_path(value[2:])
            found = True
        elif line.startswith(("--- ", "+++ ")):
            value = line[4:].split("\t", 1)[0]
            if value == "/dev/null":
                continue
            if not value.startswith(("a/", "b/")):
                raise ValueError("Unsupported patch file header")
            safe_path(value[2:])
        elif line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
            raise ValueError("Rename/copy patches are unsupported in this release")
        elif line.startswith(("old mode ", "new mode ", "new file mode ", "deleted file mode ")):
            if line.rsplit(" ", 1)[-1] not in ("100644", "100755"):
                raise ValueError("Symlink and submodule modes are unsupported")
        elif line.startswith("index ") and line.rsplit(" ", 1)[-1] in ("120000", "160000"):
            raise ValueError("Symlink and submodule modes are unsupported")
        elif line.startswith(("GIT binary patch", "Binary files ")):
            raise ValueError("Binary patches are unsupported")
    if not found:
        raise ValueError("An ordinary Git text patch is required")


def git(args: list[str], cwd: Path, *, data: bytes | None = None) -> bytes:
    completed = subprocess.run(["git", *args], cwd=cwd, input=data,
                               capture_output=True, timeout=30)
    if completed.returncode:
        raise ValueError(completed.stderr.decode("utf-8", "replace").strip())
    return completed.stdout


def snapshot(repo: Path, revision: str, destination: Path) -> str:
    sha = git(["rev-parse", "--verify", "--end-of-options", revision + "^{commit}"], repo).decode().strip()
    tree = git(["ls-tree", "-r", sha], repo)
    if any(line.startswith(b"160000 ") for line in tree.splitlines()):
        raise ValueError("Submodules are unsupported; supply a self-contained repository")
    data = git(["archive", "--format=tar", sha], repo)
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for item in archive.getmembers():
            safe_path(item.name.rstrip("/"))
            if not (item.isfile() or item.isdir()):
                raise ValueError("Snapshots with symlinks, hardlinks or special files are unsupported")
            output = destination / item.name
            if item.isdir():
                output.mkdir(parents=True, exist_ok=True)
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(item)
                assert source is not None
                output.write_bytes(source.read())
                output.chmod(item.mode & 0o777)
    return sha


def apply_patch(workspace: Path, data: bytes) -> None:
    validate_patch(data)
    git(["apply", "--check", "--whitespace=nowarn", "-"], workspace, data=data)
    git(["apply", "--whitespace=nowarn", "-"], workspace, data=data)
