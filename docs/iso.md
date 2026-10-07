# PaimenOS-ISO bauen

Unter **Actions → Build PaimenOS ISO → Run workflow** den gewünschten
Branch auswählen. Nach erfolgreichem Build das Artefakt **PaimenOS-ISO-amd64**
herunterladen und entpacken. Es enthält ISO und SHA-256-Prüfsumme.
Buildprotokolle werden auch bei einem fehlgeschlagenen Build bereitgestellt.
Die Downloads bleiben sieben Tage verfügbar. Es wird kein Release veröffentlicht.

Das Hybrid-ISO ist für amd64-PCs wie den T450 ausgelegt, mit BIOS- und UEFI-
Bootloader. ISO mit einem USB-Imager auf den Stick schreiben. Im Bootmenü
kann PaimenOS live ausprobiert oder der Debian-Installer gestartet werden.
Der Installer fragt weiterhin nach Zielplatte und Administrator-Zugang.
Als Administrator einen anderen Benutzernamen als `kids` wählen.
Es werden keine Partitionierungsentscheidungen vorgegeben.

Die Kinderoberfläche, Eltern-Dienste und das PaimenOS-Plymouth-Theme werden
bereits im Image eingerichtet. Vorinstallierte Debian-Apps: Tux Paint,
SuperTux, GCompris und VLC. Emulatoren können später im Elternbackend
installiert werden. Flatpak-Apps sind in dieser ersten ISO-Konfiguration
nicht vorinstalliert.

Beim ersten Live-Start bzw. ersten Start nach der Installation öffnet sich
ein Terminal für die neue Eltern-PIN. Danach startet das Kinder-Menü.
Das Image enthält keine nutzbare vorgegebene PIN. Das Eltern-Webbackend und
der Release-Updater starten erst nach der PIN-Einrichtung. Eine im Live-Modus
gewählte PIN wird bei der Installation zurückgesetzt. Abbruch der PIN-Eingabe
öffnet die Einrichtung erneut. Die PIN ist kein Linux-Administratorpasswort.

Der Build läuft in einem privilegierten Debian-13-Container auf einem
GitHub-Runner. Er benötigt keine zusätzlichen Repository-Secrets. Nur
vertrauenswürdige Branches bauen: die Installer-Hooks laufen als root.
ISO-Größe, Laufzeit und Actions-Speicher hängen von den Debian-Paketen ab.
Ein erfolgreicher Build ersetzt keinen Installations- und Hardwaretest.

## Lokal bauen

In einem frischen Debian-13-System mit root-Rechten:

```bash
apt-get update
apt-get install -y live-build debootstrap git ca-certificates xorriso squashfs-tools grub-pc-bin grub-efi-amd64-bin mtools dosfstools
bash iso/build.sh
```

Der Build verwendet ausschließlich den eingecheckten Stand (`git archive HEAD`).
Änderungen vorher committen. Das Buildverzeichnis `/var/tmp/paimenos-live`
muss noch nicht existieren; für weitere Builds ein neues Verzeichnis mit
`PAIMENOS_BUILD_DIR` wählen. Ergebnis: `dist/iso/`.

## Vor Freigabe testen

ISO in einer VM jeweils mit BIOS und UEFI booten, Live-PIN setzen und Menü
prüfen. Anschließend offline auf eine leere virtuelle Platte installieren:
Administrator anlegen, ISO auswerfen, Neustart, neue PIN setzen und Backend
prüfen. Danach T450-WLAN, Bluetooth, Ton, Suspend und Controller prüfen.
Secure Boot ist mit dieser Konfiguration noch nicht verifiziert.
