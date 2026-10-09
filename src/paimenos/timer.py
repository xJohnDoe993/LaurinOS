#!/usr/bin/env python3
import os, sys, time, subprocess, fcntl
from paimenos.state import read_settings, update_settings, remaining_seconds
from paimenos.screen_guard import protected_view_active

LOCKSCREEN_SCRIPT = "/usr/local/lib/paimenos/current/run.py"

def main():
    # Auch nach wiederholtem Openbox-Autostart nur einmal zählen.
    instance = open(os.path.expanduser("~/.local/state/paimenos/paimenos-timer.lock"), "a")
    try:
        fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    lock_process = None
    previous = time.monotonic()
    while True:
        time.sleep(1)
        now = time.monotonic()
        elapsed = max(0, int(now - previous))
        def tick(data):
            # Während der Sperre keine weitere Bildschirmzeit zählen.
            if lock_process is None or lock_process.poll() is not None:
                data["today_used_seconds"] += elapsed
        settings = read_settings()
        left = remaining_seconds(settings)
        if elapsed >= 10 or (left is not None and elapsed >= left):
            # Suspend zählt nicht: monotonic läuft während suspend nicht weiter.
            settings = update_settings(tick)
            previous += elapsed
        remaining = remaining_seconds(settings)
        if remaining == 0:
            if (lock_process is None or lock_process.poll() is not None) and not protected_view_active():
                lock_process = subprocess.Popen([sys.executable, "-I", LOCKSCREEN_SCRIPT, "lockscreen"])
        elif lock_process is not None and lock_process.poll() is None:
            lock_process.terminate()
            lock_process.wait(timeout=5)

if __name__ == "__main__":
    main()

