# Sparsame Emulator-Darstellung

> Die hier beschriebenen Werte entsprechen dem Hardware-Profil `low` (Standard).
> Die anderen Profile ändern Auflösung und einzelne aufwendige Optionen, siehe
> [Hardware-Profile](hardware-profiles.md).

Das Profil `efficient-v1` ist eine konservative Ausgangsbasis für Notebooks wie
ein ThinkPad T450 (i5-5300U / Intel HD 5500) und neuere Geräte. Es ist keine
Benchmark-basierte Vollgeschwindigkeitsgarantie: CPU-Kühlung, Grafiktreiber, Core
und Spiel bestimmen die tatsächliche Leistung. Es gibt keine automatische
Hochstufung allein anhand des CPU-Namens.

| Systeme | Darstellung | Aufwand |
| --- | --- | --- |
| NES, SNES, GB/GBC, GBA, Mega Drive, Master System, Game Gear | Ganzzahlige Skalierung, keine bilineare Unschärfe, Seitenverhältnis vom Core | Native Emulation, keine Shader oder CPU-Bildfilter |
| PS1 | Native interne Auflösung, leicht geglättete Ausgabe im Core-Seitenverhältnis | Bestehender Beetle-Core, kein PGXP, keine erhöhte Auflösung |
| N64 | GLideN64, HLE, dynamischer Recompiler, native Auflösung (ältere Cores: 320×240), 4:3 | Kein MSAA, keine HD-Texturen; Framebuffer-Effekte bleiben für Kompatibilität aktiv |
| PSP | OpenGL, JIT, 480×272, Seitenverhältnis vom Core, 2× anisotrope Filterung | Kein Textur-Upscaling, kein Software-Rendering, kein Frameskip |

Ganzzahlige Skalierung kann größere schwarze Ränder erzeugen. Dafür bleibt die
vertikale Pixelstruktur beim Scrollen gleichmäßig. Das Core-Seitenverhältnis
verhindert ein pauschales Strecken aller Systeme auf 16:9; Handhelds behalten ihre
Geometrie. Die leichte Glättung bei den drei 3D-Systemen ist nur der günstige
Ausgabefilter und erzeugt keine zusätzlichen internen Bilddetails.

VSync und Audio-Synchronisation bleiben aktiv. Threaded Video, Hard GPU Sync,
Frame Delay, Rewind, Run-ahead und preemptive frames bleiben aus, damit keine
zusätzlichen Emulationsdurchläufe oder knappen Synchronisationsfristen entstehen.
Der Audio-Puffer beträgt 64 ms als Kompromiss für ältere Notebooks. Die tatsächliche
Gesamtlatenz hängt zusätzlich vom Audiotreiber ab. Die Monitorauflösung wird nicht
umgeschaltet. 50-Hz-PAL-Spiele auf einem festen 60-Hz-Display können weiterhin ein
regelmäßiges Bewegungsruckeln zeigen; eine Grafikoption kann diesen Unterschied
nicht ohne weitere Kompromisse aufheben.

Core-Optionen für PS1/N64/PSP werden beim Start in eine eigene Datei geschrieben.
Aktuelle PPSSPP-Optionswerte sind groß-/kleinschreibungsabhängig (`JIT`,
`disabled` statt bisher `jit`, `0`, `1` oder `off`). Der alte Backend-Schlüssel
bleibt zusätzlich für ältere Builds erhalten. Unbekannte Optionen werden vom
jeweiligen Core ignoriert; ältere Core-Versionen müssen am Gerät geprüft werden.
2D-Cores behalten ihre eigenen Standardwerte für Emulationsgenauigkeit und Farben.
Spielbezogene Core-Optionen können die Basiswerte weiter überschreiben.
Savestate-/SRAM-Pfade, Wiederaufnahme und Controllerbelegung sind unverändert.

## Geräteprüfung

Je System ein repräsentatives Spiel mindestens fünf Minuten mit Ton testen:
Scrollen, Seitenverhältnis, Audio-Aussetzer und Reaktionszeit prüfen. Bei N64/PSP
zusätzlich eine anspruchsvolle Szene verwenden. Netzbetrieb und Akkubetrieb
getrennt vergleichen; CPU-Last, Lüfter und Framerate beobachten. Danach
Bildschirmzeit-Pause, Bonuszeit, Herunterfahren/Wiederaufnahme und reguläres
Beenden prüfen. Für weitere Qualitätsstufen erst N64 640×480 oder PSP 960×544
am Gerät messen; diese erhöhen die interne Pixelzahl ungefähr auf das Vierfache.

