# Validierung dieser Entwicklungsbasis

Stand: 5. Oktober 2026, Version 0.62.0.

Ausgeführt mit `python3 -B tools/check.py`, zusätzlich mit Flask für die optionalen Backend-Integrationstests:

- Syntaxprüfung von 60 Python-Dateien und 27 Shell-Dateien.
- JSON- und XML-/SVG-Prüfung, Manifest-Inventar, Paketimporte, Installationsquellen und Dienst-Launcher.
- 54 erfolgreiche Tests: vorhandene Daten-/Deployment-Prüfungen sowie Versionsvergleich, stabile Releases und Asset-Zuordnung, HTTPS-Ziele, Download-Grenzen, Prüfsummen, ZIP-Pfade/-Dateitypen, Offline-Cache, Prüfintervall, separate Worker-Aufträge, Wiederanlaufstatus, Archiv-/Tag-Version, Speichermangel, erfolgreiche Aktivierung und Fehler mit Rollback. Systemd-Befehle und Netzwerkantworten sind dabei simuliert.
- Die neun DNS-Tests prüfen Übernahme vorhandener Upstream-Server vor der Paketinstallation, Wiederherstellung von `resolv.conf` nach einem Paketwechsel, erfolgreiche Familien-DNS-Umstellung, nicht erreichbare DNS-Server, Dienststartfehler, fehlende Stub-Datei, vorher schon defektes DNS, Fehler bei der Wiederherstellung und Abbruch mit Strg+C. Auch hier sind DNS-Abfragen und Dienstbefehle simuliert.
- Die fünf Flask-Integrationstests prüfen die echten Backend-Routen mit dem Flask-Testclient: Eltern-Anmeldung, CSRF, getrennte Check-/Install-Aktionen, gerenderte Seite und verständliche Dienstausfälle. Ohne Flask werden diese fünf Tests übersprungen; alle übrigen Tests benötigen nur die Standardbibliothek.
- Die zwei gerenderten JavaScript-Skripte der Update-Seite wurden mit `node --check` geprüft.
- Das vollständige Code-Update vom tatsächlich vorhandenen Repo-Stand 0.60.0 auf 0.61.0 wurde in einem temporären Installationsverzeichnis geprüft, einschließlich neuer Komponenten und vorherigem Release-Link; ohne echte Dienstneustarts.
- Das fertige Archiv wurde auf enthaltene Dateien, Integrität und erfolgreiche Prüfungen nach erneutem Entpacken geprüft.

Nicht ausgeführt: tatsächliche Debian-Installation, Live-Download eines GitHub-Release-Assets, Paketdownloads, Betrieb der Systemd-Dienste/des Unix-Sockets, grafische Oberfläche, WLAN/Bluetooth, Emulatorstarts und T450-Hardwaretests. Dafür steht `docs/device-validation.md` bereit. Vor Veröffentlichung als stabiles Release ist ein Gerätetest erforderlich.

## Videoclips im Kamera-Medienbrowser

Zusätzliche Prüfung am 6. Oktober 2026 mit Flask und PyQt5 im Offscreen-Modus: 64 erfolgreiche Tests, Syntaxprüfung von 63 Python-Dateien und 27 Shell-Dateien. Die neuen Prüfungen decken gemischte Bild-/Videodateien, Groß-/Kleinschreibung, Unterordner, ausgeblendete Verzeichnisse, Abbruch und Dateilinks ab. Reale Qt-Widgets mit einem simulierten Player prüfen lokale Dateinamen mit Leerzeichen/Sonderzeichen, getrennte Bildnavigation, Pause, Suche, Lautstärke, erneute Wiedergabe, Rückkehr/Schließen mit Esc, Entfernen und Auswerfen des Mediums, verspätete Fehler sowie fehlende Multimedia-Pakete.

