#!/usr/bin/python3
"""Use the same locale detection and catalogue from Bash and Python installers."""
from pathlib import Path
import sys

release = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(release / ('app' if (release / 'app').is_dir() else 'src')))
from paimenos.i18n import language, t

if sys.argv[1:] == ['--language']:
    print(language())
elif sys.argv[1:]:
    print(t(sys.argv[1], **{'value' + str(i): value for i, value in enumerate(sys.argv[2:])}), end='')
