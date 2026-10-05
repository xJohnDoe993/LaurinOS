# Ausgangspunkt und Änderungen

Basis: angehängte `LaurinOS-Setup-v59-emulator-auswahl(1).sh`, 10.384 Zeilen.

SHA-256 der Referenz:

```text
92ba396909279c67e2f984f9c5a580410a1e309c0f9e26b9b01a228529828714
```

Übernommen wurden die vorhandenen Funktionsbereiche und Installationsentscheidungen aus v59: Menü und Elternverwaltung, App-Auswahl, Kamera/Medien, Bildschirmzeit, Webapp-Navigation, OSD, Akku, Cursor, WLAN/Bluetooth, Controller-Profile, Emulator-Auswahl/-Nachinstallation sowie Laptop-Konfiguration.

Bewusst geändert:

- Eigenständige Repo-Dateien und ein Python-Paket statt eingebetteter Python-/Konfigurations-Heredocs.
- Root-eigener Code in versionierten Releases; Einstellungen und Protokolle in eigenen Benutzerverzeichnissen.
- Gemeinsames WLAN-Modul für Client und Dienst; feste Paketimporte statt Imports aus dem Kinderverzeichnis.
- JSON-Emulator-Katalog und benannte HTML-Dateien für den Web-Elternbereich.
- Eigene Eltern-PIN beim Setup; fehlende oder ungültige Einstellungen schalten keine bekannte Standard-PIN frei.
- Gemeinsamer Flatpak-Starter: künftige Änderungen an Startoptionen gelten für alle vom Setup erzeugten App-Starter.
- Getrennter Code-Updater mit Teilupdates, Versionsaufzeichnung und Code-Rollback.
- Kein automatischer Neustart als Standard. Keine v59-Migration.

Die Controller- und Emulatoralgorithmen wurden bei der Aufteilung nicht neu entwickelt. Das ersetzt keine praktischen Leistungstests auf dem T450.
