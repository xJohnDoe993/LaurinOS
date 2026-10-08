#!/usr/bin/python3
"""Choose the initial webapp list; never replace a parent's existing app list."""
import json
from pathlib import Path
import sys
release = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(release / ('app' if (release / 'app').is_dir() else 'src')))
from paimenos.i18n import language
name = 'default-webapps.en.json' if language() == 'en' else 'default-webapps.json'
apps = json.loads((release / 'data' / name).read_text(encoding='utf-8'))
print(',\n'.join(json.dumps(app, ensure_ascii=False) for app in apps))
