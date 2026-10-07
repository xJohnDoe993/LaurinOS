#!/usr/bin/python3
"""Install the bundled PaimenOS Plymouth theme. No downloads or image libraries."""
import argparse
import contextlib
import fcntl
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
THEME = 'paimenos'
EXPECTED = {'paimenos.script', 'paimenos.plymouth', 'logo.png', 'entry.png'} | {
    'spin-' + str(i) + '.png' for i in range(48)
}


def verify_png(data):
    """Check PNG structure and chunk CRCs, including a complete IEND."""
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Ungültiges PNG.')
    offset, first, image_data = 8, True, False
    while offset + 12 <= len(data):
        size, kind = struct.unpack('>I4s', data[offset:offset + 8])
        end = offset + 12 + size
        if end > len(data):
            raise ValueError('Abgeschnittenes PNG.')
        body = data[offset + 8:offset + 8 + size]
        crc = struct.unpack('>I', data[offset + 8 + size:end])[0]
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ValueError('PNG-Prüfsumme stimmt nicht.')
        if first:
            if kind != b'IHDR' or size != 13:
                raise ValueError('PNG-Kopf fehlt.')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            if not (0 < width <= 2048 and 0 < height <= 2048 and depth == 8
                    and color == 6 and compression == 0 and filtering == 0 and interlace == 0):
                raise ValueError('Nicht unterstütztes Theme-PNG.')
            first = False
        if kind == b'IDAT' and size:
            image_data = True
        if kind == b'IEND':
            if size != 0 or not image_data or end != len(data):
                raise ValueError('Ungültiges PNG-Ende.')
            return width, height
        offset = end
    raise ValueError('PNG-Ende fehlt.')


def validate_assets(source=None):
    source = Path(source) if source is not None else ROOT / 'assets/plymouth/paimenos'
    if not source.is_dir() or source.is_symlink():
        raise ValueError('PaimenOS-Theme fehlt: ' + str(source))
    if {p.name for p in source.iterdir()} != EXPECTED | {'SHA256SUMS'}:
        raise ValueError('PaimenOS-Theme ist unvollständig oder enthält unerwartete Dateien.')
    checksums = source / 'SHA256SUMS'
    if checksums.is_symlink() or not checksums.is_file():
        raise ValueError('Ungültige Theme-Prüfsummenliste.')
    hashes = {}
    for line in checksums.read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  ([a-z0-9_.-]+)', line)
        if not match or match[2] not in EXPECTED or match[2] in hashes:
            raise ValueError('Ungültiger Eintrag in den Theme-Prüfsummen.')
        hashes[match[2]] = match[1]
    if set(hashes) != EXPECTED:
        raise ValueError('Theme-Prüfsummen sind unvollständig.')
    contents = {}
    for name in sorted(EXPECTED):
        path = source / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
            raise ValueError('Ungültige Theme-Datei: ' + name)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != hashes[name]:
            raise ValueError('Theme-Prüfsumme stimmt nicht: ' + name)
        if name.endswith('.png'):
            verify_png(data)
        contents[name] = data
    descriptor = contents['paimenos.plymouth'].decode('utf-8')
    if any(line not in descriptor.splitlines() for line in (
            'ModuleName=script', 'ImageDir=/usr/share/plymouth/themes/paimenos',
            'ScriptFile=/usr/share/plymouth/themes/paimenos/paimenos.script')):
        raise ValueError('Ungültige PaimenOS-Theme-Beschreibung.')
    contents['SHA256SUMS'] = checksums.read_bytes()
    return contents


def install(root=Path('/'), source=None):
    # Validate every source file before changing the installed theme.
    contents = validate_assets(source)
    themes = root / 'usr/share/plymouth/themes'
    destination = themes / THEME
    backup = themes / '.paimenos-backup'
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError('Ungültiges Theme-Verzeichnis: ' + str(destination))
    if backup.exists() or backup.is_symlink():
        raise ValueError('Ein Theme-Backup liegt noch vor. Vorige Installation prüfen: ' + str(backup))
    themes.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.paimenos-stage-', dir=themes))
    try:
        for name, data in contents.items():
            (stage / name).write_bytes(data)
            (stage / name).chmod(0o644)
        stage.chmod(0o755)
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(stage, destination)
        except BaseException:
            if backup.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print('  ✓ PaimenOS: Logo und 48 kleine Animationsbilder offline installiert.')
    return destination

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
        backup = path.with_name(path.name + '.before-paimenos')
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


def activate(root=Path('/'), source=None, run=subprocess.run):
    """Explicit system migration; ordinary application updates only stage the files."""
    previous = run(['plymouth-set-default-theme'], check=True, capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', previous):
        raise ValueError('Das bisherige Plymouth-Theme konnte nicht ermittelt werden.')
    grub = root / 'etc/default/grub'
    original_grub = grub.read_bytes() if grub.is_file() else None
    install(root, source)
    selected = False
    try:
        # Set the flag before the command so a partially failed selection also rolls back.
        selected = True
        run(['plymouth-set-default-theme', THEME], check=True)
        actual = run(['plymouth-set-default-theme'], check=True, capture_output=True, text=True).stdout.strip()
        if actual != THEME:
            raise ValueError('PaimenOS wurde nicht als Plymouth-Theme aktiviert.')
        if original_grub is not None:
            configure_grub(grub)
            run(['update-grub'], check=True)
        run(['update-initramfs', '-u', '-k', 'all'], check=True)
    except BaseException:
        if selected:
            try:
                run(['plymouth-set-default-theme', previous], check=True)
                if original_grub is not None:
                    fd, temporary = tempfile.mkstemp(prefix='.grub-paimenos-restore-', dir=grub.parent)
                    try:
                        with os.fdopen(fd, 'wb') as handle:
                            handle.write(original_grub)
                        shutil.copymode(grub, temporary)
                        os.replace(temporary, grub)
                    finally:
                        if os.path.exists(temporary):
                            os.unlink(temporary)
                    run(['update-grub'], check=True)
                run(['update-initramfs', '-u', '-k', 'all'], check=True)
            except (OSError, subprocess.CalledProcessError) as rollback_error:
                print('Hinweis: Wiederherstellung der Startkonfiguration unvollständig: '
                      + str(rollback_error), file=sys.stderr)
        raise
    print('  ✓ PaimenOS ist für den nächsten Systemstart aktiviert. Kein automatischer Neustart.')


def main():
    parser = argparse.ArgumentParser(description='Mitgeliefertes PaimenOS-Plymouth-Theme installieren.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Theme-Dateien offline prüfen; keine Systemänderung')
    mode.add_argument('--grub', action='store_true', help='Nur GRUB-Splash-Parameter ergänzen')
    mode.add_argument('--activate', action='store_true',
                      help='Theme installieren, aktivieren und Startabbilder neu bauen')
    args = parser.parse_args()
    if args.check:
        validate_assets()
        print('PaimenOS-Theme vollständig; Prüfsummen und PNG-Dateien gültig.')
        return
    if os.geteuid() != 0:
        parser.error('Bitte mit sudo ausführen.')
    if args.activate:
        # Coordinate with application maintenance and package installations.
        with contextlib.ExitStack() as locks:
            for name in ('paimenos-maintenance.lock', 'paimenos-emulator-install.lock'):
                lock = locks.enter_context(open('/run/' + name, 'a'))
                os.fchmod(lock.fileno(), 0o600)
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('PaimenOS-Wartung oder Paketinstallation läuft bereits.')
            activate()
    elif args.grub:
        configure_grub(Path('/etc/default/grub'))
    else:
        install()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit('FEHLER bei PaimenOS/Plymouth: ' + str(exc))
