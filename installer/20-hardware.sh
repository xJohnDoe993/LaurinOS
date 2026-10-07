#!/bin/bash
# Wird von install.sh in einer gemeinsamen Shell geladen.
# 2a. Laptop-Betrieb, Arbeitsspeicher und Wartung (Debian 12/13)
# Eigene /etc/tlp.conf und andere ZRAM-Verwalter bleiben erhalten.
# ---------------------------------------------------------------------------
echo "Laptop-Werkzeuge und sichere Energiesparregeln ..."

package_installed() {
    [[ "$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null || true)" == "install ok installed" ]]
}

install_available_firmware() {
    local package candidate
    local -a available=()
    for package in "$@"; do
        candidate=$(LC_ALL=C apt-cache policy "$package" 2>/dev/null | awk '/Candidate:/ {print $2; exit}')
        if [[ -n "$candidate" && "$candidate" != "(none)" ]]; then
            available+=("$package")
        else
            echo "Hinweis: ${package} nicht verfügbar; ggf. Debian non-free-firmware aktivieren." >&2
        fi
    done
    if (( ${#available[@]} )); then
        apt-get install -y --no-install-recommends "${available[@]}" || \
            echo "Hinweis: optionale Firmware konnte nicht vollständig installiert werden." >&2
    fi
}

apt-get install -y --no-install-recommends \
    upower acpi rfkill ethtool v4l-utils lm-sensors smartmontools fwupd \
    unattended-upgrades ca-certificates xserver-xorg-input-libinput

# Firmware nur aus bereits eingerichteten Debian-Paketquellen beziehen.
install_available_firmware firmware-misc-nonfree firmware-iwlwifi firmware-realtek firmware-atheros
case "$(awk '/vendor_id/ {print $3; exit}' /proc/cpuinfo)" in
    GenuineIntel) install_available_firmware intel-microcode ;;
    AuthenticAMD) install_available_firmware amd64-microcode ;;
esac

if [[ "$PAIMENOS_ENABLE_TLP" == 1 ]]; then
    mkdir -p /etc/tlp.d
    install_repo_file config/tlp/01-paimenos.conf /etc/tlp.d/01-paimenos.conf
    # Regeln vor Installation schreiben: auch ein Start durch das Paket nutzt sie.
    # Debian löst den Paketkonflikt mit power-profiles-daemon selbst auf.
    apt-get install -y --no-install-recommends tlp tlp-rdw
    systemctl enable tlp.service
    # Bereits aktive fremde Optimierer dürfen die TLP-Regeln nicht überschreiben.
    for power_service in auto-cpufreq.service tuned.service; do
        if systemctl is-active --quiet "$power_service"; then
            echo "Hinweis: ${power_service} wird zugunsten von TLP deaktiviert."
            systemctl disable --now "$power_service"
        fi
    done
    # Einstellungen werden beim folgenden Neustart angewendet. Kein tlp start
    # während Kamera, Medien oder eine bestehende Kindersitzung aktiv sein könnten.
fi

if [[ "$PAIMENOS_ENABLE_ZRAM" == 1 ]]; then
    ZRAM_OTHER_MANAGER=false
    if package_installed systemd-zram-generator || package_installed zram-config || \
        [[ -f /etc/systemd/zram-generator.conf || -d /etc/systemd/zram-generator.conf.d ]] || \
        [[ -f /usr/lib/systemd/zram-generator.conf || -d /usr/lib/systemd/zram-generator.conf.d ]]; then
        ZRAM_OTHER_MANAGER=true
    elif compgen -G '/sys/block/zram*' >/dev/null && ! package_installed zram-tools; then
        ZRAM_OTHER_MANAGER=true
    fi
    if [[ "$ZRAM_OTHER_MANAGER" == true ]]; then
        echo "Hinweis: vorhandene ZRAM-Verwaltung wird beibehalten."
    else
        apt-get install -y --no-install-recommends zram-tools
        # Paketinstallation kann den Dienst bereits starten. Deshalb keinen
        # laufenden Swap abschalten/neustarten; neue Werte gelten ab Neustart.
        if [[ ! -f /etc/default/zramswap ]] || \
            grep -q '^# PaimenOS managed ZRAM$' /etc/default/zramswap || \
            ! grep -Eq '^[[:space:]]*[^#[:space:]]' /etc/default/zramswap; then
            mkdir -p /etc/default
            install_repo_file config/zram/zramswap /etc/default/zramswap
        else
            echo "Hinweis: eigene ZRAM-Konfiguration wird beibehalten."
        fi
        systemctl enable zramswap.service
    fi
fi

echo "Sicherheitsupdates, SSD-Wartung und Eingabegeräte ..."
if [[ "$PAIMENOS_ENABLE_AUTO_UPDATES" == 1 ]]; then
    mkdir -p /etc/apt/apt.conf.d
    install_repo_file config/apt/90-paimenos-updates /etc/apt/apt.conf.d/90-paimenos-updates
    systemctl enable apt-daily.timer apt-daily-upgrade.timer
fi

# Wöchentliches TRIM über die Debian-Unit, ohne permanente discard-Mountoption.
systemctl enable fstrim.timer
mkdir -p /etc/systemd/journald.conf.d /etc/X11/xorg.conf.d /usr/local/share/paimenos
install_repo_file config/journald/10-paimenos.conf /etc/systemd/journald.conf.d/10-paimenos.conf
install_repo_file config/xorg/40-paimenos-touchpad.conf /etc/X11/xorg.conf.d/40-paimenos-touchpad.conf
install_repo_file docs/laptop-setup.txt /usr/local/share/paimenos/laptop-setup.txt

# Verifizierung kritischer Python-Pakete
/usr/bin/python3 -c "import flask, dbus, evdev; from gi.repository import GLib; from PyQt5.QtWidgets import QApplication" >/dev/null 2>&1 || {
    echo "FEHLER: Flask, PyQt5 oder die Bluetooth-/Controller-Python-Pakete fehlen." >&2
    exit 1
}

