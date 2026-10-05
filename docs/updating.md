# Updates und Releases

## Arbeiten im Repo

Quellcode direkt in `src/laurinos/` bearbeiten. Vor einer Freigabe:

```bash
python3 tools/build-manifest.py
python3 -B tools/check.py
python3 tools/build-release.py
```

`VERSION` ist die Release-Version. `manifest.json` muss denselben Wert enthalten. `build-manifest.py` aktualisiert das Inventar, wenn Dateien oder Komponenten hinzugefügt oder entfernt werden. Beim Ändern einer bestehenden Datei muss keine Prüfsumme von Hand gepflegt werden: Das Deployment berechnet sie für die Versionsaufzeichnung.

Das Release-Werkzeug erzeugt ein Archiv und eine SHA-256-Datei in `dist/`. Eine Prüfsumme belegt die Integrität des Archivs, ersetzt aber keine vertrauenswürdige Quelle oder Signatur. Ein automatischer Download oder Remote-Updater ist in dieser Basis nicht enthalten.

## Auf dem Gerät aktualisieren

Archiv aus einer vertrauenswürdigen Quelle kopieren und entpacken. Alle folgenden Befehle aus dem neuen Projektordner ausführen:

```bash
bash update.sh --check
sudo bash update.sh
```

Apps und Spiele vor dem Update schließen. Ein aktives Kinder-Menü und die Gerätedienste werden zur Übernahme des Codes neu gestartet. Ohne laufende Benutzersitzung startet der neue Sitzungscode bei der nächsten Anmeldung.

`update.sh` installiert keine APT-/Flatpak-Pakete, überschreibt keine Eltern-Daten und verändert keine WLAN-Profile, Firefox-Profile, TLP-Regeln oder andere Systemkonfigurationen. Solche Änderungen müssen als gesonderte Einrichtungsschritte dokumentiert werden. Die Komponente `services` installiert die im Release enthaltenen LaurinOS-Systemd-Units neu.

## Teilupdates

```bash
bash update.sh --list
sudo bash update.sh --component controller
sudo bash update.sh --component backend --component network
```

| Komponente | Inhalt |
|---|---|
| `shared` | Gemeinsame Pfade, Datenzugriff, Bilder, Diagnose, Webapp-CSS, OSD-Zustand und Launcher |
| `desktop` | Menü, lokale Elternoberfläche, Timer, Medien und Overlays |
| `controller` | Gerätefilter, Controller-Reader und Belegungsprofile |
| `network` | WLAN, Bluetooth, lokale Dialoge und Netzwerkstatus |
| `emulators` | Katalog, Spieleverwaltung, Installationsdienst und Client |
| `backend` | Gemeinsame Elternverwaltung, Webserver und HTML-Ansichten |
| `cli` | Starter, gemeinsame Flatpak-Startlogik und Hardware-Befehle |
| `tools` | Installations-/Wartungshelfer als Release-Dateien |
| `services` | System- und Benutzerdienste |

Ein Teilupdate kopiert nur gewählte Bereiche in eine Kopie des aktiven Releases. Die restlichen Dateien werden aus dem installierten Stand übernommen. Es gibt keine automatische Abhängigkeitsauflösung: Bei einer Änderung einer Schnittstelle zwischen Komponenten alle betroffenen Bereiche gemeinsam aktualisieren. Bei inkompatiblen Paketänderungen `runtime_api` im Manifest und `API` in `tools/deploy.py` erhöhen; dann ist ein vollständiges Update erforderlich.

## Wechsel und Rollback

1. Manifest, Pfade und Python-Syntax prüfen.
2. Laufende Emulator-Paketinstallation bzw. parallele Wartung ausschließen.
3. Neuen Stand in einem Staging-Verzeichnis aufbauen; vorherige Dateien ausgewählter Komponenten entfernen.
4. Ressourcen und gemeinsame Python-Imports prüfen.
5. Den aktiven Link atomar auf den fertigen Code-Stand umschalten.
6. Gegebenenfalls Systemd-Units kopieren, Dienste neu starten und deren aktiven Zustand prüfen.
7. Bei einem erkannten Startfehler den bisherigen Code und gegebenenfalls die bisherigen Units wieder aktivieren und erneut starten.

Die Aktivierung der Code-Version ist atomar. Dienstneustarts und das Kopieren von Systemd-Units sind keine atomare Gesamttransaktion. Ein Stromausfall während dieser Schritte kann manuelle Wiederherstellung erfordern. Ein aktiver Dienst bedeutet außerdem nicht, dass jede Hardwarefunktion erfolgreich getestet wurde.

Manuell zurückkehren:

```bash
sudo bash update.sh --rollback
```

Das betrifft Code und LaurinOS-Units. Spielstände, Eltern-Einstellungen, heruntergeladene Cores, BIOS-Dateien, App-Pakete und sonstige Daten werden nicht zurückgesetzt. Ein Code-Rollback ist keine Datensicherung.

Versionen anzeigen:

```bash
cat /usr/local/lib/laurinos/current/installed.json
```

Frühere Releases bleiben für Fehlersuche erhalten. Eine automatische Löschstrategie ist noch nicht enthalten.
