"""Build fresh distributions and verify the installed SDK, CLI, fixtures, and demo.

Requires build, setuptools>=77, twine, and requirements-test.lock in the invoking
environment. This script never uploads artifacts or reads registry credentials.
"""
from pathlib import Path, PurePosixPath
import argparse
import email
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def run(command, *, cwd, env, quiet=False):
    subprocess.run(command, cwd=cwd, env=env, check=True,
                   stdout=subprocess.DEVNULL if quiet else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--installer', choices=('pip', 'uv'), default='pip')
    parser.add_argument('--wheelhouse', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / 'pyproject.toml').read_text())['project']
    distribution, version = project['name'], project['version']
    normalized = re.sub(r'[-_.]+', '_', distribution)
    output = (args.output_dir or root / 'dist').resolve()
    clean_env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    source_env = {**clean_env, 'PYTHONPATH': str(root / 'src')}
    run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=root, env=source_env)

    with tempfile.TemporaryDirectory(prefix='patchproof-release-') as temporary:
        folder = Path(temporary)
        source, artifacts = folder / 'source', folder / 'dist'
        shutil.copytree(root, source, ignore=shutil.ignore_patterns(
            '.git', '.venv', 'build', 'dist', '__pycache__', '*.egg-info', '*.pyc',
            '.pytest_cache', '.DS_Store', '.env', '.env.*', 'evidence', 'runs'))
        # The default build command builds the sdist, then the wheel FROM that sdist.
        run([sys.executable, '-m', 'build', '--no-isolation', '--outdir', str(artifacts)],
            cwd=source, env=clean_env)
        wheels, sdists = list(artifacts.glob('*.whl')), list(artifacts.glob('*.tar.gz'))
        if len(wheels) != 1 or len(sdists) != 1:
            raise RuntimeError('Expected exactly one fresh wheel and one source distribution')
        wheel, sdist = wheels[0], sdists[0]
        if wheel.name != f'{normalized}-{version}-py3-none-any.whl':
            raise RuntimeError('Built wheel does not match current project metadata')
        with zipfile.ZipFile(wheel) as archive:
            members = archive.namelist()
            metadata = email.message_from_bytes(archive.read(next(n for n in members if n.endswith('/METADATA'))))
            if metadata['Name'] != distribution or metadata['Version'] != version or metadata['License-Expression'] != 'MIT':
                raise RuntimeError('Unexpected wheel identity or license metadata')
            if not any(n.endswith('/licenses/LICENSE') for n in members):
                raise RuntimeError('Wheel is missing its PEP 639 license file')
            if any(not (n.startswith('patchproof/') or n.startswith(f'{normalized}-{version}.dist-info/')) for n in members):
                raise RuntimeError('Wheel contains unexpected files')

        extracted = folder / 'sdist'
        with tarfile.open(sdist) as archive:
            members = archive.getmembers()
            for member in members:
                name = PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts or not (member.isdir() or member.isfile()):
                    raise RuntimeError('Unsafe source distribution member')
                if any(part in {'.git', '.venv', '__pycache__', 'dist', 'build', 'evidence', 'runs'} for part in name.parts):
                    raise RuntimeError('Runtime or build data included in source distribution')
                target = extracted.joinpath(*name.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise RuntimeError('Missing source distribution file')
                    target.write_bytes(stream.read())
        roots = list(extracted.iterdir())
        if len(roots) != 1:
            raise RuntimeError('Expected a single source distribution root')
        extracted_source = roots[0]
        for required in ('LICENSE', 'README_PYPI.md', 'requirements-test.lock', 'scripts/check_release.py',
                         'examples/demo.py', 'tests/test_patchproof.py', 'tests/test_v2.py', 'docs/usage.md'):
            if not (extracted_source / required).is_file():
                raise RuntimeError(f'Source distribution is missing {required}')
        run([sys.executable, '-m', 'twine', 'check', '--strict', str(wheel), str(sdist)], cwd=folder, env=clean_env)

        run([sys.executable, '-m', 'venv', str(folder / 'venv')], cwd=folder, env=clean_env)
        python, cli = folder / 'venv/bin/python', folder / 'venv/bin/patchproof'
        if args.installer == 'uv':
            executable = shutil.which('uv')
            if not executable:
                raise RuntimeError('uv installer selected but executable is unavailable')
            install = [executable, '--system-certs', 'pip', 'install', '--python', str(python)]
        else:
            install = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check']
        if args.wheelhouse:
            install += ['--no-index', '--find-links', str(args.wheelhouse.resolve())]
        install += ['-c', str(extracted_source / 'requirements-test.lock'), str(wheel) + '[runner]']
        run(install, cwd=folder, env=clean_env)
        run([str(python), '-c',
             'from pathlib import Path; import sys, patchproof; from patchproof import FailureExpectation, verify_patch; '
             'assert Path(patchproof.__file__).is_relative_to(Path(sys.prefix)); '
             'print("Installed SDK import verified inside fresh virtual environment")'], cwd=folder, env=clean_env)
        run([str(cli), '--help'], cwd=folder, env=clean_env, quiet=True)
        run([str(python), '-m', 'unittest', 'discover', '-s', str(extracted_source / 'tests'), '-v'], cwd=folder, env=clean_env)
        run([str(python), str(extracted_source / 'examples/demo.py'), '--output', str(folder / 'evidence')], cwd=folder, env=clean_env)
        run([str(cli), 'report', str(folder / 'evidence')], cwd=folder, env=clean_env, quiet=True)
        output.mkdir(parents=True, exist_ok=True)
        summary = {'distribution': distribution, 'version': version, 'checks': 'passed', 'artifacts': []}
        for artifact in (wheel, sdist):
            destination = output / artifact.name
            shutil.copy2(artifact, destination)
            summary['artifacts'].append({'file': str(destination), 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()})
        print(json.dumps(summary, indent=2))
    print('Release checks passed. No artifacts were uploaded.')


if __name__ == '__main__':
    main()
