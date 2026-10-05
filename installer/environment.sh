export DEBIAN_FRONTEND=noninteractive
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games"


KIDS_USER="kids"
KIDS_HOME="/home/${KIDS_USER}"
LAURINOS_DIR="/usr/local/lib/laurinos/current/app/laurinos"
OPENBOX_DIR="${KIDS_HOME}/.config/openbox"
CONFIG_DIR="${KIDS_HOME}/.config/laurinos"
STATE_DIR="${KIDS_HOME}/.local/state/laurinos"
ICONS_DIR="${KIDS_HOME}/.local/share/laurinos/icons"
MENU="${LAURINOS_DIR}/menu.py"
APPS_JSON="${CONFIG_DIR}/apps.json"
SETTINGS_JSON="${CONFIG_DIR}/settings.json"
TIMER_SCRIPT="${LAURINOS_DIR}/timer.py"
LOCKSCREEN_SCRIPT="${LAURINOS_DIR}/lockscreen.py"
OVERLAY_SCRIPT="${LAURINOS_DIR}/close_overlay.py"
MEDIA_DAEMON="${LAURINOS_DIR}/media.py"
PARENT_WEB_SCRIPT="${LAURINOS_DIR}/parent_web.py"
STATE_SCRIPT="${LAURINOS_DIR}/state.py"
MARKER_FILE="/etc/laurinos-laptop.installed"

# Optionale Laptop-Funktionen: 0 überspringt die Einrichtung, 1 aktiviert sie.
LAURINOS_ENABLE_TLP="${LAURINOS_ENABLE_TLP:-1}"
LAURINOS_ENABLE_ZRAM="${LAURINOS_ENABLE_ZRAM:-1}"
LAURINOS_ENABLE_AUTO_UPDATES="${LAURINOS_ENABLE_AUTO_UPDATES:-1}"
LAURINOS_ENABLE_APP_UPDATES="${LAURINOS_ENABLE_APP_UPDATES:-$LAURINOS_ENABLE_AUTO_UPDATES}"
for install_option in "$LAURINOS_ENABLE_TLP" "$LAURINOS_ENABLE_ZRAM" "$LAURINOS_ENABLE_AUTO_UPDATES" "$LAURINOS_ENABLE_APP_UPDATES"; do
    if [[ "$install_option" != 0 && "$install_option" != 1 ]]; then
        echo "FEHLER: Laptop-Installationsschalter müssen 0 oder 1 sein." >&2
        exit 1
    fi
done

echo "LaurinOS 0.60.0 – Neuinstallation"

# Einen laufenden Backend-Auftrag nicht mitten in apt/dpkg abbrechen.
exec 9>/run/laurinos-emulator-install.lock
chmod 0600 /run/laurinos-emulator-install.lock
if ! flock -n 9; then
    echo "FEHLER: Im Backend läuft eine Emulator-Installation. Bitte deren Abschluss abwarten und das Setup erneut starten." >&2
    exit 1
fi
systemctl stop laurinos-emulators.service >/dev/null 2>&1 || true
flock -u 9
exec 9>&-

