#!/usr/bin/env python3
import json, os, subprocess, time, fcntl
from paimenos.state import atomic_json
from paimenos.diagnostics import log_event

LAST_FAILURE = {}

EJECTED_FILE = os.path.expanduser("~/.local/state/paimenos/paimenos-ejected.json")

def run_json(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if p.returncode == 0:
            return json.loads(p.stdout)
    except Exception:
        pass
    return {}

def mountpoints(entry):
    m = entry.get("mountpoints") or []
    if isinstance(m, str):
        return [m] if m else []
    return [x for x in m if x]

def scan_devices():
    data = run_json([
        "lsblk", "-J", "-o",
        "NAME,TYPE,FSTYPE,LABEL,MOUNTPOINTS,RM,HOTPLUG,TRAN"
    ])
    return data.get("blockdevices")

def walk_devices(devices, removable=False):
    for device in devices:
        removable_here = removable or bool(device.get("rm") or device.get("hotplug")
                                          or device.get("tran") == "usb")
        yield device, removable_here
        yield from walk_devices(device.get("children") or [], removable_here)

def try_mount():
    lock_path = os.path.join(os.path.dirname(EJECTED_FILE), "paimenos-media-operation.lock")
    with open(lock_path, "a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try_mount_locked()

def try_mount_locked():
    scanned = scan_devices()
    if scanned is None:
        return
    devices = list(walk_devices(scanned))
    try:
        with open(EJECTED_FILE, encoding="utf-8") as handle:
            ejected = set(json.load(handle))
    except (OSError, ValueError, TypeError):
        ejected = set()
    present = {"/dev/" + device.get("name", "") for device, _ in devices}
    still_ejected = ejected & present
    if still_ejected != ejected:
        atomic_json(EJECTED_FILE, sorted(still_ejected))
    for device, removable in devices:
        # USB-Sticks können ein Dateisystem direkt auf dem ganzen Laufwerk haben.
        if device.get("type") not in ("part", "disk") or not removable:
            continue
        if device.get("fstype") not in {"vfat", "exfat", "ntfs", "ntfs3", "ext2", "ext3", "ext4", "iso9660", "udf"}:
            continue
        dev = "/dev/" + device.get("name", "")
        if mountpoints(device) or dev in still_ejected or not os.path.exists(dev):
            continue
        try:
            now = time.monotonic()
            if dev in LAST_FAILURE and now - LAST_FAILURE[dev] < 30:
                continue
            result = subprocess.run(["udisksctl", "mount", "-b", dev, "--no-user-interaction"],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                LAST_FAILURE[dev] = now
                log_event("Medien", f"{dev}: " + (result.stderr.strip() or "Einbinden fehlgeschlagen."))
            else:
                LAST_FAILURE.pop(dev, None)
                log_event("Medien", f"{dev} eingebunden.")
        except (OSError, subprocess.TimeoutExpired) as exc:
            LAST_FAILURE[dev] = time.monotonic()
            log_event("Medien", f"{dev}: {exc}")

def main():
    instance = open(os.path.expanduser("~/.local/state/paimenos/paimenos-media.lock"), "a")
    try:
        fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    while True:
        try_mount()
        time.sleep(2)

if __name__ == "__main__":
    main()
