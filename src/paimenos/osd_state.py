"""Gerätewerte und sitzungsweiter OSD-Kanal, ohne Qt-Abhängigkeit."""
import math
import os
from pathlib import Path
import re
import socket
import subprocess

KINDS = ('volume', 'brightness')

def socket_folder():
    # Für Sender und Anzeige gleich, auch ohne exportiertes XDG_RUNTIME_DIR.
    runtime = Path('/run/user') / str(os.getuid())
    base = runtime if runtime.is_dir() else Path.home() / '.cache'
    folder = base / 'paimenos-osd'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder

def notify(kind):
    if kind not in KINDS:
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
            sender.settimeout(0.1)
            sender.sendto(kind.encode('ascii'), str(socket_folder() / 'events.sock'))
    except OSError:
        # Hardware-Tasten funktionieren auch vor dem Start der grafischen Sitzung.
        pass

def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=1.0,
                                env=dict(os.environ, LC_ALL='C'))
        return result.stdout if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''

def percentage(value):
    return max(0, min(100, int(math.floor(float(value) + 0.5))))

def parse_wpctl(text):
    match = re.search(r'Volume:\s*(\d+(?:\.\d+)?)', text)
    if not match:
        return None
    return percentage(float(match.group(1)) * 100), '[MUTED]' in text

def parse_amixer(text):
    levels = re.findall(r'\[(\d+)%\]', text)
    if not levels:
        return None
    switches = re.findall(r'\[(on|off)\]', text)
    return percentage(sum(map(int, levels)) / len(levels)), bool(switches) and all(v == 'off' for v in switches)

def parse_brightness(text):
    for line in text.splitlines():
        fields = line.split(',')
        if len(fields) != 5 or fields[1] != 'backlight':
            continue
        try:
            current, maximum = int(fields[2]), int(fields[4])
            if current >= 0 and maximum > 0:
                return percentage(current * 100 / maximum), False
        except ValueError:
            continue
    return None

def read_level(kind):
    if kind == 'volume':
        result = parse_wpctl(command(['/usr/bin/wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@']))
        if result is not None:
            return result
        for control in ('Master', 'Speaker'):
            result = parse_amixer(command(['/usr/bin/amixer', 'sget', control]))
            if result is not None:
                return result
    elif kind == 'brightness':
        result = parse_brightness(command(['/usr/bin/brightnessctl', '-c', 'backlight', '-m', 'info']))
        if result is not None:
            return result
        for device in sorted(Path('/sys/class/backlight').glob('*')):
            try:
                current = int((device / 'brightness').read_text())
                maximum = int((device / 'max_brightness').read_text())
                if current >= 0 and maximum > 0:
                    return percentage(current * 100 / maximum), False
            except (OSError, ValueError):
                continue
    return None
