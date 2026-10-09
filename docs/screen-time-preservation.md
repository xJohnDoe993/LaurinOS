# Daten bei abgelaufener Bildschirmzeit erhalten

Der Sperrbildschirm lässt offene Anwendungen bestehen und fährt den Rechner
nicht mehr nach zehn Minuten automatisch herunter. Vor dem Ausschalten über
den Sperrbildschirm erscheint eine Bestätigung (Standard: Abbrechen).
Eltern können zusätzliche Zeit freigeben, damit Arbeiten gespeichert werden.
Die bestehende Sperre und die gesperrten App-Starts bleiben unverändert aktiv.

## Emulatoren

Der PaimenOS-Emulatorstarter beaufsichtigt RetroArch über eine private
Standardeingabe-Pipe. Bei Zeitablauf fordert er mit `SAVE_STATE` einen neuen,
automatisch nummerierten Speicherstand an. Nach zwei Sekunden wird nur der
eigene RetroArch-Prozess mit `SIGSTOP` angehalten. Nach Zeitfreigabe setzt
`SIGCONT` dieselbe Sitzung fort. Ein neuer Zeitablauf erzeugt einen neuen
Speicherauftrag. Es wird kein Netzwerk-Steuerport geöffnet.

Die automatische Slot-Nummerierung zählt vom ausgewählten Slot weiter; alte
Stände werden nicht automatisch gelöscht. Wird im RetroArch-Menü manuell ein
älterer Slot gewählt, kann der nächste Speicherauftrag dessen Folgeslot ersetzen.
Der letzte nummerierte Stand kann in RetroArch über F10 bzw. das F8-Schnellmenü
geladen werden; die bestehende Auto-Load-Regel für `.auto`-Stände bleibt erhalten
(bei PS1 weiterhin deaktiviert). Spielinterner SRAM wird zusätzlich alle zehn
Sekunden gespeichert, soweit der Core dies unterstützt. Normales Beenden
behält RetroArchs Auto-Save bei.

Ein Speicherauftrag ist keine bestätigte Sicherung: Core-Unterstützung,
Schreibfehler oder langsame Speichermedien können den Save-State verhindern.
Deshalb wird die Sitzung bei Zeitablauf **nicht beendet**, auch bei defekter
Befehlspipe. Die Pause im RAM überlebt keinen Neustart oder Stromausfall.
Allgemeine Anwendungen erhalten keinen künstlichen Strg+S-Tastendruck; Eltern
geben zum sicheren Speichern Zeit frei. Bewusstes Ausschalten, externe
Shutdown-Befehle und ein leerer Akku können weiterhin ungespeicherte Daten
verlieren.

## Prüfung

`PYTHONPATH=src python3 -m unittest discover -s tests -p test_emulator_session.py`
prüft einmalige Speicheraufträge, erneuten Ablauf, Zeitfreigabe während des
Speicherns, defekte Pipes sowie Pause/Fortsetzen eines echten Kindprozesses.
Die Qt-Sperrtests prüfen zusätzlich das fehlende automatische Herunterfahren
und beide Antworten auf die Ausschaltbestätigung. Ein Hardwaretest mit den
installierten RetroArch-Cores bleibt erforderlich.
