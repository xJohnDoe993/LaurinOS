import json
from pathlib import Path
apps = json.loads((Path(__file__).resolve().parents[1] / "data/default-webapps.json").read_text())
print(",\n".join(json.dumps(app, ensure_ascii=False) for app in apps))
