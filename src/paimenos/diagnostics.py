"""Begrenzte Geräte-Diagnose; keine PINs, Cookies oder Profilinhalte."""
from paimenos.paths import STATE_DIR
import fcntl
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

CONFIG_DIR = str(STATE_DIR)
LOG_FILE = os.path.join(CONFIG_DIR, "paimenos-events.log")
SERVICE_NAMES = ("paimenos-menu.service", "paimenos-timer.service", "paimenos-media.service", "paimenos-cursor.service")


def log_event(component, message):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LOG_FILE + ".lock", "a", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 256 * 1024:
                os.replace(LOG_FILE, LOG_FILE + ".previous")
            with open(LOG_FILE, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"),
                                         "component": component, "message": str(message)[:2000]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def command_output(command, timeout=4):
    try:
        environment = os.environ.copy()
        runtime = "/run/user/" + str(os.getuid())
        if os.path.isdir(runtime):
            environment.setdefault("XDG_RUNTIME_DIR", runtime)
            environment.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=" + runtime + "/bus")
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=environment)
        return process.stdout.strip() if process.returncode == 0 else (process.stderr.strip() or f"Exit {process.returncode}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)


def read_tail(path, maximum=12000):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - maximum))
            return handle.read(maximum).decode("utf-8", errors="replace")
    except OSError:
        return "Noch keine Meldungen vorhanden."


def find_program(name):
    found = shutil.which(name)
    if found:
        return found
    for directory in ("/usr/games", "/usr/local/games", "/usr/bin"):
        path = os.path.join(directory, name)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def power_supply_summary(directory="/sys/class/power_supply"):
    """Nur Ladestand/Status auslesen, keine Seriennummern oder aktiven Tests."""
    lines = []
    try:
        devices = sorted(Path(directory).iterdir())
    except OSError:
        return "Keine Akku-/Netzteilinformationen verfügbar."
    for device in devices:
        fields = []
        for name, label in (("type", "Typ"), ("status", "Status"),
                            ("capacity", "Ladestand (%)"), ("online", "Netzteil verbunden")):
            try:
                value = (device / name).read_text(encoding="utf-8").strip()[:80]
            except OSError:
                continue
            if value:
                fields.append(label + ": " + value)
        if fields:
            lines.append(device.name + " · " + ", ".join(fields))
    return "\n".join(lines) or "Keine Akku-/Netzteilinformationen verfügbar."


def bluetooth_diagnostics():
    try:
        from paimenos.bluetooth import bluetooth_request
        state = bluetooth_request()
        operation = state.get('operation')
        parts = ['Bluetooth-Verwaltung: ' + ('bereit' if state.get('available') else 'nicht bereit')]
        if operation:
            parts.append('Laufender Vorgang: ' + operation.get('action', '') + ' · ' + operation.get('name', ''))
        if state.get('error'):
            parts.append('Fehler: ' + state['error'])
        parts += state.get('events', [])
        return '\n'.join(parts)
    except Exception as exc:
        return 'Bluetooth-Diagnose nicht erreichbar: ' + str(exc)


def collect_diagnostics():
    programs = {name: find_program(name) or "Nicht gefunden" for name in
                ("tuxpaint", "udisksctl", "lsblk", "findmnt", "systemctl", "firefox-esr",
                 "tlp-stat", "zramctl", "sensors", "smartctl", "fwupdmgr", "v4l2-ctl", "flatpak")}
    media = command_output(["lsblk", "-o", "NAME,TYPE,FSTYPE,LABEL,MOUNTPOINTS,RM,HOTPLUG,TRAN"])
    services = {}
    for name in SERVICE_NAMES:
        services[name] = command_output(["systemctl", "--user", "show", name,
                                        "-p", "ActiveState", "-p", "SubState", "-p", "NRestarts", "-p", "ExecMainStatus"])
    savedir = os.path.expanduser("~/.tuxpaint")
    saved = os.path.join(savedir, "saved")
    nearest = saved
    while not os.path.exists(nearest) and os.path.dirname(nearest) != nearest:
        nearest = os.path.dirname(nearest)
    tuxpaint = programs["tuxpaint"]
    laptop = {"Bluetooth-Kopplung": bluetooth_diagnostics(), "Akku und Netzteil": power_supply_summary(),
              "Arbeitsspeicher": command_output(["free", "-h"]),
              "Auslagerungsspeicher": command_output(["swapon", "--show"]),
              "Temperaturen": command_output(["sensors"]),
              "Kameras": command_output(["v4l2-ctl", "--list-devices"]),
              "Wartungsdienste": command_output(["systemctl", "show", "tlp.service",
                  "zramswap.service", "fstrim.timer", "apt-daily-upgrade.timer", "paimenos-app-update.timer",
                  "-p", "Id", "-p", "LoadState", "-p", "ActiveState", "-p", "UnitFileState"])}
    return {"timestamp": datetime.now().isoformat(timespec="seconds"), "programs": programs,
            "media": media, "services": services, "laptop": laptop, "tuxpaint_savedir": saved,
            "flatpak_apps": command_output(['flatpak', 'list', '--system', '--app', '--columns=name,application,version,branch,origin']),
            "flatpak_updates": command_output(['systemctl', 'show', 'paimenos-app-update.timer', 'paimenos-app-update.service', '-p', 'Id', '-p', 'ActiveState', '-p', 'Result', '-p', 'NextElapseUSecRealtime']),
            "tuxpaint_writable": os.access(nearest, os.W_OK),
            "tuxpaint_version": command_output([tuxpaint, "--version"]) if tuxpaint != "Nicht gefunden" else "Nicht installiert",
            "events": read_tail(LOG_FILE), "errors": read_tail(os.path.join(CONFIG_DIR, "paimenos-errors.log")),
            "application": read_tail(os.path.join(CONFIG_DIR, "paimenos-application.log")),
            "session": read_tail(os.path.join(CONFIG_DIR, "paimenos-session.log")),
            "journal": command_output(["journalctl", "--user", "--no-pager", "-n", "30", "--output=short-iso",
                                       "-u", "paimenos-timer.service", "-u", "paimenos-media.service", "-u", "paimenos-menu.service"])}


def diagnostics_text(data):
    parts = ["PaimenOS Geräte-Diagnose · " + data["timestamp"], "\nProgramme:"]
    parts += [f"{name}: {path}" for name, path in data["programs"].items()]
    parts += ["\nTux Paint:", data["tuxpaint_version"], "Bilder: " + data["tuxpaint_savedir"],
              "Speicherordner beschreibbar: " + ("Ja" if data["tuxpaint_writable"] else "Nein"), "\nMedien:", data["media"], "\nDienste:"]
    parts += [f"{name}:\n{status}" for name, status in data["services"].items()]
    parts += ['\nFlatpak-Apps (installierte Versionen):', data.get('flatpak_apps', 'Nicht installiert'),
              '\nApp-Aktualisierungen:', data.get('flatpak_updates', 'Nicht eingerichtet')]
    for heading, status in data.get("laptop", {}).items():
        parts += ["\n" + heading + ":", status]
    for heading, key in (("Letzte Ereignisse", "events"), ("Fehler", "errors"),
                         ("Anwendungsstart", "application"), ("Sitzungsstart", "session"), ("Hintergrunddienste", "journal")):
        parts += ["\n" + heading + ":", data[key]]
    return "\n".join(parts)
