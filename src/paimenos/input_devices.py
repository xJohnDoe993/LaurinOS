"""Gamepad-Kandidaten ohne Öffnen von Tastatur-/Maus-Ereignisgeräten auswählen."""
import os
import struct
from pathlib import Path


def possible_gamepad(path):
    caps = Path('/sys/class/input') / os.path.basename(path) / 'device/capabilities/key'
    try:
        words = caps.read_text().split()
        width = struct.calcsize('@L') * 8
        keys = sum(int(word, 16) << (index*width)
                   for index, word in enumerate(reversed(words)))
    except (OSError, ValueError):
        # Falls sysfs noch nicht bereit ist: im Eingabethread per evdev prüfen.
        return True
    return any(keys & (1 << code) for code in range(256, 272)) or any(
        keys & (1 << code) for code in range(288, 320))

