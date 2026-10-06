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

## Paket-Nachinstallation, 6. Oktober 2026

`python3 -B tools/check.py` mit Flask: 67 erfolgreiche Tests, 62 Python-Dateien und 27 Shell-Dateien. Die zusätzlichen Tests prüfen Paketdeklarationen, native Architektur und vollständigen Installationszustand, nichtinteraktive Installation mit exakten Kandidatenversionen, fehlende Kandidaten, APT-Fehler, unvollständige Installation, Wiederholbarkeit, Teilupdate-Anforderungen, Abbruch vor dem Codewechsel sowie die Fehlermeldung des Update-Auftrags im Backend.

Der unveränderte Deployment-Code aus dem vorbereiteten 0.62.0-Archiv liegt als Testfixture bei. Mit ihm wird der erste Übergang auf den Paketdienst in temporären Installations- und Unit-Verzeichnissen ausgeführt: fehlgeschlagene Nachinstallation mit Code-/Unit-Rollback und anschließend erfolgreicher neuer Versuch. APT und Systemd-Startabläufe sind dabei simuliert. Eine echte Paketinstallation und die Dienstabhängigkeiten auf Debian müssen vor dem Release auf einem Testgerät geprüft werden.
