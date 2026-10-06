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

## Automatischer Release-Build auf GitHub

Der Workflow `.github/workflows/release.yml` baut das LaurinOS-Update-ZIP und seine SHA-256-Datei auf GitHub und lädt beide in einen Release-Entwurf. Er veröffentlicht das Release nicht selbst. Dadurch sieht das Gerätebackend erst nach der Freigabe ein vollständiges Release, auch wenn unveränderliche Releases auf GitHub aktiviert sind.

Einmalig diesen Workflow in `main` übernehmen. Danach für jede neue Version:

1. Alle gewünschten Änderungen in `main` zusammenführen. `VERSION`, `src/laurinos/__init__.py` und `pyproject.toml` auf dieselbe höhere Version setzen, beispielsweise `0.63.5`. `python3 tools/build-manifest.py` ausführen und die Versionsdateien samt Manifest committen/pushen. Bereits veröffentlichte Versionen bekommen keine neuen ZIPs; für Korrekturen eine neue Versionsnummer verwenden.
2. [GitHub → Actions](https://github.com/xJohnDoe993/LaurinOS/actions) öffnen, **LaurinOS Release vorbereiten → Run workflow** wählen. Als Branch `main` und als Tag `v0.63.5` angeben. **Run workflow** klicken. Der Tag muss zu den Versionsdateien passen.
3. Den erfolgreichen Lauf abwarten. GitHub prüft Versionen, Manifest, Python-/Shell-Dateien sowie Tests inklusive Flask und Qt-Widgets und baut mit `tools/build-release.py`. Die Zusammenfassung des Laufs enthält den Link zum Release-Entwurf.
4. Unter [Releases](https://github.com/xJohnDoe993/LaurinOS/releases) den Entwurf öffnen. Prüfen, dass `LaurinOS-0.63.5.zip` **und** `LaurinOS-0.63.5.zip.sha256` vorhanden sind. Die automatisch erzeugten Release-Notizen ergänzen, insbesondere nötige Systemeinrichtungsschritte und bekannte Einschränkungen.
5. Die Dateien herunterladen und die [Geräteprüfung](device-validation.md) durchführen. Danach **Publish release** wählen. Für das stabile Geräteupdate **Pre-release** ausschalten und das Release als neuestes Release markieren.
6. Im Elternbackend **Updates → Nach Updates suchen** öffnen. Bei einer bereits identischen Version wird kein Update angeboten.

Bei einem bereits vorhandenen Tag baut der manuelle Lauf dessen Commit, auch wenn im Auswahlfeld ein anderer Branch steht. Ohne vorhandenen Tag verwendet er den beim Start ausgewählten Commit und setzt diesen als Ziel des Release-Entwurfs. Vor der Veröffentlichung den Tag nicht auf einen anderen Commit verschieben. Ein leerer, schon manuell angelegter Entwurf wird mit den beiden Dateien ergänzt; seine Release-Notizen bleiben erhalten.

Alternativ nach dem Commit der Versionsdateien einen Tag pushen:

```bash
git tag v0.63.5
git push origin v0.63.5
```

Auch dieser Weg startet den Workflow automatisch. Der getaggte Commit muss den Workflow und seinen Helfer enthalten. Ein direkt auf der Releases-Seite veröffentlichtes Release löst diesen Build nicht aus; stattdessen zuerst den Workflow starten und anschließend seinen fertigen Entwurf veröffentlichen.

Es ist kein persönlicher Token oder zusätzliches Secret nötig: Der Workflow nutzt den von GitHub bereitgestellten `GITHUB_TOKEN` mit `contents: write`. Sind Actions durch Repository-/Organisationsregeln deaktiviert oder Schreibrechte eingeschränkt, müssen diese Regeln angepasst werden. Manuelles **Run workflow** ist erst sichtbar, wenn die Workflow-Datei in `main` liegt.

Bei Fehlern die Logs im Actions-Lauf ansehen. Versions-/Manifest-Fehler vor dem Upload erzeugen kein Release. Vorhandene veröffentlichte Releases sowie vorhandene ZIP-/SHA-Dateien werden nicht überschrieben. Nach einem teilweise fehlgeschlagenen Upload den Entwurf unveröffentlicht lassen, nur dessen vorhandene LaurinOS-ZIP-/SHA-Dateien löschen und den Lauf erneut starten. Bei Quellcodekorrekturen nach dem Taggen einen neuen Versions-Tag verwenden.

### Versionsfehler beim Start mit v0.63.3

Die Angabe eines neuen Tags in **Run workflow** erhöht die Projektversion nicht automatisch. Meldet der Lauf `Tag v0.63.3 zeigt auf Projektversion 0.63.1`, fehlen im ausgewählten Quellstand die Änderungen an den Versionsdateien.

Für diesen Stand sind `VERSION`, Python-Paket, `pyproject.toml` und Manifest auf `0.63.3` vorbereitet. Erst den Pull Request für diese Version in `main` zusammenführen. Danach einen **neuen** Lauf mit Branch `main` und Tag `v0.63.3` starten. Ein erneutes Ausführen des alten fehlgeschlagenen Laufs verwendet dessen alten Quellstand. Ein vorhandener Tag wird ebenfalls weiter verwendet; er muss bereits auf einen Commit mit der passenden Projektversion zeigen.

Das veröffentlichte `v0.63.2` enthält keine Update-Assets. Für den nächsten Geräteupdate deshalb den vollständigen Entwurf für `v0.63.3` bauen und erst nach erfolgreichem Build mit ZIP und SHA-256 veröffentlichen. Der neue Stand enthält auch die Korrektur des Kamera-Namens auf bestehenden Geräten und Video-Vollbild per Doppelklick.

### Fehlgeschlagener erster Lauf mit v0.63.0

Der [Lauf vom 6. Oktober 2026](https://github.com/xJohnDoe993/LaurinOS/actions/runs/37418593904) verwendete den bereits vorhandenen Tag `v0.63.0`. Dieser zeigt auf Commit `400b1a5`, dessen `VERSION` noch `0.62.0` ist und der den Release-Helfer nicht enthält. Daher meldete Python eine fehlende Datei. Die Auswahl von `main` beim manuellen Start überschreibt einen vorhandenen Tag nicht.

Der korrigierte Stand ist für `0.63.1` vorbereitet. Nach Übernahme dieser Änderungen **Run workflow** mit Branch `main` und Tag **`v0.63.1`** starten. Den bisherigen Tag nicht verschieben und den fehlgeschlagenen Lauf nicht bloß erneut starten: Beides würde den falschen Quellstand erneut verwenden. Falls `v0.63.0` schon als Release veröffentlicht wurde, für Geräte auf diesem Stand trotzdem das neue `0.63.1` verwenden.

Die frühe Versionsprüfung zeigt künftig bei einem falschen Tag die tatsächlich ausgecheckte Projektversion sowie den nächsten Schritt an. Fehlt bei passender Version der Helfer, weist sie darauf hin, dass der Tag einen Stand mit dem Workflow enthalten muss. Checkout verwendet jetzt Version 6 mit Node.js 24.

## GitHub-Release manuell bauen und hochladen

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

Code, Systemd-Units und deklarierte fehlende Debian-Abhängigkeiten werden aktualisiert. Flatpak-Einrichtung, übrige Systemkonfiguration und Datenmigrationen benötigen eigene Einrichtungsschritte. Bei einer vom installierten Deployment-Code nicht unterstützten Paket-API ist weiterhin eine manuelle Aktualisierung oder Neuinstallation nötig; dies muss in den Release-Notizen stehen.

Status und Fehlersuche auf dem Gerät:

```bash
sudo journalctl -u laurinos-updates.service -u laurinos-update-job.service -u laurinos-packages.service -n 100 --no-pager
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

`update.sh` installiert deklarierte fehlende Debian-Pakete. Es überschreibt keine Eltern-Daten und verändert keine WLAN-Profile, Firefox-Profile, TLP-Regeln oder andere LaurinOS-Systemkonfigurationen. Flatpak-Einrichtung und weitere Systemänderungen müssen als gesonderte Einrichtungsschritte dokumentiert werden. Die Komponente `services` installiert die im Release enthaltenen LaurinOS-Systemd-Units neu.

## Debian-Pakete bei Updates

Releases deklarieren benötigte Pakete in `data/update-packages.json`, getrennt nach Manifest-Komponenten. Beispiel:

```json
{
  "schema": 1,
  "components": {
    "desktop": ["python3-pyqt5.qtmultimedia", "gstreamer1.0-libav"]
  }
}
```

Die aktuelle Datei enthält die fünf Qt-Multimedia-/GStreamer-Pakete für die Videowiedergabe. Für eine neue Funktion deren benötigte Debian-Paketnamen ergänzen und ein neues Release bauen. Erlaubt sind reine Paketnamen aus den bereits eingerichteten APT-Quellen; Shell-Befehle, neue Quellen, URLs und Paketversionen gehören nicht in diese Datei. Die Zuordnung wird beim Staging in `installed.json` gespeichert. Teilupdates ersetzen nur Anforderungen der gewählten Komponenten und behalten die übrigen Anforderungen bei. Der erste Übergang auf diesen Mechanismus muss ein vollständiges Update einschließlich `tools` und `services` sein.

Bei späteren Updates prüft der bereits installierte Pakethelfer vor dem Codewechsel die Anforderungen des vorbereiteten Releases. Wenn alle Pakete installiert sind, werden keine Paketlisten geladen und kein APT-Installationslauf gestartet. Sonst aktualisiert er die Paketlisten und installiert fehlende Pakete ohne Rückfragen. Er verwendet die exakten Kandidatenversionen aus den bestehenden Quellen, übernimmt bestehende Konfigurationsdateien und verweigert Paketentfernungen. APT kann für die neuen Pakete weitere Abhängigkeiten installieren oder vorhandene Abhängigkeiten aktualisieren; ein allgemeines Systemupgrade oder automatisches Entfernen alter Pakete erfolgt nicht. Ein eventuell installiertes `needrestart` wird für diesen Aufruf auf reine Anzeige gestellt; LaurinOS startet seine Dienste selbst bei der Aktivierung neu.

Der Backend-Fortschritt zeigt Paketprüfung und Nachinstallation. APT-/DNS-Fehler brechen das Update vor dem Codewechsel ab; der bisherige Code bleibt aktiv. Nach Behebung des Fehlers das Update erneut anbieten lassen und starten. Bereits installierte Pakete bleiben erhalten und werden beim nächsten Versuch übersprungen. Ein Code-Rollback entfernt oder degradiert keine Debian-Pakete.

Der bisherige Updater aus 0.61.0/0.62.0 kennt diese Vorbereitung noch nicht. Deshalb enthält das neue Release zusätzlich `laurinos-packages.service`: Nach dem ersten Codewechsel muss dieser Dienst die Pakete erfolgreich prüfen/installieren, bevor Elternbackend und Update-Prüfdienst starten dürfen. Schlägt das fehl, setzt der bisherige Deployer Code und Units zurück. Beim ersten Übergang kann das Backend während der Paketinstallation vorübergehend unerreichbar sein; der bisherige Fortschritt zeigt dann noch die Aktivierung. Kein zusätzlicher manueller Paketbefehl ist erforderlich. Der Dienst prüft auch nach einem Neustart erneut und lädt nichts herunter, solange keine Pakete fehlen.

Paketinstallation und andere LaurinOS-Wartung werden durch Sperren serialisiert. APT wartet bis zu zwei Minuten auf seine Paketsperre und verwendet begrenzte Verbindungswartezeiten sowie Wiederholungen. Wird ein Installationslauf durch Ausschalten unterbrochen und meldet APT anschließend eine beschädigte Paketverwaltung, muss diese auf dem Gerät repariert werden; der Updater führt keine pauschalen Reparaturbefehle aus.

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
5. Fehlende deklarierte Debian-Pakete installieren; bei Fehler den Codewechsel abbrechen. Beim ersten Übergang vom bisherigen Updater übernimmt stattdessen der Paketdienst in Schritt 7 die Prüfung.
6. Den aktiven Link atomar auf den fertigen Code-Stand umschalten.
7. Gegebenenfalls Systemd-Units kopieren, Dienste neu starten und deren aktiven Zustand prüfen.
8. Bei einem erkannten Startfehler den bisherigen Code und gegebenenfalls die bisherigen Units wieder aktivieren und erneut starten.

Die Aktivierung der Code-Version ist atomar. Dienstneustarts und das Kopieren von Systemd-Units sind keine atomare Gesamttransaktion. Ein Stromausfall während dieser Schritte kann manuelle Wiederherstellung erfordern. Ein aktiver Dienst bedeutet außerdem nicht, dass jede Hardwarefunktion erfolgreich getestet wurde.

Manuell zurückkehren:

```bash
sudo bash update.sh --rollback
```

Das betrifft Code und LaurinOS-Units. Spielstände, Eltern-Einstellungen, heruntergeladene Cores, BIOS-Dateien, Debian-/Flatpak-Pakete und sonstige Daten werden nicht zurückgesetzt. Ein Code-Rollback ist keine Datensicherung.

Versionen anzeigen:

```bash
cat /usr/local/lib/laurinos/current/installed.json
```

Frühere Releases bleiben für Fehlersuche erhalten. Eine automatische Löschstrategie ist noch nicht enthalten.
