import os, shlex, sys
app_id, flatpak_id = sys.argv[1:]
path = '/usr/local/bin/paimenos-app-' + app_id
with open(path + '.new', 'w', encoding='utf-8') as handle:
    handle.write('#!/bin/sh\n# PaimenOS: stabile Flatpak-App als angemeldeter Benutzer starten.\n')
    handle.write('exec /usr/bin/python3 -I /usr/local/lib/paimenos/current/run.py cli_flatpak ' + shlex.quote(flatpak_id) + ' "$@"\n')
os.chmod(path + '.new', 0o755)
os.replace(path + '.new', path)
