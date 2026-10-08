# PaimenOS

<img src="assets/branding/paimenos-logo.png" alt="PaimenOS" width="240">

PaimenOS turns a Debian laptop into a children's computer with an app tile menu, screen time limits, local and web parent settings, camera/USB pictures and videos, controller navigation and optional emulators. *Paimen* is Finnish for shepherd.

[Deutsch](README.md) · [Language behaviour and English webapps](docs/localization.md)

## Install

Start with fresh Debian 12 or 13. Extract the project archive and run from its directory:

```bash
sudo bash install.sh
```

Setup asks for a parent PIN, apps, package sources and emulators. English Debian installations automatically use English throughout PaimenOS and receive an English default webapp list. Restart when setup finishes:

```bash
sudo reboot
```

Open `http://<device-IP>/` on another device on the same network to manage apps and screen time. Use the same parent PIN as on the laptop. Resume interrupted setup with `sudo bash install.sh --resume`. See `bash install.sh --help` for installation options.

Existing LaurinOS installations need a fresh installation; back up pictures, ROMs and saved games first. Existing PaimenOS installations can receive this feature with a **manual full code update from the new project directory**, using the commands below. The older backend updater does not support the new runtime API 3. Their app lists and custom names are kept; English webapps can be added in the parent area.

## Updates and ISO

Use **Updates** in the parent web area to check for and install stable GitHub releases. Close apps and games first and keep the laptop plugged in. Required Debian packages are installed if needed, requiring internet. Updates restart PaimenOS services and the children's session. Parent settings, app lists, media, ROMs and saved games are kept.

For a manual full update, run these commands from the new release directory:

```bash
bash update.sh --check
sudo bash update.sh
```

In GitHub Actions, **Build PaimenOS ISO** builds a Debian 13 hybrid ISO. Select your language in the Debian installer; PaimenOS setup starts interactively after installation and the first restart. The ISO includes the base system and setup source; selected apps and emulators need internet access.

## Development

```bash
python3 tools/build-shell-translations.py
python3 tools/build-manifest.py
python3 -B tools/check.py
```

Checks require Python 3 and Bash and run offline. Optional Flask and Qt packages enable more integration tests. A real Debian installation and hardware tests are still needed to verify the full system. German technical guides: [installation](docs/installation.md), [updates](docs/updating.md), [ISO](docs/iso.md), [architecture](docs/architecture.md).
