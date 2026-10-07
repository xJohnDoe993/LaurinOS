#!/bin/bash
# Runs interactively on tty1, using the same installer as a manual installation.
set -Eeuo pipefail
[[ $EUID == 0 ]] || exit 1
SOURCE=/opt/paimenos-source
PENDING=/var/lib/paimenos/setup-pending
SUCCESS=/etc/paimenos-laptop.installed
[[ -f $PENDING ]] || exit 0
# Never install/update a pre-existing finished system automatically.
if [[ ! -f $SUCCESS ]]; then
    printf '\nWillkommen bei PaimenOS!\nDie Debian-Grundinstallation ist abgeschlossen.\n'
    printf 'Für Programme und Emulatoren ist jetzt eine Internetverbindung erforderlich.\n'
    while :; do
        printf '\n1) WLAN/Netzwerk einrichten\n2) PaimenOS-Setup starten\n3) Neu starten\n'
        read -r -p 'Auswahl [2]: ' choice
        case "$choice" in
            1) nmtui || true; continue ;;
            3) systemctl reboot; exit 0 ;;
            ''|2) ;;
            *) continue ;;
        esac
        args=()
        if [[ -e /usr/local/lib/paimenos/current ]]; then args+=(--resume); fi
        # App, emulator and PIN prompts are handled by install.sh unchanged.
        if PAIMENOS_REBOOT=0 bash "$SOURCE/install.sh" "${args[@]}"; then
            [[ -f $SUCCESS ]] && break
        fi
        printf '\nSetup noch nicht abgeschlossen. Netzwerk prüfen und erneut starten.\n'
        printf 'Vorhandene Einstellungen werden beim Fortsetzen beibehalten.\n'
    done
fi
rm -f "$PENDING"
systemctl disable paimenos-setup.service
printf '\nPaimenOS ist eingerichtet. Der nächste Neustart öffnet die Kinderoberfläche.\n'
read -r -p 'Jetzt neu starten? [J/n]: ' answer
case "$answer" in
    n|N) printf 'Neustart später mit sudo reboot.\n' ;;
    *) systemctl reboot ;;
esac
