#!/bin/bash
# Wird von install.sh in einer gemeinsamen Shell geladen.
# 3. Plymouth Boot- & Shutdown Screen
# ---------------------------------------------------------------------------
echo "Plymouth Boot & Shutdown Screen konfigurieren ..."

/usr/bin/python3 /usr/local/lib/paimenos/current/tools/install-paimenos-plymouth.py
plymouth-set-default-theme paimenos
if [[ "$(plymouth-set-default-theme)" != "paimenos" ]]; then
    echo "FEHLER: PaimenOS konnte nicht als Plymouth-Theme aktiviert werden." >&2
    exit 1
fi

if [[ -f /etc/default/grub ]]; then
    /usr/bin/python3 /usr/local/lib/paimenos/current/tools/install-paimenos-plymouth.py --grub
    update-grub
fi
# Auch bereits vorhandene ältere Kernel erhalten das neue Theme.
# Ein Fehler wird sichtbar gemeldet, damit das Setup keinen falschen Erfolg meldet.
update-initramfs -u -k all
echo "  ✓ Plymouth-Theme PaimenOS ist für den nächsten Systemstart aktiviert."
