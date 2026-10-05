#!/bin/bash
# Wird von install.sh in einer gemeinsamen Shell geladen.
# 11. Eltern-Webbackend auf Port 80
# ---------------------------------------------------------------------------
# Gleicher fester Katalog und Installer wie bei einer späteren Backend-Nachinstallation.
echo "Ausgewählte Emulatoren installieren ..."
/usr/bin/python3 -I /usr/local/lib/laurinos/current/run.py emulator_service --install "$EMULATOR_SELECTION" || \
    echo "Hinweis: Nicht alle gewählten Emulatoren konnten eingerichtet werden. Im Elternbackend unter Emulatoren erneut installieren." >&2

echo "Eltern-Webbackend auf Port 80 einrichten ..."

# WLAN-Dienst und Client verwenden dasselbe root-eigene Paket.

install_repo_file systemd/system/laurinos-emulators.service /etc/systemd/system/laurinos-emulators.service

install_repo_file systemd/system/laurinos-parent-web.service /etc/systemd/system/laurinos-parent-web.service

install_repo_file systemd/system/laurinos-bluetooth.service /etc/systemd/system/laurinos-bluetooth.service

install_repo_file systemd/system/laurinos-wifi.service /etc/systemd/system/laurinos-wifi.service

systemctl daemon-reload
systemctl enable laurinos-wifi.service
systemctl enable laurinos-emulators.service
systemctl enable laurinos-bluetooth.service
systemctl enable laurinos-parent-web.service >/dev/null 2>&1 || true

# Datei wurde ersetzt: ein laufender Dienst muss den neuen Code laden.
# Rechte vor Dienststart setzen, nicht erst am Ende des Setups.
chown -R "${KIDS_USER}:${KIDS_USER}" "${CONFIG_DIR}" "${STATE_DIR}"
source "${REPO_DIR}/installer/network.sh"
systemctl enable --now bluetooth.service
rfkill unblock bluetooth || echo "Hinweis: Bluetooth ggf. am Hardware-Schalter freigeben." >&2
systemctl restart laurinos-bluetooth.service
if ! systemctl is-active --quiet laurinos-bluetooth.service; then
    echo "FEHLER: Bluetooth-Verwaltung nicht gestartet. Siehe systemctl status laurinos-bluetooth.service" >&2
    exit 1
fi
systemctl restart laurinos-emulators.service
if ! systemctl is-active --quiet laurinos-emulators.service; then
    echo "FEHLER: Emulator-Installationsdienst ist nicht gestartet. Siehe systemctl status laurinos-emulators.service" >&2
    exit 1
fi
systemctl restart laurinos-parent-web.service
sleep 2
if ! systemctl is-active --quiet laurinos-parent-web.service; then
    echo "FEHLER: Eltern-Webbackend ist nicht gestartet. Siehe systemctl status laurinos-parent-web.service" >&2
    exit 1
fi

