#!/bin/bash
set -Eeuo pipefail
REPO_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export REPO_DIR
if [[ "${1:-}" == --help ]]; then
    cat "${REPO_DIR}/docs/install-help.txt"
    exit 0
fi
RESUME=0
if [[ "${1:-}" == --resume ]]; then RESUME=1; shift; fi
if [[ $# -ne 0 ]]; then echo "Unbekannte Argumente. Siehe ./install.sh --help" >&2; exit 2; fi
if [[ "$EUID" -ne 0 ]]; then echo "Aufruf: sudo bash install.sh" >&2; exit 1; fi
. /etc/os-release
if [[ "${ID:-}" != debian || ! "${VERSION_CODENAME:-}" =~ ^(bookworm|trixie)$ ]]; then
    echo "Debian 12 oder 13 erforderlich." >&2; exit 1
fi
if [[ -f /home/kids/.config/openbox/laurinos-settings.json || -e /etc/laurinos-laptop.installed ]]; then
    echo "Diese Version erwartet eine Neuinstallation. Für modulare Installationen: sudo bash update.sh" >&2
    exit 1
fi
if [[ -e /usr/local/lib/laurinos/current && "$RESUME" != 1 ]]; then
    echo "Unvollständige modulare Installation gefunden. Fortsetzen: sudo bash install.sh --resume" >&2
    exit 1
fi
exec 8>/run/laurinos-maintenance.lock
if ! flock -n 8; then echo "Eine LaurinOS-Wartung läuft bereits." >&2; exit 1; fi
trap 'echo "FEHLER: ${BASH_SOURCE[0]}:${LINENO}; Installation nicht abgeschlossen." >&2' ERR
# A custom PIN is required before making changes to the system.
if [[ "$RESUME" == 1 && -f /home/kids/.config/laurinos/settings.json ]]; then
    LAURINOS_PARENT_PIN=""
    echo "Vorhandene Eltern-Einstellungen und PIN werden beibehalten."
else
    LAURINOS_PARENT_PIN="${LAURINOS_PARENT_PIN:-}"
    if [[ -z "$LAURINOS_PARENT_PIN" ]]; then
        read -r -s -p "Neue Eltern-PIN (4 bis 12 Ziffern): " LAURINOS_PARENT_PIN </dev/tty
        echo
        read -r -s -p "PIN wiederholen: " pin_repeat </dev/tty
        echo
        if [[ "$LAURINOS_PARENT_PIN" != "$pin_repeat" ]]; then echo "PINs stimmen nicht überein." >&2; exit 1; fi
        unset pin_repeat
    fi
    if [[ ! "$LAURINOS_PARENT_PIN" =~ ^[0-9]{4,12}$ ]]; then echo "PIN: 4 bis 12 Ziffern erforderlich." >&2; exit 1; fi
fi
unset BASH_ENV
source "${REPO_DIR}/installer/common.sh"
source "${REPO_DIR}/installer/environment.sh"
for module in 10-system 20-hardware 30-plymouth 40-user 50-browser 60-apps 70-defaults 80-services 90-desktop 99-finish; do
    source "${REPO_DIR}/installer/${module}.sh"
done
