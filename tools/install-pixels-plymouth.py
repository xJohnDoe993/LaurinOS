"""Originales Pixels-Theme aus adi1090x/plymouth-themes, Release v1.0."""
from pathlib import Path, PurePosixPath
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

URL = 'https://github.com/adi1090x/plymouth-themes/releases/download/v1.0/pixels.tar.gz'
SHA256 = '71bea87af93990f343ed4a9cb6b363f29d748bd4df864c8c9472589181794a1c'
EXPECTED = {'pixels.script', 'pixels.plymouth', 'LICENSE'} | {'progress-' + str(i) + '.png' for i in range(240)}


def valid_archive(path):
    return path.is_file() and path.stat().st_size <= 32 * 1024 * 1024 and hashlib.sha256(path.read_bytes()).hexdigest() == SHA256


def install(root=Path('/')):
    cache = root / 'usr/local/share/paimenos/cache/plymouth/pixels-v1.0.tar.gz'
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not valid_archive(cache):
        fd, temporary = tempfile.mkstemp(prefix='.pixels-', dir=cache.parent)
        os.close(fd)
        try:
            subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                '--connect-timeout', '15', '--max-time', '120', '--retry', '2',
                '--max-filesize', str(32 * 1024 * 1024), '-o', temporary, URL], check=True)
            if not valid_archive(Path(temporary)):
                raise ValueError('Prüfsumme des Pixels-Downloads stimmt nicht. Vorhandenes Theme bleibt erhalten.')
            os.replace(temporary, cache)
            cache.chmod(0o644)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    themes = root / 'usr/share/plymouth/themes'
    themes.mkdir(parents=True, exist_ok=True)
    destination = themes / 'pixels'
    stage = Path(tempfile.mkdtemp(prefix='.pixels-stage-', dir=themes))
    try:
        found = set()
        with tarfile.open(cache, 'r:gz') as archive:
            for member in archive.getmembers():
                name = PurePosixPath(member.name)
                if member.isdir() and member.name.rstrip('/') == 'pixels':
                    continue
                if not member.isfile() or len(name.parts) != 2 or name.parts[0] != 'pixels' or name.name not in EXPECTED:
                    raise ValueError('Unerwartete Datei im Pixels-Archiv.')
                if name.name in found or not 0 < member.size <= 1024 * 1024:
                    raise ValueError('Ungültige Theme-Datei: ' + name.name)
                data = archive.extractfile(member).read()
                if name.name.endswith('.png') and not data.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('Ungültiges Animationsbild: ' + name.name)
                (stage / name.name).write_bytes(data)
                (stage / name.name).chmod(0o644)
                found.add(name.name)
        if found != EXPECTED:
            raise ValueError('Pixels-Archiv ist unvollständig.')
        descriptor = (stage / 'pixels.plymouth').read_text()
        if 'ModuleName=script' not in descriptor or 'ScriptFile=/usr/share/plymouth/themes/pixels/pixels.script' not in descriptor:
            raise ValueError('Ungültige Plymouth-Theme-Beschreibung.')
        (stage / 'SOURCE.txt').write_text('Pixels aus Pack 3 · Aditya Shakya (@adi1090x)\n'
            'https://github.com/adi1090x/plymouth-themes\nRelease v1.0 · SHA256: ' + SHA256 + '\n')
        stage.chmod(0o755)
        backup = themes / '.pixels-paimenos-backup'
        if backup.exists():
            raise ValueError('Ein Theme-Backup liegt noch vor. Bitte vorige Installation prüfen: ' + str(backup))
        if destination.is_symlink():
            raise ValueError('Theme-Verzeichnis ist ein symbolischer Link: ' + str(destination))
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(stage, destination)
        except Exception:
            if backup.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print('  ✓ Pixels (Pack 3): 240 Animationsbilder und Original-Lizenz installiert.')


def configure_grub(path):
    if not path.is_file():
        return
    original = path.read_text()
    pattern = r'^(\s*GRUB_CMDLINE_LINUX_DEFAULT=)(["\'])(.*?)\2([ \t]*(?:#.*)?)$'
    match = re.search(pattern, original, re.M)
    if not match:
        if re.search(r'^\s*GRUB_CMDLINE_LINUX_DEFAULT=', original, re.M):
            raise ValueError('GRUB_CMDLINE_LINUX_DEFAULT bitte in Anführungszeichen setzen.')
        prefix, quote, value, suffix = 'GRUB_CMDLINE_LINUX_DEFAULT=', '"', '', ''
    else:
        prefix, quote, value, suffix = match.groups()
    # Nur einfache Splash-Optionen deduplizieren; alle anderen Kernel-Optionen bewahren.
    for option in ('quiet', 'splash'):
        occurrences = list(re.finditer(r'(?<!\S)' + option + r'(?!\S)', value))
        for occurrence in reversed(occurrences[1:]):
            value = value[:occurrence.start()] + value[occurrence.end():]
        if not occurrences:
            value = value.rstrip() + ' ' + option
    for option in ('loglevel=3', 'vt.global_cursor_default=0'):
        if not re.search(r'(?<!\S)' + re.escape(option.split('=')[0]) + '=', value):
            value = value.rstrip() + ' ' + option
    value = value.strip()
    replacement = prefix + quote + value + quote + suffix
    if match:
        changed = original[:match.start()] + replacement + original[match.end():]
    else:
        changed = original.rstrip('\n') + '\n' + replacement + '\n'
    if changed != original:
        backup = path.with_name(path.name + '.before-paimenos-pixels')
        if not backup.exists():
            shutil.copy2(path, backup)
        fd, temporary = tempfile.mkstemp(prefix='.grub-paimenos-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as handle:
                handle.write(changed)
            shutil.copymode(path, temporary)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


if __name__ == '__main__':
    try:
        if len(sys.argv) == 2 and sys.argv[1] == '--grub':
            configure_grub(Path('/etc/default/grub'))
        else:
            install()
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as exc:
        sys.exit('FEHLER bei Pixels/Plymouth: ' + str(exc))

