# Architektur

## Programmcode und Daten

| Zielpfad | Zweck / Eigentümer |
|---|---|
| `/usr/local/lib/laurinos/releases/<Version>-<Hash>/` | Vollständiger Code-Stand, root-eigen |
| `/usr/local/lib/laurinos/current` | Atomar umgeschalteter Link auf den aktiven Stand |
| `/usr/local/lib/laurinos/previous` | Vorheriger Code-Stand für Rollback |
| `<Release>/app/laurinos/` | Installiertes Python-Paket aus `src/laurinos/` |
| `<Release>/assets/`, `<Release>/data/`, `<Release>/tools/` | Ressourcen und Programmhelfer |
| `/usr/local/bin/laurinos-*`, `/usr/local/sbin/laurinos-wlan-handoff` | Links auf Startprogramme des aktiven Releases; Flatpak-App-Starter werden vom Setup erzeugt |
| `/home/kids/.config/laurinos/` | `settings.json`, `apps.json`, Web-Sitzungsschlüssel; Eigentümer `kids` |
| `/home/kids/.local/state/laurinos/` | Protokolle, Sperren, Menüanforderungen und Medienstatus |
| `/home/kids/.local/share/laurinos/` | Icons, Controller-Profile, Emulator-Spiele und Spielstände |
| `/home/kids/.config/openbox/` | Nur Openbox-Konfiguration und Autostart |
| `/home/kids/.mozilla/laurinos-webapps/` | Browserprofile der Webapps |
| `/var/lib/laurinos/` | Systemzustand der Emulator-Installation und Liste verwalteter Flatpak-Apps |
| `/usr/local/share/laurinos/` | Heruntergeladene RetroArch-Profile und PSP-Zusatzdateien; kein Python-Programmcode |
| `/run/laurinos-*` | Dienst-Sockets und Wartungssperren |

Root-Dienste importieren keinen Programmcode aus dem Kinderverzeichnis. `run.py` startet das Paket aus seinem eigenen, aufgelösten Release-Verzeichnis. Der Aufruf mit `python3 -I` verhindert das Übernehmen eines fremden `PYTHONPATH` oder benutzereigener Python-Pakete. Laufende Prozesse behalten ihren geladenen Release; nach einem Update werden die Dienste neu gestartet.

## Installationsmodule

`install.sh` prüft das Zielsystem, fragt die PIN ab, sperrt parallele Wartung und lädt die Module in einer gemeinsamen Shell. Dadurch bleiben Paketlisten, App-Auswahl und Pfade zwischen den Schritten verfügbar.

| Modul | Aufgabe |
|---|---|
| `10-system.sh` | Python-Basis, erstes Code-Deployment, Emulator-Auswahl, Debian-Quellen und Basispakete |
| `20-hardware.sh` | Firmware, TLP, ZRAM, Sicherheitsupdates, Touchpad und Journald |
| `30-plymouth.sh` | Boot-Theme und Initramfs |
| `40-user.sh` | Benutzer, Gruppen, Verzeichnisse und Cursor |
| `50-browser.sh` | Polkit, Proxy/DNS, Firefox-Vorgaben und Webapp-Icons |
| `60-apps.sh` | App-Auswahl, Debian/Flatpak, Starter und App-Update-Timer |
| `70-defaults.sh` | Erste Einstellungen und App-Liste |
| `80-services.sh` | Emulatoren installieren, Systemdienste und deren Startprüfung |
| `network.sh` | WLAN an NetworkManager übergeben; vom Dienstmodul geladen |
| `90-desktop.sh` | LightDM, Openbox und systemd-Benutzerdienste |
| `99-finish.sh` | Datenrechte, Startziel und Abschlussmarkierung |

Die eigentliche Programmfunktion bleibt in Python-Dateien. Konfigurationen werden mit `install_repo_file` kopiert; zwei dynamische Dateien werden mit einem Renderer erzeugt, der nur benannte Platzhalter ersetzt und keinen Shell-Code auswertet.

## Paketgrenzen

Die vorhandenen v59-Funktionsbereiche wurden zunächst als eigenständige Python-Module übernommen und ihre Imports auf `laurinos.*` umgestellt. Das Menü bleibt ein größeres Modul; eine weitere Aufteilung in einzelne Widgets kann separat erfolgen. WLAN-Client und privilegierter WLAN-Dienst verwenden jetzt dieselbe root-eigene Datei. Der Emulator-Katalog liegt in JSON, die Eltern-Webansichten in HTML-Dateien.

`manifest.json` beschreibt die gemeinsam aktualisierbaren Komponenten. Jede installierte Version enthält `installed.json` mit Herkunftsversion und SHA-256 pro Komponentendatei. Nach einem Teilupdate können Komponenten unterschiedliche Versionen haben. Der Hash im Release-Verzeichnis bezeichnet die Kombination dieser Komponenten.
