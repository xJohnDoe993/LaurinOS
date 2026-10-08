#!/bin/bash
# Keine Live-Übergabe: Debian hält die Setup-Verbindung bis zum Neustart.
PAIMENOS_WIFI_READY=false
PAIMENOS_WIFI_PENDING=false
/usr/bin/python3 -I "${REPO_DIR}/tools/stage-wifi.py" prepare
install_repo_file systemd/system/paimenos-wifi-migration.service /etc/systemd/system/paimenos-wifi-migration.service
systemctl daemon-reload
systemctl enable paimenos-wifi-migration.service
if [[ -f /var/lib/paimenos/wifi-migration/pending.json ]]; then
    PAIMENOS_WIFI_PENDING=true
else
    # Bereits von NetworkManager eingerichtetes WLAN wird nicht verändert.
    PAIMENOS_WIFI_READY=true
fi
systemctl restart paimenos-wifi.service
systemctl is-active --quiet paimenos-wifi.service || {
    echo "$(paimenos_text 'FEHLER: WLAN-Menüdienst konnte nicht gestartet werden.')" >&2
    exit 1
}
