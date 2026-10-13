"""Local release gate: fixtures, wheel build, clean install, installed CLI/SDK smoke."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
env = {**os.environ, 'PYTHONPATH': str(root / 'src')}
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=root, env=env, check=True)
subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation', '--no-index', '.', '-w', 'dist'], cwd=root, check=True)
wheel = sorted((root / 'dist').glob('patchproof_local-*.whl'))[-1]
with tempfile.TemporaryDirectory(prefix='patchproof-release-') as temporary:
    folder = Path(temporary)
    clean_env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    subprocess.run([sys.executable, '-m', 'venv', str(folder / 'venv')], cwd=folder, env=clean_env, check=True)
    python = folder / 'venv' / 'bin' / 'python'
    cli = folder / 'venv' / 'bin' / 'patchproof'
    subprocess.run([str(python), '-m', 'pip', 'install', '--no-deps', '--no-index', str(wheel)], cwd=folder, env=clean_env, check=True)
    subprocess.run([str(cli), '--help'], cwd=folder, env=clean_env, check=True)
    subprocess.run([str(python), '-c', 'from patchproof import FailureExpectation, verify_patch; print("Installed SDK import passed")'], cwd=folder, env=clean_env, check=True)
    subprocess.run([sys.executable, str(root / 'examples/demo.py'), '--output', str(folder / 'evidence')], cwd=folder, env=env, check=True)
    subprocess.run([str(cli), 'report', str(folder / 'evidence')], cwd=folder, env=clean_env, check=True, stdout=subprocess.DEVNULL)
print('Release gate passed; publication is a separate deliberate action.')
