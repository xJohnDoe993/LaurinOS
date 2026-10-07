#!/bin/bash
# Wird von install.sh in einer gemeinsamen Shell geladen.
# 11. Eltern-Webbackend auf Port 80
# ---------------------------------------------------------------------------
# Gleicher fester Katalog und Installer wie bei einer späteren Backend-Nachinstallation.
echo "Ausgewählte Emulatoren installieren ..."
/usr/bin/python3 -I /usr/local/lib/paimenos/current/run.py emulator_service --install "$EMULATOR_SELECTION" || \
    echo "Hinweis: Nicht alle gewählten Emulatoren konnten eingerichtet werden. Im Elternbackend unter Emulatoren erneut installieren." >&2

echo "Eltern-Webbackend auf Port 80 einrichten ..."

# WLAN-Dienst und Client verwenden dasselbe root-eigene Paket.

install_repo_file systemd/system/paimenos-emulators.service /etc/systemd/system/paimenos-emulators.service
install_repo_file systemd/system/paimenos-updates.service /etc/systemd/system/paimenos-updates.service

install_repo_file systemd/system/paimenos-parent-web.service /etc/systemd/system/paimenos-parent-web.service

install_repo_file systemd/system/paimenos-bluetooth.service /etc/systemd/system/paimenos-bluetooth.service

install_repo_file systemd/system/paimenos-wifi.service /etc/systemd/system/paimenos-wifi.service

systemctl daemon-reload
systemctl enable paimenos-wifi.service
systemctl enable paimenos-emulators.service
systemctl enable paimenos-updates.service
systemctl enable paimenos-bluetooth.service
systemctl enable paimenos-parent-web.service >/dev/null 2>&1 || true

# Datei wurde ersetzt: ein laufender Dienst muss den neuen Code laden.
# Rechte vor Dienststart setzen, nicht erst am Ende des Setups.
chown -R "${KIDS_USER}:${KIDS_USER}" "${CONFIG_DIR}" "${STATE_DIR}"
source "${REPO_DIR}/installer/network.sh"
systemctl enable --now bluetooth.service
rfkill unblock bluetooth || echo "Hinweis: Bluetooth ggf. am Hardware-Schalter freigeben." >&2
systemctl restart paimenos-bluetooth.service
if ! systemctl is-active --quiet paimenos-bluetooth.service; then
    echo "FEHLER: Bluetooth-Verwaltung nicht gestartet. Siehe systemctl status paimenos-bluetooth.service" >&2
    exit 1
fi
systemctl restart paimenos-emulators.service
if ! systemctl is-active --quiet paimenos-emulators.service; then
    echo "FEHLER: Emulator-Installationsdienst ist nicht gestartet. Siehe systemctl status paimenos-emulators.service" >&2
    exit 1
fi
systemctl restart paimenos-parent-web.service paimenos-updates.service
sleep 2
if ! systemctl is-active --quiet paimenos-parent-web.service; then
    echo "FEHLER: Eltern-Webbackend ist nicht gestartet. Siehe systemctl status paimenos-parent-web.service" >&2
    exit 1
fi
if ! systemctl is-active --quiet paimenos-updates.service; then
    echo "FEHLER: Release-Updater ist nicht gestartet. Siehe systemctl status paimenos-updates.service" >&2
    exit 1
fi
