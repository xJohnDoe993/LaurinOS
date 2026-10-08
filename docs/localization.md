# Deutsch und Englisch / German and English

PaimenOS verwendet die Debian-Systemsprache: `en_US.UTF-8`, `en_GB.UTF-8` und andere `en_*`-Locales wählen Englisch. Deutsche und bisher nicht unterstützte Locales verwenden Deutsch. Die Einstellung gilt für Setup, Kindermenü, Kamera/Bilder/Videos, Bildschirmzeit, lokale Elternverwaltung, Webbackend, WLAN/Bluetooth, Controller und Emulator-/Update-Meldungen.

PaimenOS reads `/etc/default/locale`, then `/etc/locale.conf`, preferring `LC_ALL`, `LC_MESSAGES`, then `LANG` in each file. If neither file defines a locale, the same environment variables are used. `C`, `C.UTF-8` and unknown languages retain the German default. This also works when sudo or a systemd service receives `C.UTF-8` despite an English Debian installation. Locale files are read as data, never executed.

The setup does not change Debian's language, timezone or keyboard layout. The ISO's Debian installer still offers its normal language choice. English selection is applied to the interactive PaimenOS setup after the first restart. Qt dialogs, menu dates and Firefox's webapp language follow the detected language. Native apps receive the configured Debian message locale; their own translations depend on the app's available language support.

For a one-off English setup or preview:

```bash
sudo env PAIMENOS_LANGUAGE=en bash install.sh
PAIMENOS_LANGUAGE=en python3 run.py menu
```

Use `de` to force German. The override is optional; an English Debian installation needs no override. A process restart is required after changing the system language. The parent backend follows the device's language, including when opened on a phone; it does not infer its language from the phone's browser.

## Initial webapps

The German list remains in `data/default-webapps.json`. New English installations use `data/default-webapps.en.json`:

| App | Purpose | Official page |
|---|---|---|
| PBS KIDS Games | Children's games | https://pbskids.org/games/ |
| LearnEnglish Kids | English games, songs and stories | https://learnenglishkids.britishcouncil.org/ |
| NASA Space Place | Science and space activities | https://spaceplace.nasa.gov/ |
| Blockly Games | Visual programming games; English selected explicitly | https://blockly.games/?lang=en |
| Scratch – Create | Direct editor access; English selected explicitly | https://scratch.mit.edu/projects/editor/?locale=en |

Bundled SVG letter icons are available offline. These are PaimenOS shortcuts, not provider logos. The websites require internet access and remain external services; regional restrictions and future site changes are outside PaimenOS's control.

App IDs, Firefox profiles and saved data remain stable. Parent-defined app names are preserved. Only recognised built-in Camera and Shut down titles are translated at display time. An update or subsequent language change does not replace the parent's existing webapp list. Add or remove webapps in the parent area if an existing installation needs the English choices.

## Updating and adding translations

Install this feature with a full code update. Runtime API 3 prevents partial updates from mixing translated components with the older runtime that lacks the translation module. Parent settings, apps, media, ROMs and saved games are kept.

The updater installed with runtime API 2 cannot apply API 3 through the web backend. For this first transition, extract the new project archive on the device and run from that new directory:

```bash
bash update.sh --check
sudo bash update.sh
```

Do not use `--component` for this transition. No fresh Debian installation is needed for an existing PaimenOS system. Subsequent compatible releases can use the parent backend again.

German source messages are keys in `assets/i18n/en.json`. Python and Jinja use `t(message, **values)`; browser code uses `PaimenTranslate(message)`. Format placeholders must match between languages. Do not translate app IDs, API keys, commands, filenames or machine-readable statuses.

The early Bash installer uses a generated subset of the same catalogue, so Python is not required before asking for the parent PIN. After editing installer messages or adding files:

```bash
python3 tools/build-shell-translations.py
python3 tools/build-manifest.py
python3 -B tools/check.py
```

Locale, placeholder, default-webapp and backend rendering tests are in `tests/test_i18n.py`. Flask enables additional page and JavaScript validation; Qt enables native dialog checks. Tests are offline and do not install packages or access hardware.
