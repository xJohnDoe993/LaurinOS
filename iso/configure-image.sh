#!/bin/bash
# Only invoked inside the live-build chroot, never on the host.
set -Eeuo pipefail
[[ $EUID == 0 && -f /run/paimenos-live-build ]] || exit 1
export REPO_DIR=/opt/paimenos-source PAIMENOS_IMAGE_BUILD=1
export PAIMENOS_APPS="${PAIMENOS_APPS:-2 8 9 11}" PAIMENOS_APP_SOURCE=debian
export PAIMENOS_EMULATORS=none PAIMENOS_REBOOT=0
# Generated only for the existing initializer; removed before packaging.
PAIMENOS_PARENT_PIN=$(/usr/bin/python3 -c 'import secrets; print("".join(str(secrets.randbelow(10)) for _ in range(12)))')
# Enable units on disk without trying to talk to a running system manager.
systemctl() {
    case "${1:-}" in
        enable|disable|set-default)
            local -a args=()
            local arg
            for arg in "$@"; do [[ $arg == --now ]] || args+=("$arg"); done
            /usr/bin/systemctl "${args[@]}" ;;
        is-active) return 1 ;;
        daemon-reload|restart|stop|start) return 0 ;;
        *) echo "Unsupported image-build systemctl operation: $*" >&2; return 1 ;;
    esac
}
udevadm() { :; } # No device events in the build chroot.
source "$REPO_DIR/installer/common.sh"
source "$REPO_DIR/installer/environment.sh"
for module in 10-system 20-hardware 30-plymouth 40-user 50-browser 60-apps 70-defaults 80-services 90-desktop 99-finish; do
    source "$REPO_DIR/installer/$module.sh"
done
apt-get install -y --no-install-recommends sudo intel-microcode amd64-microcode
install -D -m 0755 "$REPO_DIR/iso/first-boot.py" /usr/local/sbin/paimenos-first-boot
install -d -m 0700 /var/lib/paimenos/iso
/usr/bin/python3 - <<'PY'
import json
from pathlib import Path
settings = json.loads(Path('/home/kids/.config/paimenos/settings.json').read_text())
settings.pop('pin', None)
p = Path('/var/lib/paimenos/iso/settings.json')
p.write_text(json.dumps(settings))
p.chmod(0o600)
PY
/usr/local/sbin/paimenos-first-boot --reset
printf '%s\n' 'kids ALL=(root) NOPASSWD: /usr/local/sbin/paimenos-first-boot ""' > /etc/sudoers.d/paimenos-first-boot
chmod 0440 /etc/sudoers.d/paimenos-first-boot
visudo -cf /etc/sudoers.d/paimenos-first-boot
# No parent endpoints before a device-specific PIN exists.
for unit in paimenos-parent-web paimenos-updates; do
    mkdir -p "/etc/systemd/system/$unit.service.d"
    printf '[Unit]\nConditionPathExists=!/var/lib/paimenos/iso/pending\n' > "/etc/systemd/system/$unit.service.d/iso.conf"
done
# Blocking welcome dialog before the original child session starts.
/usr/bin/python3 - <<'PY'
from pathlib import Path
p = Path('/home/kids/.config/openbox/autostart')
s = p.read_text()
gate = '''
while [ -e /var/lib/paimenos/iso/pending ]; do
    xterm -fa Monospace -fs 14 -T 'PaimenOS – Ersteinrichtung' -e sudo /usr/local/sbin/paimenos-first-boot
    sleep 1
done
'''
p.write_text(s.replace('# DISPLAY und Xauthority', gate + '\n# DISPLAY und Xauthority'))
PY
# The live system must not grant the child broad passwordless sudo privileges.
rm -f /etc/sudoers.d/live
# live-config sudo component is disabled in boot parameters too.
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id /etc/ssh/ssh_host_*
rm -f /run/paimenos-live-build
rm -rf /opt/paimenos-source
