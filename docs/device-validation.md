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
systemctl status laurinos-parent-web laurinos-wifi laurinos-bluetooth laurinos-emulators laurinos-updates
journalctl -b -u laurinos-parent-web -u laurinos-wifi -u laurinos-bluetooth -u laurinos-emulators -u laurinos-updates
```

## Updateprüfung

Vorher eine App-Liste, eigene PIN, Controller-Profil und einen Spielstand anlegen. Ein reines Controller-Update aus einem vorbereiteten Testrelease ausführen. Prüfen, dass Eltern-Daten erhalten bleiben und andere Komponentendateien dieselben Hashes in `installed.json` haben. Anschließend Code-Rollback testen und erneut prüfen.

## GitHub-Updates im Backend

- Die einmalige Aktualisierung von 0.60.0 auf 0.61.0 aktiviert `laurinos-updates.service`; der Dienst startet auch nach einem Neustart.
- Ohne Eltern-Anmeldung sind Status und Update-Aktionen gesperrt. Mit Anmeldung erscheint die Seite **Updates**.
- Ein höheres stabiles Release mit passenden ZIP-/SHA-Assets wird nach der Prüfung angeboten; Entwürfe, Pre-Releases, identische und ältere Versionen werden nicht angeboten.
- Internet trennen: Fehler und letzte erfolgreiche Prüfung bleiben sichtbar, das restliche Backend funktioniert. Verbindung wiederherstellen und nach mindestens einer Minute erneut prüfen.
- Apps und Spiele schließen. Update per Klick starten; ein zweiter Auftrag währenddessen wird abgewiesen. Fortschritt beobachten, auch wenn die Backend-Verbindung während Dienstneustarts kurz ausfällt.
- Nach Abschluss die neue Version in `installed.json`, aktive Dienste und Kindersitzung prüfen. PIN, Einstellungen, Bilder und Spielstände kontrollieren.
- Code-Rollback testen; bei Rückkehr zu 0.60.0 verschwindet die neue Update-Funktion wieder. Bei Wiederaktivierung von 0.61.0 wird der Prüfdienst erneut aktiviert.
- Auf einem separaten Testgerät einen abgebrochenen Download und einen fehlerhaften Dienststart prüfen. Bei einem erkannten Startfehler muss der bisherige Code wieder aktiv sein; beim Downloadfehler darf sich `current` nicht ändern.

Diese Tests benötigen echte GitHub-Releases und ein Debian-Gerät mit Systemd. Die automatischen Tests ersetzen sie nicht.

## Paket-Nachinstallation

Auf einem separaten Testgerät mit fehlenden deklarierten Paketen prüfen:

- Ein vollständiges Backend-Update vom bisherigen 0.61.0/0.62.0 installiert die fehlenden Pakete ohne zusätzlichen Befehl. Erst danach starten Elternbackend und Prüfdienst. Das Backend kann beim ersten Übergang während der Installation kurzzeitig unerreichbar sein.
- Ein weiteres Release mit einer zusätzlichen gültigen Paketanforderung zeigt die Nachinstallation im Backend-Fortschritt. Code und Dienste wechseln erst nach erfolgreicher Installation. Neuinstallation und `sudo bash update.sh` berücksichtigen dieselben Anforderungen.
- Bei unterbrochener Internetverbindung oder einer nicht verfügbaren Paketanforderung bleibt die bisherige Code-Version aktiv bzw. wird beim ersten Übergang wieder aktiviert. Der Auftrag zeigt einen Fehler. Nach Korrektur der Verbindung/Anforderung funktioniert ein neuer Versuch.
- Ein Neustart mit bereits vorhandenen Paketen löst keinen APT-Download aus. Backend und Prüfdienst starten normal. Der erfolgreiche Oneshot-Paketdienst darf danach `inactive (dead)` sein.
- Ein Code-Rollback erhält hinzugekommene Debian-Pakete sowie Eltern-Daten. Ein Teilupdate erhält die Paketanforderungen der nicht gewählten Komponenten.

```bash
sudo journalctl -b -u laurinos-packages.service -u laurinos-update-job.service --no-pager
cat /usr/local/lib/laurinos/current/installed.json
dpkg-query -W python3-pyqt5.qtmultimedia libqt5multimedia5-plugins gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-libav
```

Erst nach diesen Geräteprüfungen den Stand als auf Debian/T450 praktisch getestet markieren.
