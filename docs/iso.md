# PaimenOS-ISO: Debian-Basis und interaktives Setup

Unter **Actions → Build PaimenOS ISO → Run workflow** den gewünschten
Branch auswählen. Das Artefakt **PaimenOS-ISO-amd64** enthält ISO und SHA-256.
Buildprotokolle stehen auch bei Fehlern bereit. Downloads bleiben sieben Tage
verfügbar; der Workflow veröffentlicht keinen Release.

## Installation

1. ISO auf einen USB-Stick schreiben und davon booten.
2. Im Bootmenü den Debian-Installer starten. Zielplatte und Administrator-Zugang
   selbst wählen; als Administrator einen anderen Namen als `kids` verwenden.
3. Installation abschließen, USB-Stick entfernen und neu starten.
4. Auf der ersten Textkonsole erscheint die PaimenOS-Einrichtung automatisch.
   Bei Bedarf mit **1** über `nmtui` WLAN einrichten; mit **2** das Setup starten.
5. Eltern-PIN, Emulatoren, Apps und Debian/Flathub-Paketquelle im normalen
   Setup selbst wählen. Nach Abschluss neu starten: Die Kinderoberfläche erscheint.

Das ISO enthält das Debian-Grundsystem, NetworkManager, WLAN-Firmware und
root-eigenen PaimenOS-Quellcode. Es installiert beim ISO-Bau keine Kinderprogramme,
Emulatoren, Eltern-Dienste oder voreingestellte PIN. Das vollständige Setup
benötigt auf dem Gerät eine Internetverbindung und verwendet unverändert
`/opt/paimenos-source/install.sh`, den aktuellen modularen Setup-Prozess des Repos.
Das Plymouth-Theme wird ebenfalls erst durch dieses Setup aktiviert.

Der Live-Modus bietet eine Debian-Textkonsole zum Prüfen der Basis, keine fertige
Kinderoberfläche. Die automatische Einrichtung wird nur auf dem installierten
System durch den Debian-Installer aktiviert. Nach erfolgreichem Setup wird sie
deaktiviert und erscheint bei späteren Neustarts nicht erneut.

Bei einem Fehler kann das Setup im selben Menü erneut gestartet werden. Eine
bereits angelegte modulare Installation wird mit `--resume` fortgesetzt. Wird
das Gerät vorher ausgeschaltet, startet die Einrichtung beim nächsten Boot wieder.
Manuell ist das Fortsetzen auch möglich:

```bash
sudo bash /opt/paimenos-source/install.sh --resume
```

## Build und Prüfung

Der Build läuft in einem privilegierten Debian-13-Container auf einem
GitHub-Runner, ohne zusätzliche Repository-Secrets. BIOS- und UEFI-Bootloader
sind enthalten; Secure Boot ist noch nicht verifiziert. Nur vertrauenswürdige
Branches bauen. Das ISO enthält den eingecheckten Stand, keine Git-Zugangsdaten.
Die Installer-Vorkonfiguration liegt unter `/cdrom/preseed.cfg`; der Build
extrahiert sie aus dem fertigen ISO und prüft den Inhalt gegen die Quelle.

Für einen lokalen Build in Debian 13 mit root-Rechten:

```bash
apt-get update
apt-get install -y live-build debootstrap git ca-certificates xorriso squashfs-tools grub-pc-bin grub-efi-amd64-bin mtools dosfstools
bash iso/build.sh
```

Änderungen vorher committen: Der Build verwendet `git archive HEAD`.
`/var/tmp/paimenos-live` darf noch nicht existieren; für weitere Builds ein neues
Verzeichnis über `PAIMENOS_BUILD_DIR` wählen. Ergebnis: `dist/iso/`.

Vor Freigabe in einer VM BIOS/UEFI-Boot und Debian-Installation testen. Nach
Entfernen des ISO prüfen: Setup startet, Netzwerk lässt sich einrichten,
App-/Emulator-Auswahl funktioniert, Fehler lassen sich fortsetzen, danach
startet die Kinderoberfläche und die Einrichtung bleibt deaktiviert. Anschließend
T450-WLAN, Bluetooth, Ton, Suspend und Controller prüfen. Ein vollständiger
ISO-/Installations- und Hardwaretest wurde für diese Umstellung noch nicht ausgeführt.
