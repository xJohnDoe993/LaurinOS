from paimenos.i18n import t
import glob
import hashlib
import json
from datetime import datetime
import os
import re
import secrets
import shlex
import subprocess
import shutil
import tempfile
import zipfile
from pathlib import Path
import paimenos.parent as parents
import paimenos.controller_profiles as controllers

ROOT = Path.home() / '.local/share/paimenos/emulators'
LIMIT = 1024 * 1024 * 1024
import sys
import paimenos.emulator_catalog as catalog
SYSTEMS = {key: (item['name'], item['core'], set(item['extensions'])) for key, item in catalog.CATALOG.items()}

BIOS = {'scph5500.bin': 524288, 'scph5501.bin': 524288, 'scph5502.bin': 524288, 'gba_bios.bin': 16384}


PS1_BIOS_MD5 = {
    'scph5500.bin': '8dd7d5296a650fac7319bce665a6a53c',
    'scph5501.bin': '490f666e1afb15b7362b406ed1cea246',
    'scph5502.bin': '32736f17079d0b2b7024407c39bd3050',
}
PS1_REGIONS = {'jp': ('Japan', 'scph5500.bin'), 'us': ('USA', 'scph5501.bin'), 'eu': (t('Europa'), 'scph5502.bin')}

def bios_inventory():
    result = []
    for name, expected in PS1_BIOS_MD5.items():
        path = ROOT / 'bios' / name
        item = {'name': name, 'valid': False, 'status': 'Fehlt', 'md5': ''}
        if path.is_file():
            try:
                if path.stat().st_size != BIOS[name]:
                    item['status'] = t('Falsche Dateigröße')
                else:
                    digest = hashlib.md5(path.read_bytes()).hexdigest()
                    item['md5'] = digest
                    item['valid'] = digest == expected
                    item['status'] = t('Geprüft – korrekt') if item['valid'] else t('Inhalt passt nicht zu diesem BIOS-Dateinamen')
            except OSError:
                item['status'] = t('Nicht lesbar')
        result.append(item)
    return result

