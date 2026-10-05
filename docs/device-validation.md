# Prüfung auf dem Gerät

Die automatischen Prüfungen decken Syntax, Paketimporte, Ressourcen, Emulator-Auswahl, Einstellungszugriff, Webapp-Profile, Gerätefilter und Code-Deployment ab. Sie führen keine echte Debian-Installation, APT-Vorgänge, Systemd-Aktivierung, X11-Sitzung oder Hardwaretests aus.

## Neuinstallation nach dem Neustart

- Kinder-Menü startet durch LightDM; Kacheln öffnen die gewählten Programme.
- Der Elternbereich am Gerät und unter `http://<IP>/` akzeptiert die selbst gesetzte PIN und weist eine falsche PIN ab.
- App-Aktivierung, eigene Webapp, Bild-Upload und Einstellungen bleiben nach einem Neustart erhalten.
- Tageslimit und Bonuszeit funktionieren; der Lockscreen lässt sich mit der Eltern-PIN entsperren.
- Webapps zeigen Zurück/Weiter und schließen ohne fehlerhafte Absturzmeldung. Vollbildvideos prüfen.
- Akku, Uhr, F1–F3, F5/F6, Hardware-Lautstärke/-Helligkeitstasten und OSD prüfen.
- Bluetooth koppelt den Controller; Menüsteuerung, Belegungsassistent und Cursor-Ausblenden funktionieren. Den auf dem T450 bislang zuverlässigen D-Input-Modus zuerst verwenden.
- WLAN kann scannen, verbinden und gespeicherte Verbindungen verwalten. Erweiterte Einstellungen öffnen den NetworkManager-Editor.
- Kamera-/SD-/USB-Bilder werden angezeigt; Tux Paint startet ein gewähltes Bild und beendet sich ohne CameraBrowser-Fehler.
- Gewählte Emulatoren starten mit eigenem Testspiel; Nachinstallation im Elternbackend und Controller-Belegung prüfen. BIOS-/PSP-Dateien und Spielstände berücksichtigen.

Dienstzustände und Protokolle:

```bash
systemctl status laurinos-parent-web laurinos-wifi laurinos-bluetooth laurinos-emulators
journalctl -b -u laurinos-parent-web -u laurinos-wifi -u laurinos-bluetooth -u laurinos-emulators
```

## Updateprüfung

Vorher eine App-Liste, eigene PIN, Controller-Profil und einen Spielstand anlegen. Ein reines Controller-Update aus einem vorbereiteten Testrelease ausführen. Prüfen, dass Eltern-Daten erhalten bleiben und andere Komponentendateien dieselben Hashes in `installed.json` haben. Anschließend Code-Rollback testen und erneut prüfen.

Erst nach diesen Geräteprüfungen den Stand als auf Debian/T450 praktisch getestet markieren.
