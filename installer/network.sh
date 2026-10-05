#!/bin/bash
# WLAN dauerhaft und zur Laufzeit an NetworkManager übergeben.
laurinos_configure_wifi() {
    local selected="${1:-}" devices device kind found=false policy temp backup state code failed=false
    local ifaces legacy_empty=false reload_needed=false attempt config_dir
    if ! command -v nmcli >/dev/null 2>&1; then
        echo "FEHLER: NetworkManager / nmcli fehlt. Bitte zuerst LaurinOS v43 oder neuer installieren." >&2
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
    # Bei ausschließlich Loopback kann das ifupdown-Plugin sicher freigegeben
    # werden. Es kann ältere Geräte-Sperren bis zum Dienstneustart behalten.
    if command -v ifquery >/dev/null 2>&1; then
        if ifaces=$(ifquery --list 2>/dev/null); then
            legacy_empty=true
            while IFS= read -r device; do
                [[ -z "$device" || "$device" == lo ]] || legacy_empty=false
            done <<< "$ifaces"
        fi
    fi
    config_dir=/etc/NetworkManager/conf.d
    policy="$config_dir/99-laurinos-wifi-managed.conf"
    if [[ -L "$policy" || ( -e "$policy" && ! -f "$policy" ) ]]; then
        echo "FEHLER: WLAN-Konfigurationsdatei ist kein reguläres Ziel." >&2
        return 1
    fi
    install -d -o root -g root -m 0755 "$config_dir" || return 1
    temp=$(mktemp "$config_dir/.laurinos-wifi.XXXXXX") || return 1
    if ! install_repo_file config/networkmanager/99-laurinos-wifi-managed.conf "$temp"
    then
        rm -f -- "$temp"; return 1
    fi
    if [[ "$legacy_empty" == true ]]; then
        printf '\n[ifupdown]\nmanaged=true\n' >> "$temp" || { rm -f -- "$temp"; return 1; }
    fi
    if [[ -f "$policy" ]] && ! cmp -s "$temp" "$policy"; then
        backup=$(mktemp -d /var/backups/laurinos-wifi-manage.XXXXXX) || { rm -f -- "$temp"; return 1; }
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
    # Erst ohne Neustart anwenden. Strikte Plugin-Sperren ggf. neu initialisieren.
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
        echo "NetworkManager wird zur Aufhebung der Plugin-Sperre neu gestartet; Netzwerkverbindungen können kurz unterbrochen werden."
        systemctl restart NetworkManager.service || return 1
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

LAURINOS_WIFI_READY=false
if laurinos_configure_wifi; then
    LAURINOS_WIFI_READY=true
else
    echo "HINWEIS: WLAN noch nicht verfügbar. Das übrige LaurinOS-Setup wird abgeschlossen." >&2
fi

# Bestehende ifupdown-WLAN-Verwaltung gezielt übernehmen (v60 / 0.60.0).
# Startprogramm ist bereits als root-verwalteter Release-Link installiert.
while IFS=: read -r device kind; do
    if [[ "$kind" == wifi ]] && systemctl is-active --quiet "ifup@$device.service"; then
        if /bin/bash /usr/local/sbin/laurinos-wlan-handoff "$device"; then
            LAURINOS_WIFI_READY=true
        else
            echo "HINWEIS: WLAN-Übergabe für $device fehlgeschlagen; übriges Setup wird abgeschlossen." >&2
        fi
    fi
done < <(LC_ALL=C nmcli --terse --escape no --fields DEVICE,TYPE device status)
systemctl restart laurinos-wifi.service
if ! systemctl is-active --quiet laurinos-wifi.service; then
    echo "FEHLER: WLAN-Verwaltung nicht gestartet. Siehe systemctl status laurinos-wifi.service" >&2
    exit 1
fi