def cue_tracks(game):
    text = game.read_text(encoding='utf-8-sig')
    names = re.findall(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+BINARY\s*$', text, re.I | re.M)
    tracks = []
    for quoted, plain in names:
        name = quoted or plain
        path = (game.parent / name).resolve()
        if '/' in name or '\\' in name or not path.is_relative_to(game.parent.resolve()) or not path.is_file():
            raise ValueError(t('BIN-Track fehlt oder hat einen ungültigen Pfad: ') + name)
        if path.stat().st_size == 0:
            raise ValueError(t('BIN-Track ist leer: ') + name)
        tracks.append(path)
    if not tracks:
        raise ValueError(t('Die CUE enthält keine lesbaren BIN-Tracks.'))
    return tracks

def ps1_region(game):
    # Nur eine klare Lizenzmarkierung im Daten-Track verwenden; Dateinamen reichen nicht.
    if game.suffix.lower() != '.cue':
        return None
    for track in cue_tracks(game):
        with track.open('rb') as handle:
            header = handle.read(128 * 1024)
        header = re.sub(rb'\s+', b' ', header).lower()
        if b'sony computer entertainment europe' in header:
            return 'eu'
        if b'sony computer entertainment america' in header:
            return 'us'
        if b'sony computer entertainment inc.' in header:
            return 'jp'
    return None

def ps1_preflight(game):
    if game.suffix.lower() == '.cue':
        cue_tracks(game)
    region = ps1_region(game)
    inventory = bios_inventory()
    if region:
        label, required = PS1_REGIONS[region]
        if not next(b for b in inventory if b['name'] == required)['valid']:
            raise ValueError(t('PS1-Spielregion ') + label + ': ' + required + t(' fehlt oder ist ungültig. Bitte unter Eltern → Emulatoren die BIOS-Prüfung ansehen.'))
    elif not any(b['valid'] for b in inventory):
        raise ValueError(t('Kein geprüftes PS1-BIOS vorhanden. Bitte unter Eltern → Emulatoren ein korrektes scph5500/5501/5502.bin hochladen.'))
    return region, inventory


def controller_report():
    profile_root = Path('/usr/local/share/paimenos/retroarch-autoconfig')
    profiles = sorted((profile_root / 'udev').glob('*.cfg'))
    lines = [t('Eigene Controller-Profile: ') + str(len(controllers.read_profiles())), t('RetroArch-Joypad-Treiber: udev'), t('Linux-Controller-Profile: ') + str(len(profiles)),
             t('SN30-Profile: ') + ', '.join(p.name for p in profiles if 'sn30' in p.name.lower())]
    try:
        import evdev
    except ImportError:
        return '\n'.join(lines + [t('Controller-Diagnose: python3-evdev fehlt.')])
    found = 0
    for path in sorted(glob.glob('/dev/input/event*')):
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue
        try:
            keys = set(device.capabilities(absinfo=False).get(evdev.ecodes.EV_KEY, []))
            if '8bitdo' not in device.name.lower() and not keys.intersection(range(288, 320)):
                continue
            found += 1
            lines.append(device.name + ' · ' + path + ' · VID:PID ' +
                         f'{device.info.vendor:04x}:{device.info.product:04x}' + ' · lesbar')
            try:
                props = subprocess.run(['/usr/bin/udevadm', 'info', '--query=property', '--name=' + path],
                                       capture_output=True, text=True, timeout=2)
                prop = next((line for line in props.stdout.splitlines() if line.startswith('ID_INPUT_JOYSTICK=')), t('ID_INPUT_JOYSTICK fehlt'))
                lines.append('  ' + prop)
            except (OSError, subprocess.TimeoutExpired):
                lines.append(t('  udev-Merkmale konnten nicht gelesen werden.'))
        except OSError as exc:
            lines.append(t('Controller wurde während der Diagnose getrennt: ') + str(exc))
        finally:
            device.close()
        if found >= 8:
            break
    if not found:
        lines.append(t('Kein lesbares Gamepad erkannt. Controller verbinden und Sitzung nach Gruppenänderungen neu starten.'))
    return '\n'.join(lines)

def emulator_log():
    parts = [t('PaimenOS Emulator-Diagnose'), t('Zeit: ') + datetime.now().isoformat(timespec='seconds')]
    for system, values in SYSTEMS.items():
        parts.append(values[0] + ': ' + str(core_path(system) or t('Core fehlt')))
    parts += ['\nController:', controller_report(), '\nPS1-BIOS:']
    for bios in bios_inventory():
        parts.append(bios['name'] + ': ' + bios['status'] + (' · MD5 ' + bios['md5'] if bios['md5'] else ''))
    for title, path in [(t('Letzter Emulatorstart'), ROOT / 'last-launch.txt'),
                        (t('Ausführliches Startprotokoll'), ROOT / 'retroarch-last.log'),
                        (t('Anwendungsprotokoll'), Path.home() / '.local/state/paimenos/paimenos-application.log')]:
        parts.append('\n' + title + ':')
        try:
            with path.open('rb') as handle:
                handle.seek(max(0, path.stat().st_size - 64 * 1024))
                parts.append(handle.read(64 * 1024).decode('utf-8', errors='replace'))
        except OSError:
            parts.append(t('Noch kein Protokoll vorhanden.'))
    return '\n'.join(parts)

def core_path(system):
    return catalog.core_path(system)

def status():
    return catalog.status()

def ready(system):
    return bool(shutil.which('retroarch') and core_path(system) and (system != 'psp' or catalog.psp_assets_ready()))


def copy_bounded(source, target, limit):
    total = 0
    with open(target, 'xb') as out:
        while True:
            block = source.read(min(1024 * 1024, limit - total + 1))
            if not block:
                break
            total += len(block)
            if total > limit:
                raise ValueError(t('Datei oder entpacktes Spiel überschreitet das Größenlimit.'))
            out.write(block)
    if not total:
        raise ValueError(t('Die Datei ist leer.'))
    return total

def upload_bios(upload):
    name = (upload.filename or '').lower()
    if name not in BIOS:
        raise ValueError(t('BIOS-Dateiname muss scph5500.bin, scph5501.bin, scph5502.bin oder gba_bios.bin sein.'))
    folder = ROOT / 'bios'
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder) as temp:
        target = Path(temp) / name
        count = copy_bounded(upload.stream, target, BIOS[name])
        if count != BIOS[name]:
            raise ValueError(t('Die BIOS-Datei hat eine unerwartete Größe.'))
        if name in PS1_BIOS_MD5:
            digest = hashlib.md5(target.read_bytes()).hexdigest()
            if digest != PS1_BIOS_MD5[name]:
                actual = next((n for n, expected in PS1_BIOS_MD5.items() if expected == digest), None)
                if actual:
                    raise ValueError(t('Die Datei gehört zu ') + actual + t('. Bitte mit diesem Namen hochladen.'))
                raise ValueError(t('Die BIOS-Prüfsumme passt nicht zu ') + name + t('. Eine andere oder beschädigte Datei wurde gewählt.'))
        os.replace(target, folder / name)

