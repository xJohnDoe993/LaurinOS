#!/bin/bash
# Wird von install.sh in einer gemeinsamen Shell geladen.
# 13. Rechte setzen & System-Setup abschließen
# ---------------------------------------------------------------------------
echo "Rechte setzen & Setup abschließen ..."

chown -R "${KIDS_USER}:${KIDS_USER}" "${KIDS_HOME}/.config" "${KIDS_HOME}/.local" "${KIDS_HOME}/.mozilla" "${KIDS_HOME}/.Xresources" "${KIDS_HOME}/.gtkrc-2.0"
chmod -R 755 "${ICONS_DIR}"
chmod 0755 "${KIDS_HOME}"
chmod 0700 "${KIDS_HOME}/.mozilla/laurinos-webapps"

systemctl set-default graphical.target >/dev/null 2>&1 || true
systemctl enable lightdm >/dev/null 2>&1 || true
systemctl enable NetworkManager >/dev/null 2>&1 || true
systemctl enable systemd-resolved >/dev/null 2>&1 || true

date > "${MARKER_FILE}"

echo
echo "============================================================"
echo " INSTALLATION ERFOLGREICH ABGESCHLOSSEN (0.60.0)"
echo "============================================================"
if [[ "$LAURINOS_WIFI_READY" != true ]]; then
    echo " WLAN-PRÜFUNG OFFEN: Gerät wird noch nicht verwaltet."
    echo " Nach dem Neustart WLAN-Diagnose im Terminal prüfen."
fi
echo "Installation abgeschlossen. Ein Neustart aktiviert die neue Sitzung."
echo

if [[ "${LAURINOS_REBOOT:-0}" == 1 ]]; then
    sleep 3
    reboot
else
    echo "Bitte das Gerät jetzt neu starten: sudo reboot"
fi
