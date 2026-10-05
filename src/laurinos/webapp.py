"""Firefox-Webapp-Profile mit vereinfachter, nativer Navigation."""
import os
from laurinos.paths import ASSETS_DIR
import tempfile

BAR_HEIGHT = 64
MENU_WIDTH = 160
CHROME_IMPORT = '@import url("laurinos-webapp.css");'
BEGIN = '// LaurinOS Webapp-Navigation: Anfang'
END = '// LaurinOS Webapp-Navigation: Ende'
PREFERENCES = '''user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
user_pref("browser.fullscreen.autohide", false);
user_pref("browser.tabs.drawInTitlebar", true);
user_pref("browser.startup.page", 0);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.link.open_newwindow", 1);
user_pref("browser.link.open_newwindow.restriction", 0);
'''


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.laurinos-webapp-', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_text(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return handle.read()
    except FileNotFoundError:
        return ''


def prepare_profile(profile_dir, template):
    os.makedirs(profile_dir, exist_ok=True)
    user_path = os.path.join(profile_dir, 'user.js')
    current = read_text(template) if os.path.isfile(template) else read_text(user_path)
    if BEGIN in current and END in current:
        before, rest = current.split(BEGIN, 1)
        current = before + rest.split(END, 1)[1]
    write_text(user_path, current.rstrip() + '\n' + BEGIN + '\n' + PREFERENCES + END + '\n')
    chrome_path = os.path.join(profile_dir, 'chrome', 'userChrome.css')
    current = read_text(chrome_path)
    if CHROME_IMPORT not in current:
        write_text(chrome_path, CHROME_IMPORT + '\n' + current)
    style = read_text(str(ASSETS_DIR / 'webapp.css'))
    if not style:
        raise OSError('Die Webapp-Navigationsleiste fehlt. Bitte die gemeinsame Code-Komponente aktualisieren.')
    write_text(os.path.join(profile_dir, 'chrome', 'laurinos-webapp.css'), style)


def browser_command(profile_dir, url):
    # Openbox maximiert das Fenster; Firefox reserviert selbst den Leistenplatz.
    return ['firefox-esr', '--no-remote', '--profile', profile_dir, '--new-window', url]