def validate_game(folder, system):
    files = [p for p in folder.iterdir() if p.suffix.lower() != '.sbi']
    entries = [p for p in files if p.suffix.lower() in SYSTEMS[system][2]]
    if len(entries) != 1:
        raise ValueError(t('Bitte genau ein Spiel hochladen. PS1: eine CUE mit allen BIN-Tracks oder eine CHD/PBP-Datei.'))
    entry = entries[0]
    if entry.suffix.lower() == '.cue':
        if entry.stat().st_size > 128 * 1024:
            raise ValueError(t('CUE-Datei ist zu groß.'))
        text = entry.read_text(encoding='utf-8-sig')
        refs = re.findall(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+BINARY\s*$', text, re.I | re.M)
        if not refs or len(refs) != len(re.findall(r'^\s*FILE\b', text, re.I | re.M)):
            raise ValueError(t('CUE muss gültige FILE-Einträge mit BINARY-Tracks enthalten.'))
        for quoted, plain in refs:
            name = quoted or plain
            if '/' in name or '\\' in name or name in ('.', '..') or not (folder / name).is_file() or Path(name).suffix.lower() != '.bin':
                raise ValueError(t('Eine in der CUE genannte BIN-Datei fehlt oder der Pfad ist ungültig: ') + name)
    elif len(files) != 1:
        raise ValueError(t('Dieses Format benötigt nur eine ROM-Datei.'))
    return entry.name

def upload_game(system, title, uploads):
    if system not in SYSTEMS:
        raise ValueError(t('Bitte eine gültige Konsole auswählen.'))
    if not ready(system):
        raise ValueError(t('Dieser Emulator ist noch nicht bereit. Bitte oben im Elternbackend installieren.'))
    limit = 2 * LIMIT if system == 'psp' else LIMIT
    title = title.strip()
    if not title or len(title) > 80 or any(ord(c) < 32 for c in title):
        raise ValueError(t('Bitte einen Spielnamen mit höchstens 80 Zeichen eingeben.'))
    uploads = [u for u in uploads if u.filename]
    if not uploads or len(uploads) > 100:
        raise ValueError(t('Bitte ein Spiel mit höchstens 100 Dateien auswählen.'))
    games = ROOT / 'roms'
    games.mkdir(parents=True, exist_ok=True)
    app_id = 'rom-' + secrets.token_hex(12)
    final = games / app_id
    with tempfile.TemporaryDirectory(dir=games) as temp:
        folder = Path(temp) / 'game'
        folder.mkdir()
        total = 0
        allowed = SYSTEMS[system][2] | ({'.bin', '.sbi'} if system == 'ps1' else set())
        def safe_name(name):
            if not name or '/' in name or '\\' in name or name.startswith('.') or any(ord(c) < 32 for c in name) or Path(name).suffix.lower() not in allowed:
                raise ValueError(t('Ungültiger Dateiname oder nicht unterstütztes Format: ') + name)
            if (folder / name).exists() or name.casefold() in {p.name.casefold() for p in folder.iterdir()}:
                raise ValueError(t('Doppelter Dateiname: ') + name)
            return name
        if len(uploads) == 1 and uploads[0].filename.lower().endswith('.zip'):
            archive = Path(temp) / 'upload.zip'
            copy_bounded(uploads[0].stream, archive, limit)
            try:
                with zipfile.ZipFile(archive) as z:
                    members = z.infolist()
                    if not members or len(members) > 100 or sum(m.file_size for m in members) > limit:
                        raise ValueError(t('ZIP ist leer oder zu groß.'))
                    for member in members:
                        name = safe_name(member.filename)
                        if member.is_dir() or (member.external_attr >> 16) & 0o170000 == 0o120000:
                            raise ValueError(t('ZIP darf nur Dateien direkt im Hauptverzeichnis enthalten.'))
                        with z.open(member) as stream:
                            total += copy_bounded(stream, folder / name, limit - total)
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
                raise ValueError(t('ZIP-Datei ist beschädigt, verschlüsselt oder nicht unterstützt.')) from None
        else:
            for upload in uploads:
                name = safe_name(upload.filename)
                total += copy_bounded(upload.stream, folder / name, limit - total)
        entry = validate_game(folder, system)
        os.rename(folder, final)
        try:
            item = {'id': app_id, 'title': title, 'type': 'native', 'custom': True, 'enabled': True,
                    'emulator': system, 'rom_entry': entry,
                    'command': shlex.join(['/usr/local/bin/paimenos-emulator', system, str(final / entry)])}
            with parents.app_transaction():
                items = parents.read_apps()
                items.append(item)
                parents.atomic_json(parents.APPS_FILE, items)
        except Exception:
            shutil.rmtree(final)
            raise
    return app_id

def launch(system, filename):
    if system not in SYSTEMS:
        raise ValueError(t('Unbekannter Emulator.'))
    game = Path(filename).resolve()
    if not game.is_file() or not game.is_relative_to((ROOT / 'roms').resolve()):
        raise ValueError(t('Spiel wurde nicht gefunden.'))
    core = core_path(system)
    if not core or not ready(system):
        raise ValueError(t('Emulator oder benötigte Zusatzdateien fehlen. Bitte im Elternbackend installieren.'))
    region = None
    if system == 'ps1':
        region, inventory = ps1_preflight(game)
    for name in ('bios', 'saves', 'states'):
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    autoconfig = controllers.effective_autoconfig()
    cfg = ROOT / ('retroarch-paimenos-' + system + '.cfg')
    content = '\n'.join([
        'video_fullscreen = "true"', 'config_save_on_exit = "false"',
        'savestate_auto_save = "true"',
        'savestate_auto_index = "true"', 'savestate_max_keep = "0"',
        'autosave_interval = "10"',
        'stdin_cmd_enable = "true"', 'network_cmd_enable = "false"',
        'savestate_auto_load = "' + ('false' if system == 'ps1' else 'true') + '"',
        'joypad_autoconfig_dir = ' + controllers.quote(autoconfig),
        'input_driver = "udev"', 'input_joypad_driver = "udev"',
        'input_player1_joypad_index = "0"', 'input_libretro_device_p1 = "1"',
        'input_autodetect_enable = "true"', 'input_exit_emulator = "escape"',
        'input_menu_toggle = "f8"', 'input_save_state = "f9"', 'input_load_state = "f10"',
        'savefile_directory = "' + str(ROOT / 'saves') + '"',
        'savestate_directory = "' + str(ROOT / 'states') + '"',
        'system_directory = "' + str(catalog.SHARED_SYSTEM if system == 'psp' else ROOT / 'bios') + '"',
        'sort_savefiles_by_content_enable = "true"', 'sort_savestates_by_content_enable = "true"',
        'input_player1_a = "x"', 'input_player1_b = "z"', 'input_player1_x = "s"',
        'input_player1_y = "a"', 'input_player1_l = "q"', 'input_player1_r = "w"',
        'input_player1_start = "enter"', 'input_player1_select = "rshift"']) + '\n'
    if system == 'ps1':
        options = ROOT / 'ps1-paimenos-options.cfg'
        options.write_text('beetle_psx_internal_resolution = "1x(native)"\n'
                           'beetle_psx_skip_bios = "disabled"\n'
                           'beetle_psx_pgxp_mode = "disabled"\n'
                           'beetle_psx_cd_fastload = "2x(native)"\n'
                           'mednafen_psx_internal_resolution = "1x(native)"\n'
                           'mednafen_psx_skip_bios = "disabled"\n')
        content += 'video_driver = "gl"\nvideo_shader_enable = "false"\n'
        content += 'core_options_path = "' + str(options) + '"\n'
        content += 'auto_overrides_enable = "false"\nauto_remaps_enable = "false"\n'
    if system in ('n64', 'psp'):
        options = ROOT / (system + '-paimenos-options.cfg')
        if system == 'n64':
            # Beide Schlüsselpräfixe decken ältere und aktuelle Core-Versionen ab.
            values = {prefix + key: value for prefix in ('mupen64plus', 'mupen64plus-next')
                      for key, value in [('-rdp-plugin', 'gliden64'), ('-rsp-plugin', 'hle'),
                                         ('-43screensize', '320x240'), ('-169screensize', '640x360'), ('-MultiSampling', '0')]}
        else:
            values = {'ppsspp_cpu_core': 'jit', 'ppsspp_internal_resolution': '480x272',
                      'ppsspp_rendering_mode': 'OpenGL', 'ppsspp_texture_scaling_level': '1',
                      'ppsspp_texture_anisotropic_filtering': 'off', 'ppsspp_frameskip': '0'}
        options.write_text(''.join(key + ' = "' + value + '"\n' for key, value in values.items()))
        content += 'video_driver = "gl"\nvideo_shader_enable = "false"\n'
        content += 'core_options_path = "' + str(options) + '"\n'
        content += 'auto_overrides_enable = "false"\n'
    cfg.write_text(content)
    (ROOT / 'last-launch.txt').write_text(t('Zeit: ') + datetime.now().isoformat(timespec='seconds') +
        '\nSystem: ' + system + t('\nSpiel: ') + str(game) + '\nCore: ' + core +
        '\nRegion: ' + (PS1_REGIONS[region][0] if region else t('Nicht vorab erkannt')) +
        t('\nKonfiguration: ') + str(cfg) + '\n')
    log = ROOT / 'retroarch-last.log'
    log.write_text('')
    from paimenos.emulator_session import run_session
    return run_session(['/usr/bin/retroarch', '--verbose', '--log-file', str(log),
                                 '-f', '-c', str(cfg), '-L', core, str(game)])
