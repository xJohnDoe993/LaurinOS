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
Neustart wiederhergestellt. Diese Vorgaben werden auch auf bestehenden
Webapp-Profilen beim nächsten Start angewendet. Der normale Firefox außerhalb
des Kinder-Menüs ist davon nicht betroffen.

Diese Änderung verbessert die Wiederverwendung gespeicherter Website-Dateien
und den Start-/Schließablauf. Sie behält keine laufende Seite im Hintergrund:
Firefox und die Website starten weiterhin neu. Eine Verringerung der Ladezeit
auf dem jeweiligen Gerät muss gemessen werden.
