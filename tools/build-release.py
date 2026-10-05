#!/usr/bin/python3
"""Build a clean repo archive with an external SHA-256 checksum."""
import hashlib
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-B', str(ROOT / 'tools/check.py')], check=True)
version = (ROOT / 'VERSION').read_text().strip()
output = ROOT / 'dist'
output.mkdir(exist_ok=True)
archive = output / ('LaurinOS-' + version + '.zip')
folders = ['src', 'installer', 'config', 'systemd', 'assets', 'data', 'bin', 'sbin', 'tools', 'tests', 'docs', '.github']
files = [p for p in ROOT.iterdir() if p.is_file() and p.name not in {'.DS_Store'}]
for folder in folders:
    files.extend(p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.pyo'})
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as target:
    for path in sorted(files):
        target.write(path, 'LaurinOS/' + str(path.relative_to(ROOT)))
checksum = archive.with_suffix('.zip.sha256')
checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
print(archive)
print(checksum)