Die Videoansicht wurde mit realen Qt-Widgets bei 1366×768 gerendert und visuell geprüft. Echte Codec-Decodierung, Audioausgabe und Hardware-Wiedergabe wurden nicht getestet; der Medienplayer ist in den Widgettests simuliert. Ohne die optionalen PyQt5-Abhängigkeiten werden die acht Widgettests übersprungen; die Dateisuche benötigt nur die Standardbibliothek.

## Automatischer GitHub-Release-Build

Am 6. Oktober 2026: 86 Tests mit Flask und Qt im Offscreen-Modus erfolgreich; Syntaxprüfung von 67 Python-Dateien und 27 Shell-Dateien. Neun neue Tests prüfen identische Versionsdateien, gültige Tags, ZIP-/SHA-Abgleich, Commitbindung einschließlich annotierter Tags, neue/vorhandene Entwürfe ohne Veröffentlichung, Schutz bestehender Assets und veröffentlichter Releases, fehlende Berechtigungen sowie unvollständige Uploads. GitHub-CLI-Antworten sind dabei simuliert; es wird kein echtes Release erstellt.

Der Workflow wurde als YAML gelesen, seine Shell- und eingebettete Python-Syntax geprüft und die Tag-Auswahl mit fehlendem, vorhandenem und ungültigem Tag simuliert. Der ZIP-Build und die Prüfung des entpackten Archivs wurden lokal ausgeführt. Ein vollständiger Lauf auf einem GitHub-Runner mit echtem Entwurf/Asset-Upload steht noch aus und erfolgt beim ersten Release nach Übernahme des Workflows.

## Release-Korrektur 0.63.1

Der erste GitHub-Lauf wurde geprüft: `v0.63.0` checkte Commit `400b1a5` mit Projektversion `0.62.0` und ohne `.github/scripts/release.py` aus. Für den neuen Tag `v0.63.1` sind die Versionsdateien und das Manifest synchronisiert; Checkout wurde auf Version 6 mit Node.js 24 aktualisiert.

89 Tests mit Flask/Qt erfolgreich. Die drei zusätzlichen Workflow-Tests führen den tatsächlichen Versionsprüfungsblock aus: falsche alte Version ohne Helfer, passende Version ohne Helfer und gültiger Stand mit dem echten Versionshelfer. Workflow-YAML/Shell-Syntax und der ZIP-/SHA-Build wurden geprüft. Der korrigierte Workflow wurde noch nicht auf GitHub ausgeführt; nach Übernahme muss ein neuer Lauf für `v0.63.1` gestartet werden.

## Kamera-Titel und Video-Vollbild

Am 6. Oktober 2026: 94 Tests mit Flask/PyQt5 im Offscreen-Modus erfolgreich; Syntaxprüfung von 67 Python-Dateien und 27 Shell-Dateien. Die fünf zusätzlichen Tests prüfen die Übernahme des alten Kamera-Standardnamens im gemeinsamen Elternbereich, Kinder-Menü und gerenderten Web-Backend, unveränderte eigene Namen/Icons/Freigaben und App-Dateien sowie Doppelklick, F11, Esc und Leertaste mit realen Qt-Widgets. Der Vollbildwechsel füllt den Bildschirm, erhält Medienobjekt, Wiedergabeposition und Pausezustand und stellt Fensterzustand, Ränder und Bedienung wieder her. Die vorhandenen Tests für Rückkehr, Schließen, Entfernen, Auswerfen und Decoderfehler prüfen jetzt auch das Verlassen des Video-Vollbilds.

Die Playeransicht bei 1366×768 und die randlose Vollbildansicht wurden gerendert und visuell geprüft. Der Medienplayer ist simuliert; echte QVideoWidget-Ausgabe, Codec-Decodierung, Ton und Verhalten auf dem Gerät bleiben über `docs/device-validation.md` zu prüfen. Ohne PyQt5 werden jetzt elf Widgettests übersprungen, ohne Flask sechs Backendtests.
