# Installation

## Zielsystem

Ein frisches Debian 12 (bookworm) oder Debian 13 (trixie) mit Internetzugang, administrativem Benutzer und funktionierendem APT. Der Installer ist für einen dedizierten Kinder-Laptop vorgesehen: Er richtet LightDM-Autologin für `kids`, Openbox, Grafik, Audio, Familien-DNS, Proxy, Paketquellen der eigenen Debian-Version, Energiesparen und Gerätedienste ein.

Das frühere monolithische Setup wird nicht mehr benötigt. `install.sh` lädt die Module aus `installer/`; Python-Code und Konfigurationsdateien stehen als eigene Dateien im Projekt. Das gesamte Projekt muss deshalb lokal verfügbar sein. Ein einzelnes aus einer Pipe gestartetes Setup-Skript genügt nicht mehr.

## Ablauf

1. Projekt entpacken und in den Ordner `LaurinOS` wechseln.
2. `sudo bash install.sh` ausführen.
3. Neue Eltern-PIN mit 4 bis 12 Ziffern festlegen und wiederholen.
4. Emulatoren wählen. `empfohlen` entspricht der Auswahl aus v59; N64 und PSP bleiben optional.
5. Native Apps und Flathub oder Debian als Quelle wählen.
6. Abschlussmeldung und gegebenenfalls offene WLAN-Diagnose beachten.
7. `sudo reboot` ausführen.

Das Setup startet das Gerät standardmäßig nicht automatisch neu. Ein WLAN-Problem wird weiterhin sichtbar gemeldet, ohne die übrige Installation unnötig zu blockieren.

Eine unvollständige modulare Installation lässt sich mit `sudo bash install.sh --resume` fortsetzen. Bereits vorhandene Eltern-Einstellungen werden dabei erhalten. Für abgeschlossene modulare Installationen ist `update.sh` zuständig. Eine v59-Installation wird weder beim Setup noch beim Update übernommen.

## Schalter

Umgebungsvariablen mit `sudo env` übergeben, wenn `sudo` die Umgebung bereinigt:

```bash
sudo env LAURINOS_APPS="2 6 9 11" \
  LAURINOS_APP_SOURCE=debian \
  LAURINOS_EMULATORS=empfohlen \
  bash install.sh
```

| Variable | Werte / Standard |
|---|---|
| `LAURINOS_APPS` | Leer: interaktive Auswahl. Nummern aus dem Setup; `13`: keine nativen Apps |
| `LAURINOS_APP_SOURCE` | Leer: interaktiv; `flathub` oder `debian` |
| `LAURINOS_EMULATORS` | Leer: interaktiv; `empfohlen`, `all`, `none` oder IDs mit Kommas |
| `LAURINOS_ENABLE_TLP` | `1` / `0`, Standard `1` |
| `LAURINOS_ENABLE_ZRAM` | `1` / `0`, Standard `1` |
| `LAURINOS_ENABLE_AUTO_UPDATES` | Debian-Sicherheitsupdates, Standard `1` |
| `LAURINOS_ENABLE_APP_UPDATES` | Verwaltete Flatpak-Apps, Standard wie Auto-Updates |
| `LAURINOS_REBOOT` | `1`: am Ende automatisch neu starten; Standard `0` |
| `LAURINOS_PARENT_PIN` | Für automatisierte Installationen; sonst verdeckte Eingabe. Keine feste Standard-PIN |

Die Emulator-IDs stehen in `data/emulator-catalog.json`. Das Setup bzw. Backend installiert Emulator-Software; ROMs und erforderliche BIOS-Dateien bringt man selbst mit.

## Nach dem Neustart

Der Elternbereich ist lokal über das Menü sowie im Netz über `http://<Geräte-IP>/` erreichbar. Erst den Gerätecheck in `docs/device-validation.md` durchgehen. Falls das Setup abgebrochen wurde, Dienste nicht als erfolgreich eingerichtet betrachten: Die Abschlussmarkierung wird erst ganz am Ende geschrieben.
