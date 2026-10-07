#!/bin/bash
# Wird von install.sh in einer gemeinsamen Shell geladen.
# 12. Openbox Autostart & Keybindings
# ---------------------------------------------------------------------------
echo "Autostart & Openbox Konfiguration aktualisieren ..."

install_repo_file config/lightdm/lightdm.conf /etc/lightdm/lightdm.conf

if [[ -x /usr/sbin/lightdm ]]; then
    printf '%s\n' '/usr/sbin/lightdm' > /etc/X11/default-display-manager
fi

install_repo_file config/openbox/rc.xml "${OPENBOX_DIR}/rc.xml"

mkdir -p /etc/systemd/user
install_repo_file systemd/user/paimenos-session.target /etc/systemd/user/paimenos-session.target

install_repo_file systemd/user/paimenos-osd.service /etc/systemd/user/paimenos-osd.service

install_repo_file systemd/user/paimenos-menu.service /etc/systemd/user/paimenos-menu.service

install_repo_file systemd/user/paimenos-timer.service /etc/systemd/user/paimenos-timer.service

install_repo_file systemd/user/paimenos-media.service /etc/systemd/user/paimenos-media.service

# Sitzungsweit und unabhängig von Bluetooth/Controller; Mausbewegung zeigt ihn wieder.
install_repo_file systemd/user/paimenos-cursor.service /etc/systemd/user/paimenos-cursor.service

install_repo_file config/openbox/autostart "${OPENBOX_DIR}/autostart"

chmod 0755 "${OPENBOX_DIR}/autostart"
chmod 0644 "${OPENBOX_DIR}/rc.xml"

