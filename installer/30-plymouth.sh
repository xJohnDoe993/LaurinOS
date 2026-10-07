#!/bin/bash
# Wird von install.sh in einer gemeinsamen Shell geladen.
# 3. Plymouth Boot- & Shutdown Screen
# ---------------------------------------------------------------------------
echo "Plymouth Boot & Shutdown Screen konfigurieren ..."

mkdir -p /usr/local/share/paimenos
/usr/bin/python3 /usr/local/lib/paimenos/current/tools/install-pixels-plymouth.py
plymouth-set-default-theme pixels
if [[ "$(plymouth-set-default-theme)" != "pixels" ]]; then
    echo "FEHLER: Pixels konnte nicht als Plymouth-Theme aktiviert werden." >&2
    exit 1
fi

if [[ -f /etc/default/grub ]]; then
    /usr/bin/python3 /usr/local/lib/paimenos/current/tools/install-pixels-plymouth.py --grub
    update-grub
fi
# Auch bereits vorhandene ältere Kernel erhalten das neue Theme.
# Ein Fehler wird sichtbar gemeldet, damit das Setup keinen falschen Erfolg meldet.
update-initramfs -u -k all
echo "  ✓ Plymouth-Theme Pixels ist für den nächsten Systemstart aktiviert."

