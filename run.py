#!/usr/bin/python3
"""Stable launcher: python3 -I /usr/local/lib/laurinos/current/run.py MODULE."""
from pathlib import Path
import runpy
import sys

release = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(release / ("app" if (release / "app").is_dir() else "src")))
from laurinos.paths import ensure_user_directories

ALLOWED = {"menu", "timer", "media", "status_overlay", "close_overlay", "lockscreen",
           "parent_web", "bluetooth", "wifi", "controller", "emulator_service",
           "cli_osd_notify", "cli_update_apps", "cli_flatpak", "cli_emulator", "cli_emulator_check"}
if len(sys.argv) < 2 or sys.argv[1] not in ALLOWED:
    raise SystemExit("Aufruf: run.py " + "|".join(sorted(ALLOWED)))
module = sys.argv.pop(1)
# Privileged services do not create directories in the child's home.
if module not in {"wifi", "bluetooth", "emulator_service", "cli_update_apps"}:
    ensure_user_directories()
runpy.run_module("laurinos." + module, run_name="__main__")
