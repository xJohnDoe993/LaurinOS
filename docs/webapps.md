# Firefox-Webapps

Jede Webapp behält ihr eigenes Profil unter `~/.mozilla/paimenos-webapps/`.
Festplatten- und Arbeitsspeicher-Cache sind eingeschaltet; die Größe des
Festplatten-Caches verwaltet Firefox automatisch. Cookies, Website-Speicher
und Cache werden beim Menüwechsel nicht gelöscht. Die Cache-Regeln der
Website bleiben wirksam.

Die Firefox-Startseite, deren Vorladen, Top-Sites-Feeds und automatische
Seiten-Vorschaubilder sind in diesen Profilen abgeschaltet. Diese Funktionen
werden im Kinder-Menü nicht verwendet und können zusätzliche Seiten im
Hintergrund laden. Unveränderte Profil-/CSS-Dateien werden beim Wiederstart
nicht erneut geschrieben.

Der Start wird durch `paimenos.browser` überwacht. Ein zusätzlicher Start
desselben Profils wird verhindert. Der Menüknopf fordert zunächst normales
Fensterschließen an, damit Firefox seine Daten speichern kann. Erst bei einem
hängenden Browser folgt nach acht Sekunden eine begrenzte Wiederherstellung
mit SIGTERM/SIGKILL für dessen eigene Prozessgruppe. Das Menü wartet auf das
Ende und die Freigabe der Profil-Sperre.

Nach einem früheren Menüabsturz kann ein verwaister Firefox des gleichen
Benutzers und mit genau diesem Profil automatisch geschlossen werden. Andere
Profile bleiben unangetastet. Sperrdateien werden nicht gelöscht. Bei einer
nicht eindeutig zuordenbaren Sperre startet kein zweiter Firefox.

Alte Tabs werden weder nach einem Absturz noch nach einem Betriebssystem-
Neustart wiederhergestellt. Zusätzlich ist der separate Hinweis „Open previous
tabs? You can restore your previous session…“ über
`browser.startup.couldRestoreSession.count = -1` deaktiviert. Firefox zeigt
diesen Hinweis sonst beim zweiten geeigneten Start unabhängig von der
automatischen Wiederherstellung an. Diese Vorgaben werden auch auf bestehenden
Webapp-Profilen beim nächsten Start angewendet. Der normale Firefox außerhalb
des Kinder-Menüs ist davon nicht betroffen.

Diese Änderung verbessert die Wiederverwendung gespeicherter Website-Dateien
und den Start-/Schließablauf. Sie behält keine laufende Seite im Hintergrund:
Firefox und die Website starten weiterhin neu. Eine Verringerung der Ladezeit
auf dem jeweiligen Gerät muss gemessen werden.

## Bildschirmzeit und Elternansicht

Bei abgelaufener Bildschirmzeit verschwindet „Zum Menü“. Auch ein bereits
eingereihter Klick prüft die aktuellen Eltern-Einstellungen und kann die
Webapp dann nicht schließen. Das Kindermenü prüft dieselbe Sperre vor jedem
App-Start, bei Controller-/Tastatureingaben, beim Menü-Hotkey und bei der
Rückkehr aus einer App oder der Kameraansicht.

Sperrbildschirm, Eltern-PIN und Elternbereich liegen auf deckenden
Vollbildflächen. Weitere angeschlossene Bildschirme werden ebenfalls
abgedeckt. Der Menüknopf sowie Lautstärke-/Helligkeitsanzeigen bleiben während
dieser Ansichten ausgeblendet. Dialoge zur Eltern-PIN und Zeitzugabe bleiben
über der Vollbildfläche bedienbar. Die Fensterpriorität wird durch eine
Prozesssperre angezeigt; ein Prozessabbruch hinterlässt keine dauerhafte Sperre.

Zusätzliche Elternzeit bzw. der Tageswechsel geben die Kinderansicht wieder
frei. Solange die Elternansicht offen ist, bleibt sie im Vordergrund. Das
Ändern des Tageslimits während eines geöffneten Elterndialogs öffnet keinen
zweiten Sperrbildschirm über diesem Dialog.
