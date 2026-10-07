#!/bin/bash
# WLAN dauerhaft und zur Laufzeit an NetworkManager übergeben.
paimenos_configure_wifi() {
    local selected="${1:-}" devices device kind found=false policy temp backup state code failed=false
    local reload_needed=false attempt config_dir
    if ! command -v nmcli >/dev/null 2>&1; then
        echo "FEHLER: NetworkManager / nmcli fehlt. Bitte zuerst PaimenOS v43 oder neuer installieren." >&2
        return 1
    fi
    systemctl enable --now NetworkManager.service || return 1
    devices=$(LC_ALL=C nmcli --terse --escape no --fields DEVICE,TYPE device status) || return 1
    if [[ -n "$selected" ]]; then
        while IFS=: read -r device kind; do
            if [[ "$device" == "$selected" && "$kind" == wifi ]]; then found=true; fi
        done <<< "$devices"
        if [[ "$found" != true ]]; then
            echo "FEHLER: Der angegebene WLAN-Adapter wurde nicht gefunden: $selected" >&2
            return 1
        fi
    fi
    config_dir=/etc/NetworkManager/conf.d
    policy="$config_dir/99-paimenos-wifi-managed.conf"
    if [[ -L "$policy" || ( -e "$policy" && ! -f "$policy" ) ]]; then
        echo "FEHLER: WLAN-Konfigurationsdatei ist kein reguläres Ziel." >&2
        return 1
    fi
    install -d -o root -g root -m 0755 "$config_dir" || return 1
    temp=$(mktemp "$config_dir/.paimenos-wifi.XXXXXX") || return 1
    if ! install_repo_file config/networkmanager/99-paimenos-wifi-managed.conf "$temp"
    then
        rm -f -- "$temp"; return 1
    fi
    if [[ -f "$policy" ]] && ! cmp -s "$temp" "$policy"; then
        backup=$(mktemp -d /var/backups/paimenos-wifi-manage.XXXXXX) || { rm -f -- "$temp"; return 1; }
        chmod 0700 "$backup" || { rm -f -- "$temp"; return 1; }
        cp -a -- "$policy" "$backup/" || { rm -f -- "$temp"; return 1; }
        echo "Bisherige WLAN-Verwaltungsregel gesichert: $backup"
    fi
    if ! install -o root -g root -m 0644 "$temp" "$temp".ready; then
        rm -f -- "$temp" "$temp".ready; return 1
    fi
    rm -f -- "$temp"
    if ! mv -Tf -- "$temp".ready "$policy"; then
        rm -f -- "$temp".ready; return 1
    fi
    # Konfiguration anwenden, ohne bereits aktive Verbindungen zu beenden.
    LC_ALL=C nmcli --wait 10 general reload conf || return 1
    while IFS=: read -r device kind; do
        [[ "$kind" == wifi ]] || continue
        [[ -z "$selected" || "$device" == "$selected" ]] || continue
        LC_ALL=C nmcli --wait 10 device set "$device" managed yes || reload_needed=true
        state=$(LC_ALL=C nmcli --get-values GENERAL.STATE device show "$device") || { reload_needed=true; continue; }
        code=${state%% *}
        [[ "$code" =~ ^[0-9]+$ && "$code" != 10 ]] || reload_needed=true
    done <<< "$devices"
    if [[ "$reload_needed" == true ]]; then
        echo "HINWEIS: WLAN-Freigabe wird erneut geprüft; aktive Netzwerkverbindungen bleiben erhalten." >&2
    fi
    while IFS=: read -r device kind; do
        [[ "$kind" == wifi ]] || continue
        [[ -z "$selected" || "$device" == "$selected" ]] || continue
        # Initialisierung läuft nach Dienststart teilweise noch asynchron.
        code=10
        for attempt in {1..16}; do
            if LC_ALL=C nmcli --wait 10 device set "$device" managed yes && state=$(LC_ALL=C nmcli --get-values GENERAL.STATE device show "$device"); then
                code=${state%% *}
                if [[ "$code" =~ ^[0-9]+$ && "$code" != 10 ]]; then break; fi
            fi
            sleep 0.25
        done
        if [[ ! "$code" =~ ^[0-9]+$ || "$code" == 10 ]]; then
            echo "FEHLER: $device ist weiterhin nicht verwaltet. Status: $state" >&2
            echo "Diagnosebefehl (nur die folgende Zeile ausführen):" >&2
            echo "nmcli -f GENERAL device show $device" >&2
            failed=true
        else
            echo "WLAN-Adapter $device wird jetzt von NetworkManager verwaltet."
        fi
    done <<< "$devices"
    if [[ "$failed" == true ]]; then
        echo "WLAN weiterhin gesperrt. Verwaltungsregel wurde gespeichert; die Ursache benötigt weitere Diagnose." >&2
        return 1
    fi
}

PAIMENOS_WIFI_READY=false
# Bestehende Debian-Profile zuerst übernehmen, bevor eine allgemeine managed-
# Regel installiert wird. Auch networking.service nutzt ifupdown, ohne dass
# ifup@<Adapter>.service aktiv sein muss.
systemctl enable --now NetworkManager.service
devices=$(LC_ALL=C nmcli --terse --escape no --fields DEVICE,TYPE device status) || exit 1
while IFS=: read -r device kind; do
    [[ "$kind" == wifi ]] || continue
    if systemctl is-active --quiet "ifup@$device.service" ||
        { command -v ifquery >/dev/null 2>&1 && ifquery "$device" >/dev/null 2>&1; }; then
        if ! /bin/bash /usr/local/sbin/paimenos-wlan-handoff "$device"; then
            echo "FEHLER: WLAN-Übergabe für $device fehlgeschlagen. Setup angehalten; nach Prüfung mit --resume fortsetzen." >&2
            exit 1
        fi
    fi
done <<< "$devices"
if paimenos_configure_wifi; then
    PAIMENOS_WIFI_READY=true
else
    echo "FEHLER: WLAN-Freigabe fehlgeschlagen. Setup angehalten; aktive Verbindungen wurden nicht neu gestartet." >&2
    exit 1
fi
systemctl restart paimenos-wifi.service
if ! systemctl is-active --quiet paimenos-wifi.service; then
    echo "FEHLER: WLAN-Verwaltung nicht gestartet. Siehe systemctl status paimenos-wifi.service" >&2
    exit 1
fi
