# Validierung dieser Entwicklungsbasis

Stand: 5. Oktober 2026, Version 0.60.0.

Ausgeführt mit `python3 -B tools/check.py`:

- Syntaxprüfung von 53 Python-Dateien und 27 Shell-Dateien.
- JSON- und XML-/SVG-Prüfung, Manifest-Inventar, Paketimporte, Installationsquellen und Dienst-Launcher.
- 17 erfolgreiche Tests für vollständiges Code-Deployment, Teilupdates, Entfernen alter Dateien, Syntaxfehler vor Aktivierung, Code-Rollback, Dienst-/Unit-Fehler mit Wiederherstellung, ungültige Pfade/Quellen, Eltern-Einstellungen, Emulator-Auswahl, Controller-Gerätefilter, generierte App-Liste und Firefox-Ressourcen.
- Zusätzlich: Alle 18 extrahierten HTML-Ressourcen stimmen bytegenau mit ihren ursprünglichen Texten aus der v59 überein.
- Das fertige Archiv wurde auf enthaltene Dateien, Integrität und erfolgreiche Prüfungen nach erneutem Entpacken geprüft.

Nicht ausgeführt: tatsächliche Debian-Installation, Paketdownloads, Betrieb der Systemd-Dienste, grafische Oberfläche, WLAN/Bluetooth, Emulatorstarts und T450-Hardwaretests. Dafür steht `docs/device-validation.md` bereit.
