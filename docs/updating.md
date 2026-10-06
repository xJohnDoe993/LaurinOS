# Updates und Releases

## GitHub als Update-Quelle

Das Eltern-Webbackend verwendet fest [xJohnDoe993/LaurinOS](https://github.com/xJohnDoe993/LaurinOS/releases). Der root-Dienst `laurinos-updates.service` prüft beim Start und danach alle sechs Stunden das neueste veröffentlichte stabile Release. Entwürfe und Pre-Releases werden nicht angeboten. Die Version muss `vMAJOR.MINOR.PATCH` heißen, beispielsweise `v0.61.0`; intern steht `0.61.0` in `VERSION` und Manifest. Versionsnummern werden numerisch verglichen. Ein installiertes neueres Modul wird nicht durch ein älteres Release ersetzt.

Angemeldete Eltern sehen einen Hinweis auf jeder Backend-Seite und können unter **Updates** Release-Notizen lesen, manuell prüfen und ein Update starten. Die Prüfung läuft im Hintergrund. Ohne Internet bleibt die letzte erfolgreiche Prüfung sichtbar, zusammen mit dem Fehler; der Updater installiert nichts automatisch. Manuelle Prüfungen werden auf höchstens eine pro Minute begrenzt.

Der Download und die Aktivierung laufen als eigener transienter Systemd-Dienst `laurinos-update-job.service`. Dadurch überlebt der Auftrag Neustarts von Webbackend und Prüfdienst. Der Auftrag wird dauerhaft gespeichert. Wird der Rechner währenddessen ausgeschaltet, startet der Auftrag nicht automatisch erneut; der Backend-Status weist auf die Unterbrechung hin.

Das Release benötigt zwei hochgeladene Assets:

| Asset für Version 0.62.0 | Inhalt |
|---|---|
| `LaurinOS-0.62.0.zip` | Mit `tools/build-release.py` erstelltes Projektarchiv |
| `LaurinOS-0.62.0.zip.sha256` | SHA-256 und Dateiname des Archivs |

GitHubs automatisch erzeugte „Source code“-Archive ersetzen diese Assets nicht. Die früheren Dateinamen `LaurinOS-v60-modular-<Version>.zip` und ihre Prüfsummendatei werden ebenfalls erkannt. ZIP-Download höchstens 50 MiB; entpackt höchstens 100 MiB und 5.000 Einträge. Diese Grenzen müssen angepasst werden, falls LaurinOS später größere Release-Pakete benötigt.

## GitHub-Release Schritt für Schritt

1. Änderungen prüfen und in den Hauptbranch übernehmen. `VERSION`, `src/laurinos/__init__.py` und `pyproject.toml` auf dieselbe neue Version setzen, für diesen Stand `0.62.0`.
2. Aus dem Projektordner das Inventar aktualisieren und das Release bauen:

   ```bash
   python3 tools/build-manifest.py
   python3 tools/build-release.py
   ```

   Der Build führt die Offline-Prüfungen und Tests aus. Optional installiertes Flask aktiviert zusätzlich die Backend-Integrationstests. Bei einem Fehler kein Release veröffentlichen.

3. Falls das Manifest oder Versionsdateien geändert wurden, diese Änderungen committen und nach GitHub pushen:

   ```bash
   git add VERSION pyproject.toml src/laurinos/__init__.py manifest.json
   git commit -m "Prepare release 0.62.0"
   git push origin main
   ```

   Wenn diese Dateien bereits im Hauptbranch committed sind, entfällt der zusätzliche Commit. `dist/` bleibt bewusst außerhalb von Git.

4. Auf [GitHub → Releases](https://github.com/xJohnDoe993/LaurinOS/releases) **Draft a new release** öffnen.
5. Tag `v0.62.0` erstellen und als Ziel den geprüften Commit im Hauptbranch wählen. Als Titel beispielsweise `LaurinOS 0.62.0 – Family-DNS` verwenden.
6. Release-Notizen schreiben. Neue Funktionen, nötige Einrichtungsschritte und bekannte Einschränkungen nennen. Für 0.62.0 auf die separate Übernahme der Family-DNS-Systemkonfiguration auf bestehenden Geräten hinweisen.
7. Beide Dateien aus `dist/` als Assets hochladen: `LaurinOS-0.62.0.zip` **und** `LaurinOS-0.62.0.zip.sha256`. Upload vollständig abwarten.
8. Auf einem Testgerät die Installation bzw. das manuelle Update und die [Geräteprüfung](device-validation.md) ausführen. Bis dahin das Release als Entwurf speichern; alternativ für Tests ein Pre-Release verwenden, das der stabile Updater ignoriert.
9. Erst nach dem Gerätetest **Publish release** wählen und das Release als neuestes stabiles Release markieren. **Pre-release** muss ausgeschaltet sein.
10. Im Elternbackend **Updates → Nach Updates suchen** prüfen. Eine vorhandene identische Version wird nicht erneut angeboten. Für den nächsten echten Update-Test eine höhere Version veröffentlichen.

Für spätere Releases diese Schritte mit einer höheren Versionsnummer wiederholen, beispielsweise `0.63.0` / `v0.63.0`. Veröffentlichte Tags und Assets nicht nachträglich ersetzen; Korrekturen bekommen eine neue Versionsnummer. Der Installationsauftrag prüft vor dem Download erneut, ob die angebotenen Assets unverändert sind.

## Einmalige Einrichtung auf 0.60.0

Das geprüfte 0.61.0-Release herunterladen, die Prüfsumme vergleichen, entpacken und aus dem neuen `LaurinOS`-Ordner ausführen:

```bash
sha256sum -c LaurinOS-0.61.0.zip.sha256
unzip LaurinOS-0.61.0.zip
cd LaurinOS
bash update.sh --check
sudo bash update.sh
sudo systemctl status laurinos-updates.service --no-pager
```

Die ersten zwei Befehle laufen im Downloadordner, bevor in den Projektordner gewechselt wird. Dieses vollständige Update aktiviert auch den neuen Prüfdienst. Danach das Backend neu laden; weitere Code-Releases lassen sich dort installieren. Eine frische 0.61.0-Installation richtet den Dienst bereits im Setup ein.

## Family-DNS auf bestehenden Geräten ab 0.62.0

Neuinstallationen übernehmen die globale Routing-Domain `~.` automatisch. Ein Code-Update verändert die DNS-Systemkonfiguration nicht. Nach dem Update daher einmalig aus dem entpackten 0.62.0-Projektordner ausführen:

```bash
sudo python3 tools/configure-dns.py family config/resolved/laurinos-family-dns.conf
resolvectl status
timeout 10 getent ahostsv4 deb.debian.org
```

Bei Erfolg steht unter `Global` neben den Family-DNS-Adressen `DNS Domain: ~.`. Funktioniert die Namensauflösung nach der Umstellung nicht, stellt der Helfer die vorherige Konfiguration wieder her und weist darauf hin, dass Family-DNS nicht aktiviert wurde. Lokale Netzwerk-Domains bleiben beim jeweiligen Link-DNS; zusätzliche VPN-Routing-Domains und Anwendungen mit eigenem DNS müssen am Gerät gesondert geprüft werden.

## Prüfung und Vertrauensmodell

Der Dienst lädt nur über HTTPS von GitHub und den erlaubten GitHub-Asset-Hosts. Archivgröße, SHA-256, ein gegebenenfalls von GitHub gelieferter Digest, sichere ZIP-Pfade, Tag/Archiv-Version sowie Manifest, Paket-API und Python-Syntax werden vor der Aktivierung geprüft. Der aktuell installierte Deployment-Code führt die Installation aus; heruntergeladene Deployment-Skripte werden nicht vor der Aktivierung ausgeführt.

Die SHA-Datei sichert die Integrität; sie ist keine unabhängige Signatur. Schreibberechtigte dieses Repos sind damit auch Herausgeber von root-ausgeführten Updates. Der lokale Kontroll-Socket akzeptiert ausschließlich root und den fest vorgesehenen `kids`-Benutzer; die Webaktionen benötigen zusätzlich Eltern-Anmeldung und CSRF-Token. Quelle, Download-URLs und Systembefehle sind nicht frei über den Socket wählbar. Private Repos mit Token werden derzeit nicht unterstützt.

Code und Systemd-Units werden aktualisiert. APT-/Flatpak-Pakete, übrige Systemkonfiguration und Datenmigrationen sind nicht Teil dieses Updaters. Benötigt ein Release solche Änderungen oder eine vom installierten Deployment-Code nicht unterstützte Paket-API, müssen eigene Einrichtungsschritte bzw. eine Neuinstallation in den Release-Notizen stehen.

Status und Fehlersuche auf dem Gerät:

```bash
sudo journalctl -u laurinos-updates.service -u laurinos-update-job.service -n 100 --no-pager
sudo cat /var/lib/laurinos/updates/state.json
cat /usr/local/lib/laurinos/current/installed.json
```

## Arbeiten im Repo

Quellcode direkt in `src/laurinos/` bearbeiten. Vor einer Freigabe:

```bash
python3 tools/build-manifest.py
python3 -B tools/check.py
python3 tools/build-release.py
```

`VERSION` ist die Release-Version. `manifest.json` muss denselben Wert enthalten. `build-manifest.py` aktualisiert das Inventar, wenn Dateien oder Komponenten hinzugefügt oder entfernt werden. Beim Ändern einer bestehenden Datei muss keine Prüfsumme von Hand gepflegt werden: Das Deployment berechnet sie für die Versionsaufzeichnung.

Das Release-Werkzeug erzeugt ein Archiv und eine SHA-256-Datei in `dist/`. Beide Dateien als GitHub-Release-Assets veröffentlichen, wie oben beschrieben.

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
| `updates` | Lokaler Update-Client, GitHub-Download und Prüfdienst/Installationsworker |
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
