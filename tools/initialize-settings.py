"""Create initial parent settings; never overwrite a pre-existing file."""
import json
from pathlib import Path
import re
import sys

path, pin = Path(sys.argv[1]), sys.argv[2]
if not re.fullmatch(r"[0-9]{4,12}", pin):
    raise SystemExit("Eltern-PIN: 4 bis 12 Ziffern erforderlich.")
settings = json.loads((Path(__file__).resolve().parents[1] / "data/default-settings.json").read_text())
settings["pin"] = pin
with path.open("x", encoding="utf-8") as handle:
    json.dump(settings, handle, ensure_ascii=False, indent=2)
path.chmod(0o600)
