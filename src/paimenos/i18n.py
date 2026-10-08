"""German/English UI strings, selected from Debian's configured message locale.

System services and sudo often receive C.UTF-8 instead of the installer's locale.
Read Debian's locale files without executing them. An explicit
PAIMENOS_LANGUAGE=de/en override is useful for previews and automated tests.
"""
from functools import lru_cache
import json
import os
from pathlib import Path
import re
from paimenos.paths import ASSETS_DIR

# Debian 13's installed locale takes precedence over legacy live-image defaults.
# Debian 12 still uses /etc/default/locale.
LOCALE_FILES = (Path('/etc/locale.conf'), Path('/etc/default/locale'))


@lru_cache(maxsize=1)
def configured_locale():
    for path in LOCALE_FILES:
        try:
            text = path.read_text(encoding='utf-8')
        except OSError:
            continue
        values = {}
        for line in text.splitlines():
            match = re.fullmatch(r'\s*(?:export\s+)?(LANG|LC_MESSAGES|LC_ALL)\s*=\s*(.*?)\s*', line)
            if match:
                value = match[2].split(' #', 1)[0].strip().strip('\"\x27')
                if value:
                    values[match[1]] = value
        for name in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
            if values.get(name):
                return values[name]
    return ''


def message_locale():
    return configured_locale() or next((os.environ[key] for key in
        ('LC_ALL', 'LC_MESSAGES', 'LANG') if os.environ.get(key)), '')


def language():
    override = os.environ.get('PAIMENOS_LANGUAGE', '').lower()
    if override in ('de', 'en'):
        return override
    value = message_locale()
    return 'en' if re.match(r'^en(?:[_.@-]|$)', value, re.I) else 'de'


@lru_cache(maxsize=1)
def english_catalog():
    return json.loads((ASSETS_DIR / 'i18n/en.json').read_text(encoding='utf-8'))


def t(message, **values):
    translated = english_catalog().get(message, message) if language() == 'en' else message
    return translated.format(**values) if values else translated


def browser_locale():
    return 'en' if language() == 'en' else 'de'


def regional_locale():
    """A BCP 47 locale for dates in the parent backend, retaining e.g. en_GB."""
    value = message_locale()
    if value.lower().startswith(language() + '_'):
        return value.split('.', 1)[0].split('@', 1)[0].replace('_', '-')
    return 'en-GB' if language() == 'en' else 'de-DE'


def application_environment():
    """Pass Debian's message locale to native apps even from a C.UTF-8 service."""
    environment = dict(os.environ)
    value = message_locale()
    if value and value.lower().startswith(tuple(language() + separator for separator in ('_', '-', '.'))):
        environment['LC_MESSAGES'] = value
        environment['LANG'] = value
        # LC_ALL=C in the launching service must not hide the system language.
        environment.pop('LC_ALL', None)
    environment['LANGUAGE'] = language()
    return environment


def setup_qt(application):
    """Translate native Qt buttons, file dialogs and accessibility strings too."""
    from PyQt5.QtCore import QLibraryInfo, QLocale, QTranslator
    QLocale.setDefault(QLocale(regional_locale()))
    previous = getattr(application, '_paimenos_translator', None)
    if previous is not None:
        application.removeTranslator(previous)
    translator = QTranslator(application)
    translator.load('qtbase_' + language(), QLibraryInfo.location(QLibraryInfo.TranslationsPath))
    application.installTranslator(translator)
    application._paimenos_translator = translator


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--language']:
        print(language())
    elif sys.argv[1:]:
        print(t(sys.argv[1]), end='')