## Quellen

- https://docs.libretro.com/guides/optimal-vsync/
- https://docs.libretro.com/library/mupen64plus/
- https://docs.libretro.com/library/ppsspp/
- https://github.com/libretro/RetroArch/blob/v1.20.0/configuration.c
- https://github.com/libretro/RetroArch/blob/v1.20.0/gfx/video_defines.h
- https://github.com/libretro/mupen64plus-libretro-nx/blob/develop/libretro/libretro_core_options.h
- https://github.com/hrydgard/ppsspp/blob/master/libretro/libretro_core_options.h

Optionsnamen und Werte am 10.10.2026 mit den Quellen abgeglichen. Lokale Tests
prüfen die erzeugten Startkonfigurationen aller unterstützten Systeme; sie messen
keine echte Emulator-Performance.

## Dolphin: optionale GameCube-/Wii-Unterstützung

Im Elternbackend unter **Emulatoren → GameCube / Wii (Dolphin) → Nachinstallieren**
oder als `dolphin` im Setup auswählbar. Nicht Teil der empfohlenen Standardauswahl.
Der vorhandene Installationsdienst verwendet den Libretro-Core und installiert
`Dolphin.zip` vom offiziellen Buildbot nach
`/usr/local/share/paimenos/retroarch-system/dolphin-emu/Sys`.
Fehlende Zusatzdateien lassen sich auch bei bereits vorhandenem Core nachinstallieren.
Die Sys-Dateien enthalten insbesondere die spielbezogenen Kompatibilitätseinstellungen.

Unterstützte Einzelabbilder: ISO, GCM, RVZ, WBFS, GCZ und CISO; maximal 9 GiB pro
Spiel, auch nach ZIP-Entpackung. ZIP enthält wie bisher genau ein Spiel ohne
Unterordner. Mehrdisc-Playlists und WiiWare-/WAD-Installation sind nicht Teil dieser
Integration. Der Upload erfolgt über den vorhandenen begrenzten Datenstrom.

Dolphin erhält native interne Auflösung (1×), Hardware-Rendering über OpenGL,
JIT (x86-64 bzw. ARM64), Dual-Core und DSP-HLE. Keine Kantenglättung, anisotrope
Filterung, HD-Texturen oder Breitbild-Hacks. Das Seitenverhältnis wird automatisch
vom Core gewählt. Synchroner Shader-Aufbau spart die Last von Ubershaders, kann
beim ersten Auftreten eines Effekts aber kurz ruckeln. Die Optionen entsprechen
dem aktuellen Libretro-Dolphin-Quellcode mit numerischen Enum-Werten; alte
Distro-Core-Builds können andere Optionen verwenden und müssen separat geprüft
werden. Es werden keine aggressiven EFB-Kompatibilitätshacks erzwungen.

Ein Gamepad wird bei GameCube als Controller verwendet. Bei Wii ist standardmäßig
eine emulierte Wiimote aktiv. Nunchuk, Classic Controller oder Bewegungs-/Zeiger-
Steuerung müssen je Spiel ggf. im RetroArch-Schnellmenü (F8) unter Steuerung
angepasst werden. Eine echte Wiimote wird nicht automatisch gekoppelt.

Bildschirmzeit-Pause und Savestate-Wiederaufnahme laufen über den bestehenden
Supervisor. Spielstände liegen im eigenen Spielverzeichnis unter saves, Core-
Systemdateien separat im gemeinsamen Systemverzeichnis. Tests prüfen die
Integration, nicht das Laden realer GameCube-/Wii-Savestates.

Auf einem i5-5300U/HD 5500 ist Vollgeschwindigkeit nicht für alle Spiele zu erwarten.
Vor Freigabe am Gerät ein GameCube- und ein Wii-Spiel mit Ton/Controller prüfen,
danach Bildschirmzeit-Pause, Bonuszeit, Herunterfahren/Wiederaufnahme und reguläres
Beenden. Auch aktuelle Grafiktreiber und Kühlung beeinflussen die Leistung.

Quellen:
- https://docs.libretro.com/library/dolphin/
- https://github.com/libretro/dolphin/blob/master/Source/Core/DolphinLibretro/Common/Options.cpp
- https://github.com/libretro/dolphin/blob/master/Source/Core/DolphinLibretro/Common/Options.h
- https://github.com/libretro/dolphin/blob/master/Source/Core/DolphinLibretro/Input.cpp
