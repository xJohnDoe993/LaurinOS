import json, sys
app_id, title, theme, command, source, flatpak_id, icon_file, package = sys.argv[1:]
item = dict(id=app_id, title=title, type='native', icon_theme=theme, command=command,
            install_source=source, package=package)
if flatpak_id:
    item['flatpak_id'] = flatpak_id
if icon_file:
    item['icon_file'] = icon_file
print(json.dumps(item, ensure_ascii=False) + ',')
