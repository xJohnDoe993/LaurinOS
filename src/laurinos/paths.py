"""Central paths. Application files and writable user data are independent."""
from pathlib import Path
import os

RELEASE_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = RELEASE_DIR / "assets"
DATA_DIR = RELEASE_DIR / "data"
CONFIG_DIR = Path.home() / ".config/laurinos"
STATE_DIR = Path.home() / ".local/state/laurinos"
USER_DATA_DIR = Path.home() / ".local/share/laurinos"


def ensure_user_directories():
    for directory in (CONFIG_DIR, STATE_DIR, USER_DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    STATE_DIR.chmod(0o700)
