"""Einmalige Kopie vorhandener App-Daten; Ausführung als kids, nie als root."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MIGRATIONS = {
    'org.luanti.luanti': [(('.var/app/net.minetest.Minetest/.minetest', '.minetest'), '.minetest')],
    'org.kde.gcompris': [(('.config/gcompris',), 'config/gcompris'),
                         (('.local/share/gcompris',), 'data/gcompris')],
    'net.supertuxkart.SuperTuxKart': [(('.config/supertuxkart',), 'config/supertuxkart'),
                                    (('.local/share/supertuxkart',), 'data/supertuxkart')],
    'org.libreoffice.LibreOffice': [(('.config/libreoffice',), 'config/libreoffice')],
}


def copy_once(home, sources, destination):
    target = home / destination
    # Vorhandene Flatpak-Daten haben immer Vorrang, auch bei Wiederholung.
    if target.exists() or target.is_symlink():
        return
    source = next((home / item for item in sources
                   if (home / item).is_dir() and not (home / item).is_symlink()), None)
    if source is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.paimenos-migrate-', dir=target.parent))
    try:
        # Keine Symlinks auf außerhalb liegende Ordner oder Spezialdateien folgen.
        def ignore(directory, names):
            return [name for name in names if (Path(directory) / name).is_symlink() or
                    not ((Path(directory) / name).is_file() or (Path(directory) / name).is_dir())]
        shutil.copytree(source, staging / 'data', ignore=ignore)
        os.rename(staging / 'data', target)
        print('  ✓ Vorhandene Daten kopiert: ' + str(source))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def migrate(home, app_id):
    home = Path(home)
    if app_id == 'org.luanti.luanti':
        running = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x',
                                  '(minetest|minetestserver|luanti|luantiserver|luanti.bin)'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if running.returncode == 0:
            raise RuntimeError('Luanti/Minetest läuft noch. Bitte schließen und das Setup erneut ausführen, damit Spielstände sicher kopiert werden.')
    for sources, destination in MIGRATIONS.get(app_id, []):
        copy_once(home, sources, '.var/app/' + app_id + '/' + destination)
    if app_id == 'org.luanti.luanti':
        # Das bisher vom Debian-Paket gelieferte Spiel ebenfalls erhalten.
        for directory in ('/usr/share/games/minetest/games', '/usr/share/luanti/games'):
            game_root = Path(directory)
            if not game_root.is_dir():
                continue
            for game in game_root.iterdir():
                if game.is_dir() and (game / 'game.conf').is_file() and game.name != 'devtest':
                    copy_once(home, (str(game),), '.var/app/' + app_id + '/.minetest/games/' + game.name)
        games = home / '.var/app' / app_id / '.minetest/games'
        if not games.is_dir() or not any(games.glob('*/game.conf')):
            print('  Hinweis: Luanti benötigt ein Spiel. Im Startbildschirm unter Inhalte z. B. Minetest Game installieren.')


if __name__ == '__main__':
    try:
        migrate(sys.argv[1], sys.argv[2])
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
