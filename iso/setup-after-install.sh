#!/bin/bash
# Runs interactively on tty1, using the same installer as a manual installation.
set -Eeuo pipefail
[[ $EUID == 0 ]] || exit 1
SOURCE=/opt/paimenos-source
PENDING=/var/lib/paimenos/setup-pending
SUCCESS=/etc/paimenos-laptop.installed
[[ -f $PENDING ]] || exit 0
REPO_DIR="$SOURCE"
source "$SOURCE/installer/language.sh"
APT_SESSION_CONFIG=$(mktemp /run/paimenos-apt.XXXXXX)
trap 'rm -f "$APT_SESSION_CONFIG"' EXIT
# Never install/update a pre-existing finished system automatically.
if [[ ! -f $SUCCESS ]]; then
    printf "$(paimenos_text '\nWillkommen bei PaimenOS!\nDie Debian-Grundinstallation ist abgeschlossen.\n')"
    printf "$(paimenos_text 'Für Programme und Emulatoren ist jetzt eine Internetverbindung erforderlich.\n')"
    while :; do
        printf "$(paimenos_text '\n1) WLAN/Netzwerk einrichten\n2) PaimenOS-Setup starten\n3) Neu starten\n4) Netzwerkdiagnose / IPv4-Test\n')"
        read -r -p "$(paimenos_text 'Auswahl [2]: ')" choice
        case "$choice" in
            1) nmtui || true; continue ;;
            3) systemctl reboot; exit 0 ;;
            4)
                printf "$(paimenos_text '\nNetzwerkdiagnose und IPv4-APT-Test ...\n')"
                /usr/bin/python3 "$SOURCE/iso/prepare-apt.py" --diagnose || true
                if /usr/bin/python3 "$SOURCE/iso/prepare-apt.py" --apt-config "$APT_SESSION_CONFIG" &&
                    APT_CONFIG="$APT_SESSION_CONFIG" apt-get \
                        -o Acquire::ForceIPv4=true -o Acquire::ForceIPv6=false \
                        -o Acquire::Retries=0 -o Acquire::http::Timeout=10 \
                        -o Acquire::https::Timeout=10 -o APT::Update::Error-Mode=any update; then
                    printf "$(paimenos_text 'IPv4-APT-Test erfolgreich.\n')"
                else
                    printf "$(paimenos_text 'IPv4-APT-Test fehlgeschlagen. Bitte die Fehlermeldungen oben prüfen.\n')"
                fi
                read -r -p "$(paimenos_text 'Mit Enter zurück zum Setup-Menü: ')" diagnostic_answer
                continue
                ;;
            ''|2) ;;
            *) continue ;;
        esac
        if ! /usr/bin/python3 "$SOURCE/iso/prepare-apt.py" --apt-config "$APT_SESSION_CONFIG"; then
            printf "$(paimenos_text 'Paketquellen konnten nicht vorbereitet werden. Bitte prüfen und erneut versuchen.\n')"
            continue
        fi
        # An active link does not prove internet access. Require fresh, signed
        # package indexes before asking for the PIN or installing anything.
        if ! APT_CONFIG="$APT_SESSION_CONFIG" apt-get update; then
            printf "$(paimenos_text 'Debian-Paketquellen konnten nicht vollständig geprüft werden. Netzwerk und APT-Fehler oben prüfen; dann erneut versuchen.\n')"
            /usr/bin/python3 "$SOURCE/iso/prepare-apt.py" --diagnose || true
            continue
        fi
        args=()
        if [[ -e /usr/local/lib/paimenos/current ]]; then args+=(--resume); fi
        # App, emulator and PIN prompts are handled by install.sh unchanged.
        if APT_CONFIG="$APT_SESSION_CONFIG" PAIMENOS_REBOOT=0 bash "$SOURCE/install.sh" "${args[@]}"; then
            [[ -f $SUCCESS ]] && break
        fi
        printf "$(paimenos_text '\nSetup noch nicht abgeschlossen. Netzwerk prüfen und erneut starten.\n')"
        printf "$(paimenos_text 'Vorhandene Einstellungen werden beim Fortsetzen beibehalten.\n')"
    done
fi
rm -f "$PENDING"
systemctl disable paimenos-setup.service
printf "$(paimenos_text '\nPaimenOS ist eingerichtet. Der nächste Neustart öffnet die Kinderoberfläche.\n')"
read -r -p "$(paimenos_text 'Jetzt neu starten? [J/n]: ')" answer
case "$answer" in
    n|N) printf "$(paimenos_text 'Neustart später mit sudo reboot.\n')" ;;
    *) systemctl reboot ;;
esac
