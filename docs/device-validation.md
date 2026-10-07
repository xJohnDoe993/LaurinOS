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
- Kamera-/SD-/USB-Videos (mindestens MP4/H.264 und MOV/MJPEG) erscheinen als Videokacheln. Wiedergabe mit Ton, Pause, Zeitleiste, Lautstärke und Clipwechsel prüfen; Bilder wechseln weiterhin nur zwischen Bildern, Tux Paint erhält keine Videodatei.
- Nach einem Update heißt der alte Standardeintrag im Kinder-Menü sowie im lokalen und Web-Elternbereich `Kamera / Bilder / Videos`; eigene Namen und Freigaben bleiben erhalten. Doppelklick auf das Video maximiert die Videoansicht ohne Wiedergabeneustart. Weiterer Doppelklick/F11 oder Esc zeigt die Bedienung wieder; Leertaste pausiert auch im Vollbild. Entfernen/Auswerfen und Schließen auch während des Vollbilds prüfen.
- Doppelklick bei bereits laufender Videoausgabe mehrfach zum Vergrößern und Verkleinern verwenden. Nach einem Klick ins Video Esc prüfen: erstes Esc zeigt die Bedienung und lässt den Clip weiterlaufen, zweites Esc beendet ihn und zeigt die Übersicht, drittes Esc schließt den Medienbrowser. F11 und Leertaste auch nach Fokuswechsel auf die Videoausgabe prüfen. Alt-F4 gibt den Clip auch im Vollbild sofort frei. Ein Eltern-Popup darf Esc weiterhin selbst behandeln.
- Während eines Clips zur Übersicht wechseln, Esc zweimal drücken, Alt-F4 verwenden und die SD-Karte/den Stick entfernen. Ton und Dateizugriff müssen enden; das Kamerafenster darf keinen Fehler über ein gelöschtes Qt-Objekt zeigen. Danach Medium wieder einstecken und einen neuen Clip öffnen.
- Beschädigten Clip und ein Gerät ohne Qt-Multimedia-Pakete prüfen: Hinweis im Player, weiter erreichbare Übersicht und unverändert funktionierende Bildanzeige. Ein vollständiges Backend-Update installiert fehlende Abhängigkeiten; die manuelle Alternative steht in `docs/installation.md`.
- Gewählte Emulatoren starten mit eigenem Testspiel; Nachinstallation im Elternbackend und Controller-Belegung prüfen. BIOS-/PSP-Dateien und Spielstände berücksichtigen.

Dienstzustände und Protokolle:

```bash
systemctl status paimenos-parent-web paimenos-wifi paimenos-bluetooth paimenos-emulators paimenos-updates
journalctl -b -u paimenos-parent-web -u paimenos-wifi -u paimenos-bluetooth -u paimenos-emulators -u paimenos-updates
```

## WLAN beim initialen Setup

- Frisches Debian 12/13 über ifupdown-WLAN installieren. Während aller Paket-/App-/Emulator-Schritte muss die Verbindung aktiv bleiben; keine zweite Passworteingabe und keine Live-Übergabe. Vor dem regulären Neustart müssen die ifupdown-Dateien unverändert sein und ein privater `pending.json`-Plan existieren.
- Eine unterbrochene Installation mit `--resume` fortsetzen. Profile und Plan dürfen sich nicht duplizieren. Vorhandene PIN und Eltern-Einstellungen müssen erhalten bleiben.
- Nach dem regulären Neustart: Migration vor den Netzwerkdiensten abgeschlossen, `completed.json` vorhanden, NetworkManager verbunden, Standardroute/DNS/APT und Elternbackend funktionsfähig. Kein zweiter WPA-/ifupdown-Besitzer desselben WLAN-Adapters.
- Einen zweiten Neustart prüfen: keine erneute Migration und weiterhin Autoconnect. Bei vorher über `nmtui` verbundenem WLAN darf keine Migration vorbereitet werden.
- Auf einem Testgerät Fehler bzw. Prozessabbruch während der Boot-Übernahme simulieren und Wiederherstellung prüfen. Spätere manuelle Änderungen an der Debian-Konfiguration dürfen nicht überschrieben werden.
- Die GitHub-Prüfung `Debian Wi-Fi installation and reboot` verwendet getrennte Debian-12/13-VMs, `mac80211_hwsim`, einen WPA2-AP und echte DHCP-/NetworkManager-/WPA-Dienste. Sie führt das normale Setup, einen Abbruch mit Fortsetzung sowie den echten Neustart aus. VM-Ergebnisse ersetzen keinen T450-Test mit Intel-Firmware und Hardware-Schalter.

## PaimenOS-Plymouth

- Nach Neuinstallation bzw. einmaliger Aktivierung auf einem vorhandenen Gerät
  muss `plymouth-set-default-theme` den Wert `paimenos` ausgeben.
- Kaltstart, Neustart und Herunterfahren prüfen: heller Hintergrund, lesbare
  PaimenOS-Wortmarke, sanftes Einblenden und laufender grüner Ladekreis. Bei schnellem
  Boot darf die Animation nicht auf einen vollständigen Durchlauf warten.
- Wenn vorhanden, die Laufwerksverschlüsselung prüfen: Passwortabfrage sichtbar,
  Sternchen bei Eingabe und Rücknahme, erfolgreicher Start nach Entsperrung.
  Auch ein falsches Passwort testen. Passwörter werden vom Theme nicht protokolliert.
- Kleine Auflösung und native T450-Auflösung prüfen: Logo, Ladekreis, Meldungen
  und Eingabefeld dürfen weder abgeschnitten sein noch einander verdecken.
- Ein normales Code-Update bzw. Code-Rollback darf die separat ausgewählte
  Theme-Einstellung nicht verändern. Den Nachinstallationsbefehl erneut ausführen
  und bei Bedarf die Rückkehr zum weiterhin installierten Pixels-Theme prüfen.

## Updateprüfung

Vorher eine App-Liste, eigene PIN, Controller-Profil und einen Spielstand anlegen. Ein reines Controller-Update aus einem vorbereiteten Testrelease ausführen. Prüfen, dass Eltern-Daten erhalten bleiben und andere Komponentendateien dieselben Hashes in `installed.json` haben. Anschließend Code-Rollback testen und erneut prüfen.

## GitHub-Updates im Backend

- Die einmalige Aktualisierung von 0.60.0 auf 0.61.0 aktiviert `paimenos-updates.service`; der Dienst startet auch nach einem Neustart.
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
sudo journalctl -b -u paimenos-packages.service -u paimenos-update-job.service --no-pager
cat /usr/local/lib/paimenos/current/installed.json
dpkg-query -W python3-pyqt5.qtmultimedia libqt5multimedia5-plugins gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-libav
```

Erst nach diesen Geräteprüfungen den Stand als auf Debian/T450 praktisch getestet markieren.
