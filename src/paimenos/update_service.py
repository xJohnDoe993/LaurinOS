"""Fixed-source release checks and a separate, restart-safe installation worker."""
import argparse
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time

from paimenos import release_source
from paimenos.updates import REPOSITORY_URL, SOCKET_PATH, UpdateError, update_available

BASE = Path('/usr/local/lib/paimenos')
STATE_DIR = Path('/var/lib/paimenos/updates')
CACHE_DIR = Path('/var/cache/paimenos-updates')
JOB_UNIT = 'paimenos-update-job.service'
CHECK_INTERVAL = 6 * 60 * 60
BUSY = {'queued', 'running'}


class StateStore:
    """Short locked transactions shared by the daemon and independent worker."""
    def __init__(self, directory=STATE_DIR):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextmanager
    def transaction(self, write=True):
        with (self.directory / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = self.directory / 'state.json'
            state = json.loads(path.read_text()) if path.exists() else {}
            yield state
            if not write:
                return
            fd, name = tempfile.mkstemp(prefix='.state-', dir=self.directory)
            try:
                with os.fdopen(fd, 'w') as out:
                    json.dump(state, out, ensure_ascii=False)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(name, path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)

    def read(self):
        with self.transaction(write=False) as state:
            return state.copy()


def installed_record(base=BASE):
    current = base / 'current'
    if not current.is_symlink():
        raise UpdateError('Die modulare PaimenOS-Installation fehlt.')
    return json.loads((current / 'installed.json').read_text())


def job_active():
    result = subprocess.run(['systemctl', 'is-active', JOB_UNIT], capture_output=True, text=True)
    return result.stdout.strip() in {'active', 'activating', 'deactivating'}


class UpdateManager:
    def __init__(self, store, base=BASE):
        self.store, self.base = store, base
        self.check_lock = threading.Lock()
        with store.transaction() as state:
            state['checking'] = False

    def status(self):
        state = self.store.read()
        installed = installed_record(self.base)
        release = state.get('release')
        available = bool(release and update_available(installed, release['version']))
        return {'ok': True, 'repository': REPOSITORY_URL, 'current_version': installed['source_version'],
                'component_versions': sorted({item['version'] for item in installed['components'].values()}),
                'release': release, 'update_available': available, 'checking': state.get('checking', False),
                'last_checked': state.get('last_checked'), 'check_error': state.get('check_error'), 'job': state.get('job')}

    def check(self, automatic=False, force_source=False):
        if not self.check_lock.acquire(blocking=False):
            return
        started = False
        try:
            with self.store.transaction() as state:
                elapsed = time.time() - state.get('last_attempt', 0)
                interval = CHECK_INTERVAL if automatic else 60
                if elapsed < interval or state.get('job', {}).get('status') in BUSY:
                    return
                state.update(checking=True, last_attempt=time.time(), check_error=None)
            threading.Thread(target=self._check, args=(force_source,), daemon=True).start()
            started = True
        finally:
            if not started:
                self.check_lock.release()

    def _check(self, force_source=False):
        try:
            release = release_source.release_metadata(force_source=True) if force_source else release_source.release_metadata()
            with self.store.transaction() as state:
                state.update(release=release, last_checked=time.time(), check_error=None)
        except Exception as exc:
            with self.store.transaction() as state:
                state['check_error'] = str(exc)[:1000]
        finally:
            try:
                with self.store.transaction() as state:
                    state['checking'] = False
            finally:
                self.check_lock.release()

    def install(self, tag, force_source=False):
        job_id = secrets.token_hex(12)
        with self.store.transaction() as state:
            if state.get('job', {}).get('status') in BUSY:
                raise UpdateError('Ein PaimenOS-Update läuft bereits.')
            release = state.get('release')
            if not release or release['tag'] != tag or not update_available(installed_record(self.base), release['version']):
                raise UpdateError('Dieses Release wird nicht mehr angeboten. Bitte erneut prüfen.')
            if release.get('source_override') and not force_source:
                raise UpdateError('Abweichende Release-Quelle vor der Installation ausdrücklich bestätigen.')
            if job_active():
                raise UpdateError('Ein Update-Auftrag läuft bereits.')
            state['job'] = {'id': job_id, 'status': 'queued', 'tag': tag, 'release': release,
                            'force_source': bool(release.get('source_override') and force_source),
                            'message': 'Update wird vorbereitet.', 'progress': 0, 'updated_at': time.time()}
        # The worker has its own cgroup, so restarting this daemon cannot kill it.
        subprocess.run(['systemctl', 'reset-failed', JOB_UNIT], check=False, capture_output=True)
        try:
            subprocess.run(['systemd-run', '--quiet', '--collect', '--unit=' + JOB_UNIT,
                            '--property=Type=exec', '--property=UMask=0077', '--property=Nice=10',
                            '/usr/bin/python3', '-I', str(BASE / 'current/run.py'),
                            'update_service', '--apply', job_id], check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            update_job(self.store, job_id, status='failed', message='Update-Auftrag konnte nicht gestartet werden.')
            raise UpdateError('Update-Auftrag konnte nicht gestartet werden.') from exc

    def recover(self):
        state = self.store.read()
        job = state.get('job', {})
        if job.get('status') in BUSY and time.time() - job.get('updated_at', 0) > 30 and not job_active():
            update_job(self.store, job['id'], status='failed',
                       message='Update wurde unterbrochen. Aktuelle Version prüfen und Update erneut starten. Bei einem Stromausfall kann eine manuelle Wiederherstellung nötig sein.')


def update_job(store, job_id, **fields):
    with store.transaction() as state:
        job = state.get('job', {})
        if job.get('id') != job_id:
            raise UpdateError('Update-Auftrag ist nicht mehr aktuell.')
        job.update(fields, updated_at=time.time())


@contextmanager
def maintenance_locks():
    with open('/run/paimenos-maintenance.lock', 'a') as maintenance, open('/run/paimenos-emulator-install.lock', 'a') as emulator:
        for handle in (maintenance, emulator):
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise UpdateError('Eine andere Wartung oder Emulator-Installation läuft. Bitte deren Abschluss abwarten.') from exc
        yield


def load_deployer(base):
    # Use the currently installed trusted deployer, never execute downloaded tools.
    spec = importlib.util.spec_from_file_location('paimenos_deploy', base / 'current/tools/deploy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_job(store, job_id, base=BASE, cache=CACHE_DIR):
    job = store.read().get('job', {})
    if job.get('id') != job_id or job.get('status') != 'queued':
        raise UpdateError('Kein passender Update-Auftrag vorhanden.')
    expected = job['release']
    try:
        with maintenance_locks():
            deploy = load_deployer(base)
            update_job(store, job_id, status='running', message='Release wird auf GitHub geprüft.', progress=5)
            release = (release_source.release_metadata(expected['tag'], force_source=True)
                       if job.get('force_source') is True else release_source.release_metadata(expected['tag']))
            if release['archive'] != expected['archive'] or release['checksum'] != expected['checksum']:
                raise UpdateError('Die Release-Dateien wurden verändert. Bitte erneut nach Updates suchen.')
            if not update_available(installed_record(base), release['version']):
                raise UpdateError('Die installierte Version ist bereits aktuell oder neuer.')
            cache.mkdir(parents=True, exist_ok=True, mode=0o700)
            download_space = release_source.MAX_ARCHIVE + release_source.MAX_UNPACKED
            staging_space = 2 * release_source.MAX_UNPACKED
            shared_disk = cache.stat().st_dev == base.stat().st_dev
            required_cache = download_space + staging_space if shared_disk else download_space
            if shutil.disk_usage(cache).free < required_cache or shutil.disk_usage(base).free < staging_space:
                raise UpdateError('Nicht genügend freier Speicher für Download und sichere Vorbereitung.')
            with tempfile.TemporaryDirectory(prefix='release-', dir=cache) as folder:
                root = Path(folder)
                archive = root / release['archive']['name']
                last_progress = [-1, 0.0]
                def progress(count, total):
                    value = min(65, 10 + int(55 * count / release['archive']['size']))
                    if value != last_progress[0] and time.monotonic() - last_progress[1] >= 0.5:
                        update_job(store, job_id, message='Update wird heruntergeladen.', progress=value)
                        last_progress[:] = [value, time.monotonic()]
                release_source.download(release['archive']['url'], archive, progress=progress)
                if archive.stat().st_size != release['archive']['size']:
                    raise UpdateError('Die Download-Größe stimmt nicht mit dem Release überein.')
                checksum = release_source.download(release['checksum']['url'], limit=4096).decode('ascii')
                update_job(store, job_id, message='Prüfsumme und Archiv werden geprüft.', progress=70)
                release_source.verify_archive(archive, checksum, release['archive'])
                source = release_source.extract_archive(archive, root / 'source')
                if (source / 'VERSION').read_text().strip() != release['version']:
                    raise UpdateError('Archiv-Version und Release-Tag stimmen nicht überein.')
                update_job(store, job_id, message='Neue Code-Version wird vorbereitet.', progress=80)
                staged, names = deploy.stage_release(source, base)
                def package_progress(message):
                    update_job(store, job_id, message=message, progress=85)
                update_job(store, job_id, message='Benötigte Debian-Pakete werden geprüft.', progress=82)
                deploy.ensure_packages(staged, package_progress)
                update_job(store, job_id, message='Code wird aktiviert. Dienste und Kindersitzung starten neu.', progress=90)
                deploy.activate(base, staged, units='services' in names, packages_prepared=True)
                update_job(store, job_id, status='succeeded', message='Update erfolgreich installiert.', progress=100)
    except Exception as exc:
        update_job(store, job_id, status='failed', message='Update fehlgeschlagen: ' + str(exc)[:1500])
        raise


def authorized_peer(connection):
    _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
    return uid in {0, pwd.getpwnam('kids').pw_uid}


class UpdateHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(3)
        try:
            if not authorized_peer(self.connection):
                raise UpdateError('Update-Anfrage nicht erlaubt.')
            line = self.rfile.readline(4097)
            if len(line) > 4096 or not line.endswith(b'\n'):
                raise UpdateError('Ungültige Update-Anfrage.')
            message = json.loads(line)
            if not isinstance(message, dict) or set(message) - {'action', 'tag', 'force_source'}:
                raise UpdateError('Ungültige Update-Anfrage.')
            if 'force_source' in message and type(message['force_source']) is not bool:
                raise UpdateError('Ungültige Quellenbestätigung.')
            force_source = message.get('force_source', False)
            action = message.get('action')
            manager = self.server.manager
            if action == 'check':
                manager.check(force_source=True) if force_source else manager.check()
            elif action == 'install':
                manager.install(message.get('tag'), force_source=True) if force_source else manager.install(message.get('tag'))
            elif action != 'status':
                raise UpdateError('Unbekannte Update-Aktion.')
            result = manager.status()
        except Exception as exc:
            result = {'ok': False, 'error': str(exc)[:1500]}
        try:
            self.wfile.write((json.dumps(result, ensure_ascii=False) + '\n').encode())
        except OSError:
            pass


def serve(store):
    manager = UpdateManager(store)
    path = Path(SOCKET_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o750)
    os.chown(path.parent, 0, pwd.getpwnam('kids').pw_gid)
    path.unlink(missing_ok=True)
    with socketserver.UnixStreamServer(str(path), UpdateHandler) as server:
        server.manager = manager
        os.chown(path, 0, pwd.getpwnam('kids').pw_gid)
        path.chmod(0o660)
        server.timeout = 1
        last_tick = 0
        while True:
            if time.monotonic() - last_tick >= 60:
                manager.recover()
                manager.check(automatic=True)
                last_tick = time.monotonic()
            server.handle_request()


def main():
    parser = argparse.ArgumentParser(description='PaimenOS GitHub-Release-Updater')
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--apply', metavar='JOB_ID')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Der Update-Dienst benötigt root.')
    store = StateStore()
    if args.apply:
        apply_job(store, args.apply)
    else:
        serve(store)


if __name__ == '__main__':
    main()
