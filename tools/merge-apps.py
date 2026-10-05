import json, os, shlex, sys
path = sys.argv[1]
with open(path + ".new", encoding="utf-8") as handle:
    generated = json.load(handle)
old = []
if os.path.exists(path):
    with open(path, encoding="utf-8") as handle:
        old = json.load(handle)
    if not isinstance(old, list) or not all(isinstance(item, dict) for item in old):
        raise ValueError("Ungültige Apps-Datei; Sicherung bleibt erhalten.")
existing = {item.get("id"): item for item in old}
merged = []
for item in generated:
    if os.path.exists(path) and item.get("type") == "webapp" and item["id"] not in existing:
        continue
    previous = existing.pop(item["id"], None)
    # Eigene Startbefehle, Bilder und Namen beim Setup-Update erhalten.
    preserve = previous and (item.get("type") == "webapp" or
                             (previous.get("user_modified") is True and item.get("id") != "poweroff"))
    if preserve:
        saved = dict(previous)
        if item.get('type') == 'native' and saved.get('type') == 'native':
            # Bei einem Quellenwechsel Standard-Startprogramme austauschen,
            # dabei vom Elternbereich gesetzte Parameter und Bilder erhalten.
            defaults = {
                'minetest': {'minetest', 'luanti'}, 'gcompris': {'gcompris-qt'},
                'supertuxkart': {'supertuxkart'}, 'gimp': {'gimp'},
                'libreoffice': {'libreoffice', 'soffice'},
            }
            try:
                old_command = shlex.split(saved.get('command', ''))
                new_command = shlex.split(item.get('command', ''))
            except ValueError:
                old_command, new_command = [], []
            if old_command and new_command and item['id'] in defaults:
                old_program = old_command[0]
                standard = (os.path.basename(old_program) in defaults[item['id']] and
                            ('/' not in old_program or os.path.dirname(old_program) in ('/usr/bin', '/usr/games', '/bin')))
                wrapper = old_program == '/usr/local/bin/laurinos-app-' + item['id']
                if standard or wrapper:
                    saved['command'] = shlex.join(new_command + old_command[1:])
                    for key in ('install_source', 'flatpak_id', 'package'):
                        if key in item:
                            saved[key] = item[key]
                        else:
                            saved.pop(key, None)
                    if not saved.get('icon_file') and item.get('icon_file'):
                        saved['icon_file'] = item['icon_file']
        merged.append(saved)
    else:
        merged.append(item)
merged.extend(existing.values())
with open(path + ".new", "w", encoding="utf-8") as handle:
    json.dump(merged, handle, indent=2, ensure_ascii=False)
os.replace(path + ".new", path)
