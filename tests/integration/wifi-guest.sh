#!/bin/bash
# Run exclusively in the disposable Debian VM created by wifi-vm.sh.
set -euo pipefail
[[ -f /etc/paimenos-integration-vm ]] || { echo 'Disposable test VM required.' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
phase=$1
trap 'code=$?; echo "Guest test failed ($phase), line $LINENO" >&2; ip -br address; ip route; journalctl -b --no-pager -n 80 -u paimenos-test-ap -u paimenos-wifi-migration -u NetworkManager -u paimenos-packages -u paimenos-parent-web; exit "$code"' ERR
if [[ "$phase" == install ]]; then
    apt-get update
    apt-get install -y wpasupplicant ifupdown hostapd dnsmasq iw iptables isc-dhcp-client rfkill
    # Cloud images name these QEMU interfaces consistently after a reboot.
    [[ -d /sys/class/net/ens4 ]] || { ip -br link; exit 1; }
    install -m 0755 /source/tests/integration/wifi-ap.sh /usr/local/sbin/paimenos-test-ap
    cat > /etc/systemd/system/paimenos-test-ap.service <<'UNIT'
[Unit]
DefaultDependencies=no
After=local-fs.target sys-subsystem-net-devices-ens4.device
Requires=sys-subsystem-net-devices-ens4.device
Before=networking.service NetworkManager.service paimenos-wifi-migration.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/paimenos-test-ap
RemainAfterExit=yes
[Install]
WantedBy=networking.service NetworkManager.service
UNIT
    systemctl daemon-reload
    systemctl enable --now paimenos-test-ap.service
    cat > /etc/network/interfaces <<'CONF'
auto lo
iface lo inet loopback
auto wlan0
iface wlan0 inet dhcp
    wpa-ssid PaimenOS-Test
    wpa-psk test-password-only
CONF
    # The cloud management NIC must never become a second internet path.
    mkdir -p /etc/NetworkManager/conf.d
    cat > /etc/NetworkManager/conf.d/99-paimenos-test-management.conf <<'CONF'
[keyfile]
unmanaged-devices=interface-name:ens3;interface-name:ens4
CONF
    ifup wlan0
    # Keep the SSH management link, but force internet traffic through Wi-Fi.
    ip route del default dev ens3 || true
    ip -6 route del default dev ens3 || true
    printf 'nameserver 192.168.42.1\n' > /etc/resolv.conf
    ip route get 1.1.1.1 | grep -q 'dev wlan0'
    getent ahostsv4 deb.debian.org
    cp /etc/network/interfaces /root/interfaces.before
    # Interrupted installation, then the same standard --resume path.
    cp -a /source /root/PaimenOS
    sed -i '1a exit 77' /root/PaimenOS/installer/99-finish.sh
    cd /root/PaimenOS
    set +e
    PAIMENOS_PARENT_PIN=4815 PAIMENOS_APPS=13 PAIMENOS_APP_SOURCE=debian PAIMENOS_EMULATORS=none PAIMENOS_ENABLE_TLP=0 PAIMENOS_ENABLE_ZRAM=0 PAIMENOS_ENABLE_AUTO_UPDATES=0 PAIMENOS_ENABLE_APP_UPDATES=0 bash install.sh
    code=$?
    set -e
    [[ "$code" == 77 ]]
    [[ ! -f /etc/paimenos-laptop.installed ]]
    cmp /root/interfaces.before /etc/network/interfaces
    ip route get 1.1.1.1 | grep -q 'dev wlan0'
    cp /home/kids/.config/paimenos/settings.json /root/settings.before
    cp /source/installer/99-finish.sh installer/99-finish.sh
    PAIMENOS_APPS=13 PAIMENOS_APP_SOURCE=debian PAIMENOS_EMULATORS=none PAIMENOS_ENABLE_TLP=0 PAIMENOS_ENABLE_ZRAM=0 PAIMENOS_ENABLE_AUTO_UPDATES=0 PAIMENOS_ENABLE_APP_UPDATES=0 bash install.sh --resume
    [[ -f /etc/paimenos-laptop.installed ]]
    cmp /root/settings.before /home/kids/.config/paimenos/settings.json
    cmp /root/interfaces.before /etc/network/interfaces
    [[ -f /var/lib/paimenos/wifi-migration/pending.json ]]
    ip route get 1.1.1.1 | grep -q 'dev wlan0'
    getent ahostsv4 deb.debian.org
    apt-get update
    curl --fail --retry 60 --retry-delay 2 --retry-connrefused --max-time 10 http://127.0.0.1/login >/dev/null
elif [[ "$phase" == reboot ]]; then
    # Test the actual boot ordering, not a manual invoke of the migration.
    [[ -f /var/lib/paimenos/wifi-migration/completed.json ]]
    [[ ! -f /var/lib/paimenos/wifi-migration/pending.json ]]
    if [[ "${SECOND_BOOT:-0}" != 1 ]]; then systemctl is-active --quiet paimenos-wifi-migration.service; fi
    systemctl is-active --quiet NetworkManager.service
    for attempt in {1..60}; do
        state=$(LC_ALL=C nmcli -g GENERAL.STATE device show wlan0)
        [[ "${state%% *}" == 100 ]] && break
        sleep 1
    done
    [[ "${state%% *}" == 100 ]]
    ! ifquery wlan0 >/dev/null 2>&1
    nmcli -g GENERAL.CONNECTION device show wlan0 | grep -q 'PaimenOS Debian WLAN'
    ip route del default dev ens3 || true
    ip -6 route del default dev ens3 || true
    ip route get 1.1.1.1 | grep -q 'dev wlan0'
    getent ahostsv4 deb.debian.org
    apt-get update
    curl --fail --retry 60 --retry-delay 2 --retry-connrefused --max-time 10 http://127.0.0.1/login >/dev/null
    systemctl is-active --quiet paimenos-wifi.service
    echo 'PASS: fresh installation, interrupted/resumed setup and reboot Wi-Fi autoconnect'
else exit 2; fi
