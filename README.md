# PaimenOS

<img src="assets/branding/paimenos-logo.png" alt="PaimenOS" width="240">

PaimenOS macht einen Debian-Laptop zum Kinder-PC mit Kachelmenü, lokalen und webbasierten Eltern-Einstellungen, Bildschirmzeit, Kamera-/USB-Medien, Controller-Steuerung und auswählbaren Emulatoren.

**Version 0.64.0: LaurinOS heißt jetzt PaimenOS.** Paimen ist Finnisch für Schäfer. Oberfläche, Python-Paket, Dienste, Befehle, Datenverzeichnisse und Release-Dateien verwenden den neuen Namen. Diese Version benötigt eine Neuinstallation auf frischem Debian 12 oder 13; bestehende LaurinOS-Installationen werden nicht automatisch übernommen. Eigene Bilder, ROMs und Spielstände vor der Neuinstallation sichern.

## Installieren

Archiv entpacken, in den Projektordner wechseln und ausführen:

```bash
sudo bash install.sh
```

Das Setup fragt eine neue Eltern-PIN, die gewünschten Apps, deren Paketquelle und die Emulatoren ab. Am Ende selbst neu starten:

```bash
sudo reboot
```

Der Eltern-Webbereich ist anschließend unter `http://<IP-des-Geräts>/` erreichbar. Die gewählte PIN gilt auch am Laptop.

Bei einem abgebrochenen Setup kann dieselbe modulare Installation fortgesetzt werden:

```bash
sudo bash install.sh --resume
```

Details und Installationsschalter stehen in [docs/installation.md](docs/installation.md).


## Code aktualisieren

Im Eltern-Webbackend unter **Updates** neue stabile Versionen prüfen und installieren. Ein Hinweis erscheint auf allen angemeldeten Backend-Seiten, sobald ein neueres Release verfügbar ist. Quelle ist das [bestehende GitHub-Repo](https://github.com/xJohnDoe993/LaurinOS/releases). Sein Repository-Name wird separat geändert; [Hinweise zur Umbenennung](docs/updating.md#repository-auf-github-umbenennen).

ZIP und SHA-256 lassen sich automatisch auf GitHub erzeugen: **Actions → PaimenOS Release vorbereiten → Run workflow**. Der Workflow erstellt einen Release-Entwurf mit beiden Dateien. Anleitung: [Automatischer Release-Build](docs/updating.md#automatischer-release-build-auf-github).

Für ein manuelles Update einer vorhandenen PaimenOS-Installation das neue Release auf das Gerät kopieren, in dessen Ordner wechseln und zunächst prüfen:

```bash
bash update.sh --check
sudo bash update.sh
```

Nur Controller-Code aktualisieren:

```bash
sudo bash update.sh --component controller
```

Zur vorherigen Code-Version zurückkehren:

```bash
sudo bash update.sh --rollback
```

Updates starten die PaimenOS-Dienste und eine aktive Kindersitzung neu. Vorher laufende Apps und Spiele beenden. Eltern-Einstellungen, App-Listen, eigene Bilder, ROMs und Spielstände werden nicht aus dem Repo überschrieben. Fehlende Debian-Pakete aus `data/update-packages.json` werden beim Backend-Update und mit `update.sh` automatisch nachinstalliert. Dafür ist Internet erforderlich. Übrige Systemkonfiguration und Flatpak-Einrichtung benötigen weiterhin eigene Einrichtungsschritte; Systemd-Units lassen sich über die Komponente `services` aktualisieren.

[docs/updating.md](docs/updating.md) enthält die Schritt-für-Schritt-Anleitung für GitHub-Releases, die einmalige Einrichtung, Grenzen, Teilupdates und Rollback.

## Entwickeln

```bash
python3 -B tools/check.py
```

Diese Prüfung benötigt nur Python 3 und Bash. Sie installiert nichts und greift weder auf Netzwerk noch auf Geräte zu. Für einen GUI-/Gerätetest werden die Debian-Pakete und eine laufende X11-Sitzung benötigt.

Neue Dateien einem Bereich in `tools/build-manifest.py` zuordnen und das Manifest erzeugen:

```bash
python3 tools/build-manifest.py
python3 -B tools/check.py
```

Für die Entwicklung wird der Quellcode direkt bearbeitet. Auf dem Kindergerät startet derselbe Paketcode über `run.py`, ohne Abhängigkeit von einem Git-Checkout oder einer Python-Virtualenv.

## Projektbereiche

| Verzeichnis | Inhalt |
|---|---|
| `src/paimenos/` | Python-Paket: Menü, Elternbereich, Controller, WLAN/Bluetooth, Emulatoren, Bildschirmzeit |
| `installer/` | Installation in thematischen Bash-Modulen; gemeinsame Helfer und Variablen |
| `config/` | Openbox, Firefox, LightDM, Polkit, NetworkManager, TLP und weitere Systemkonfiguration |
| `systemd/` | System- und Benutzerdienste |
| `assets/` | Icons, Webapp-CSS und HTML des Elternbackends |
| `data/` | Vorgaben für Apps/Einstellungen und Emulator-Katalog |
| `bin/`, `sbin/` | Kleine Startbefehle und WLAN-Übergabe |
| `tools/` | Deployment, Release-Erstellung und Installationshelfer |
| `tests/` | Automatische Tests für Datenzugriff, Ressourcen, Teilupdates und Rollback |
| `docs/` | Installation, Architektur, Updates und Geräteprüfung |

Die Aufteilung und die bewusst geänderten Pfade sind in [docs/architecture.md](docs/architecture.md) dokumentiert. Eine echte Debian-Installation und T450-Hardwaretests wurden bei dieser Umstellung noch nicht ausgeführt; der Stand ist eine geprüfte Entwicklungsbasis.
