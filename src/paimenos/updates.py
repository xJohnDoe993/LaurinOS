"""Fast local update client and version comparison, shared with the parent UI."""
import json
import re
import socket

# Canonical repository and its previous name before the GitHub rename.
REPOSITORY = 'xJohnDoe993/PaimenOS'
REPOSITORY_ALIASES = {REPOSITORY, 'xJohnDoe993/LaurinOS'}
REPOSITORY_URL = 'https://github.com/' + REPOSITORY
SOCKET_PATH = '/run/paimenos-updates/control.sock'

class UpdateError(ValueError):
    pass

def version_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise UpdateError('Release-Version muss dem Format v0.61.0 entsprechen.')
    return tuple(map(int, value.removeprefix('v').split('.')))

def update_available(installed, offered):
    """Mixed component installs also offer completion to the advertised version."""
    candidate = version_key(offered)
    versions = [item.get('version', '') for item in installed.get('components', {}).values()]
    if not versions:
        versions = [installed.get('source_version', '')]
    keys = [version_key(value) for value in versions]
    # Never replace a newer installed component with an older release.
    return bool(keys) and max(keys) <= candidate and min(keys) < candidate

def update_request(action='status', tag=None, force_source=False):
    message = {'action': action}
    if tag is not None:
        message['tag'] = tag
    if force_source:
        message['force_source'] = True
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(3)
            connection.connect(SOCKET_PATH)
            connection.sendall((json.dumps(message) + '\n').encode())
            data = bytearray()
            while not data.endswith(b'\n'):
                chunk = connection.recv(4096)
                if not chunk:
                    raise UpdateError('Der Update-Dienst hat die Verbindung beendet.')
                data.extend(chunk)
                if len(data) > 256 * 1024:
                    raise UpdateError('Ungültige Antwort des Update-Dienstes.')
        result = json.loads(data)
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise UpdateError(result.get('error', 'Update-Anfrage fehlgeschlagen.') if isinstance(result, dict) else 'Ungültige Antwort.')
        return result
    except (OSError, ValueError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError('Update-Dienst nicht erreichbar. Die GitHub-Update-Funktion muss einmalig auf dem Gerät eingerichtet sein.') from exc
