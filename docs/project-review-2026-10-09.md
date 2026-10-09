# Projektprüfung vom 9. Oktober 2026

Basis: `86bb68eee70f8f94ae83bbd529b353070d42b4bb`, PaimenOS 0.65.0.
Geprüft wurde das aktuelle modulare GitHub-Projekt. Der zusätzlich bereitgestellte
historische LaurinOS-v36-Installer ist keine Grundlage für diesen Fix.

## Gefundene und behobene Fehler

1. `state.update_settings()` ersetzte beschädigte Zeitwerte durch null und
   ergänzte fehlende Werte ebenfalls mit null. Ein ungültiges Tageslimit konnte
   damit unbegrenzte Nutzung freigeben; fehlerhafte Verbrauchswerte konnten
   verbrauchte Zeit zurücksetzen. Negative Werte, Bruchteile und boolesche Werte
   wurden ebenfalls still umgewandelt. Diese Werte werden nun zurückgewiesen,
   ohne die Datei zu überschreiben. Nichtnegative Ganzzahlen und bisher
   unterstützte reine Ziffernstrings bleiben verwendbar.
2. Bei nicht lesbaren Einstellungen beendete sich der Zeitwächter. Auch der
   Sperrbildschirm scheiterte beim Start oder bei einer späteren Aktualisierung.
   Der Zeitwächter bleibt nun aktiv und startet die Sperre; der Sperrbildschirm
   bleibt bei Datenfehlern geschlossen für Kinderzugriffe. Ein bereits sichtbares
   Kindermenü wird ausgeblendet. Nach einer gültigen Reparatur mit verfügbarer
   Zeit wird die Sperre wieder aufgehoben. Fehler im PIN-/Bonusdialog starten die
   zuvor angehaltenen Aktualisierungs- und Abschalttimer zuverlässig erneut.

## Prüfungen

- Projektweite Prüfung mit `tools/check.py`: Syntax von 85 Python- und
  35 Shell-Dateien, Manifest, Ressourcen, JSON/XML/SVG, Paketimporte,
  Installerquellen und Dienstpfade.
- Vollständiger Testlauf mit Flask, PyQt5 und python-xlib: 229 Tests,
  davon 225 erfolgreich und vier übersprungen. Enthalten sind Deployment und
  Rollback, Update-/Releaseprüfung, ISO-/APT-Helfer, WLAN-Übergabe, Browserprofile,
  Medien, Qt-Sperre, Elternbackend, CSRF und deutsche/englische Oberflächen
  einschließlich JavaScript-Syntax der gerenderten Seiten.
- Anschließend ergänzter Kompatibilitätstest für numerische Strings:
  alle neun Tests in `test_runtime.py` erfolgreich. Der finale Testbestand
  umfasst somit 230 Tests; 226 unterschiedliche Tests wurden erfolgreich
  ausgeführt, vier benötigen zusätzliche Laufzeitumgebungen.
- Die neuen Fehlerfälle für ungültige Zeitwerte, Zeitwächter und Qt-Sperre
  schlugen vor der jeweiligen Korrektur reproduzierbar fehl.
- Pyflakes über `src`, `tools`, `iso` und `.github/scripts`: keine undefinierten
  Namen; vorhandene Hinweise betreffen ungenutzte Imports/lokale Variablen.
- `git diff --check` ohne Befund.

## Grenzen

Die vier übersprungenen Tests betreffen Firefox mit Openbox/X11, zwei echte
X11-Fenster-/Eingabeprüfungen und ein Qt-Multimedia-Widget. Systembefehle,
Netzwerk- und Hardwareantworten werden in vielen Tests simuliert. Kein echter
ISO-Build, keine Debian-Neuinstallation, keine realen WLAN-/Bluetooth- oder
Emulator-/Gerätetests wurden ausgeführt. Die Prüfung ist keine Zusicherung,
dass das gesamte Projekt fehlerfrei ist.

Dieser Fix repariert keine beschädigten Einstellungen automatisch und verändert
keine Spielstände. Er führt auch keine neue automatische Speichern-Funktion ein.
Die Projektversion bleibt unverändert; es wurde kein Release veröffentlicht.
