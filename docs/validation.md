# Validierung dieser Entwicklungsbasis

Stand: 5. Oktober 2026, Version 0.61.0.

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
