# Hardware-Profile

Ein Hardware-Profil legt grob fest, wie aufwendig Apps darstellen dürfen. Es wird
beim Setup gewählt und kann jederzeit geändert werden:

```bash
sudo paimenos-hardware-profile            # aktuelles Profil, Vorschlag und Auswahl 1–4
sudo paimenos-hardware-profile medium     # direkt setzen
paimenos-hardware-profile show            # anzeigen (ohne sudo)
paimenos-hardware-profile detect          # nur den Vorschlag ausgeben
```

Unbeaufsichtigtes Setup: `PAIMENOS_HARDWARE_PROFILE=ultra-low|low|medium|high`.
Ohne Angabe fragt das Setup nach und bietet einen Vorschlag an (Enter übernimmt ihn).
Bei `install.sh --resume` bleibt ein bereits gewähltes Profil erhalten.

| Profil | Gedacht für |
|---|---|
| `ultra-low` | CPU älter als Intel 5. Generation oder unterhalb von i5 (Celeron, Pentium, Atom, i3, Core M), alte AMD-APUs, weniger als ~4 GB RAM |
| `low` | z. B. Intel i5/i7 der 5.–7. Generation (ThinkPad T450), Ryzen 1000/2000, 4–6 GB RAM. **Standard** und identisch mit den bisherigen Voreinstellungen |
| `medium` | z. B. Intel i5/i7 der 8.–10. Generation, Ryzen 3000/4000 |
| `high` | Intel ab 11. Generation, Core Ultra, Ryzen ab 5000 |

Der Vorschlag wertet nur den CPU-Namen aus `/proc/cpuinfo` und den Arbeitsspeicher
aus. Weniger als ~3,5 GiB ergibt immer `ultra-low`, weniger als ~7,5 GiB höchstens
`low`. Unbekannte CPUs ergeben `low`. Er ersetzt keinen Test am Gerät: Kühlung,
Grafiktreiber und Spiel bestimmen die tatsächliche Leistung.

## Gespeichert

`/etc/paimenos/hardware-profile`, Besitzer root, für alle lesbar. Die Kindersitzung
kann das Profil nicht ändern. Fehlt die Datei oder ist sie ungültig, gilt `low`.

## Wirkung

| Bereich | ultra-low | low | medium | high | Wirksam |
|---|---|---|---|---|---|
| RetroArch allgemein | Threaded Video, 96 ms Audio-Puffer | wie bisher | wie low | wie low | nächster Spielstart |
| PS1 interne Auflösung | 1× | 1× | 2× | 4×, PGXP (nur Speicher) | nächster Spielstart |
| N64 | nativ, ohne Framebuffer-Emulation | nativ | 2× (640×480) | 3× (960×720) | nächster Spielstart |
| PSP | 480×272, ohne anisotrope Filterung, Auto-Frameskip | 480×272, 2× AF | 960×544, 4× AF | 1440×816, 8× AF | nächster Spielstart |
| Dolphin | 1× | 1× | 1× | 2× | nächster Spielstart |
| Luanti | Sichtweite 50, 30 FPS, ohne Wolken/Partikel/Shader | Sichtweite 80, 45 FPS | Sichtweite 140, 3D-Wolken, wehende Pflanzen | Sichtweite 240, dynamische Schatten, Kantenglättung | sofort (`minetest.conf`) |
| SuperTuxKart | ohne dynamische Beleuchtung, einfache Geometrie, keine animierten Figuren, kleine Texturen, 75 % Effektauflösung | ohne dynamische Beleuchtung, 2× AF | dynamische Beleuchtung, Glow, Lichtstreuung, HD-Texturen, 4× AF | zusätzlich Bloom, Lichtstrahlen, Schatten, SSAO, MLAA, 8× AF | sofort bzw. vor dem nächsten Start |
| Firefox-Webapps | 1 Inhaltsprozess, keine Animationen/weiches Scrollen, 30 FPS | 2 Prozesse, keine Animationen | 4 Prozesse | Firefox-Standard | nächster Webapp-Start |
| Kindermenü | ohne Hintergrundkreise, einfacher Kachelschatten | volle Effekte | volle Effekte | volle Effekte | nächste Anmeldung |

Ohne Framebuffer-Emulation (N64, `ultra-low`) können einzelne Spieleffekte fehlen.
Auto-Frameskip (PSP, `ultra-low`) hält die Geschwindigkeit, lässt aber Bilder aus.

### Luanti

Es werden nur die Schlüssel aus der Tabelle in `minetest.conf` gesetzt; alle anderen
Einstellungen (Name, Steuerung, Lautstärke …) bleiben erhalten. Wer im Spiel die
Grafik ändert, wird beim nächsten Profilwechsel überschrieben. Berücksichtigt werden
`~/.minetest`, `~/.luanti` und die Flatpak-Variante
`~/.var/app/org.luanti.luanti/.minetest`; verknüpfte Ordner werden nicht verfolgt.
Ist Luanti im Menü eingetragen, aber noch nie gestartet worden, wird der passende
Ordner angelegt, damit das Profil schon beim ersten Start gilt. Läuft Luanti beim
Profilwechsel, bricht die Übernahme ab, weil Luanti die Datei beim Beenden
überschreiben würde; danach den Befehl erneut ausführen. Ältere Schlüssel wie
`enable_shaders` ignorieren neuere Luanti-Versionen.

### SuperTuxKart

Geändert werden nur einzelne Attribute der Elemente `<Video>` und `<GFX>` in einer
`config.xml`, die STK selbst angelegt hat (Format `stkconfig version="8"`, geprüft
mit einer Datei von einem echten Gerät). Kommentare, Auflösung, Steuerung und alle
anderen Einstellungen bleiben unverändert. Es wird nie eine eigene Datei erzeugt:
Vor dem allerersten Start existiert keine Konfiguration, dann gelten die STK-Standards.
Das Kindermenü wendet das Profil deshalb einmalig vor dem nächsten STK-Start an.
Welches Profil bereits übernommen wurde, steht in
`~/.local/state/paimenos/hardware-profile-applied.json`; eigene Änderungen im Spiel
bleiben so bis zum nächsten Profilwechsel erhalten. Berücksichtigt werden Flatpak
(`~/.var/app/net.supertuxkart.SuperTuxKart/config/supertuxkart/config-*/`) und Debian
(`~/.config/supertuxkart/config-*/`). Läuft STK, wird nicht geändert, weil STK die
Datei beim Beenden vollständig neu schreibt.

## Nicht abgedeckt

- **GCompris** bringt eine eigene Automatik mit; das Konfigurationsformat wird erst
  nach einer Prüfung auf echten Geräten eingebunden.
- Tux Paint, LibreOffice, GIMP, Geany und VLC haben keine nennenswerten
  Grafikstufen.
- System-Einstellungen (TLP, ZRAM, Auflösung) bleiben unabhängig vom Profil.

## Geräteprüfung

Je Profil ein N64- und ein PSP-Spiel sowie Luanti und SuperTuxKart fünf Minuten spielen und
Framerate, Ton und Lüfter beobachten. Nach `sudo paimenos-hardware-profile high`
und Rückkehr zu `low` müssen eigene Luanti-Einstellungen außerhalb der Tabelle
erhalten bleiben.
