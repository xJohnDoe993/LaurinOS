import copy
from contextlib import nullcontext
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from laurinos import release_source as source, update_service as service, updates


def release_payload(version='0.62.0'):
    tag = 'v' + version
    name = 'LaurinOS-' + version + '.zip'
    return {'tag_name': tag, 'name': 'Release ' + tag, 'body': '<script>untrusted notes</script>',
            'draft': False, 'prerelease': False, 'published_at': '2026-10-05T12:00:00Z',
            'assets': [{'name': filename, 'state': 'uploaded', 'size': 128,
                        'browser_download_url': updates.REPOSITORY_URL + '/releases/download/' + tag + '/' + filename}
                       for filename in [name, name + '.sha256']]}


def receipt(version='0.61.0'):
    return {'source_version': version, 'components': {'shared': {'version': version}, 'backend': {'version': version}}}


class VersionTests(unittest.TestCase):
    def test_numeric_order_and_mixed_install_completion(self):
        self.assertTrue(updates.update_available(receipt('0.9.0'), '0.10.0'))
        self.assertFalse(updates.update_available(receipt(), '0.61.0'))
        mixed = receipt()
        mixed['components']['shared']['version'] = '0.62.0'
        self.assertTrue(updates.update_available(mixed, '0.62.0'))
        self.assertFalse(updates.update_available(mixed, '0.61.0'))
    def test_prerelease_and_non_semver_are_rejected(self):
        for value in ['v1.2.3-rc.1', 'v1.2', '../1.2.3', '01.2.3', None]:
            with self.subTest(value=value), self.assertRaises(updates.UpdateError):
                updates.version_key(value)


class ReleaseTests(unittest.TestCase):
    def test_stable_release_requires_matching_assets_from_fixed_repo(self):
        parsed = source.parse_release(release_payload())
        self.assertEqual(parsed['version'], '0.62.0')
        cases = []
        for field in ['draft', 'prerelease']:
            payload = release_payload(); payload[field] = True; cases.append(payload)
        payload = release_payload(); payload['assets'].pop(); cases.append(payload)
        payload = release_payload(); payload['assets'][0]['browser_download_url'] = 'https://github.com/other/repo/releases/download/v0.62.0/file.zip'; cases.append(payload)
        payload = release_payload(); payload['assets'][0]['size'] = source.MAX_ARCHIVE + 1; cases.append(payload)
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(updates.UpdateError):
                source.parse_release(payload)
        with self.assertRaises(updates.UpdateError):
            source.parse_release(release_payload(), expected_tag='v0.63.0')
    def test_redirects_require_https_and_known_asset_hosts(self):
        for url in ['http://github.com/a', 'https://example.com/a', 'https://github.com:444/a', 'https://user:secret@github.com/a']:
            with self.subTest(url=url), self.assertRaises(updates.UpdateError): source.trusted_url(url)
        self.assertEqual(source.trusted_url('https://release-assets.githubusercontent.com/a'), 'https://release-assets.githubusercontent.com/a')
    def test_checksum_rejects_tampering_wrong_filename_and_github_digest(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            archive = Path(folder) / 'test.zip'; archive.write_bytes(b'release')
            digest = hashlib.sha256(b'release').hexdigest()
            asset = {'name': 'test.zip', 'digest': 'sha256:' + digest}
            source.verify_archive(archive, digest + '  test.zip', asset)
            for checksum in [digest + '  other.zip', '0' * 64 + '  test.zip', digest + '  test.zip\n' + digest + '  test.zip']:
                with self.assertRaises(updates.UpdateError): source.verify_archive(archive, checksum, asset)
            with self.assertRaises(updates.UpdateError): source.verify_archive(archive, digest + '  test.zip', {'name': 'test.zip', 'digest': 'sha256:bad'})
    def test_zip_rejects_traversal_symlinks_and_duplicate_names_before_writing(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            root = Path(folder)
            cases = ['LaurinOS/../../outside', '/LaurinOS/VERSION', 'LaurinOS\\VERSION', 'Other/VERSION']
            for name in cases:
                archive = root / 'bad.zip'
                with zipfile.ZipFile(archive, 'w') as package: package.writestr(name, b'bad')
                with self.assertRaises(updates.UpdateError): source.extract_archive(archive, root / 'out')
                self.assertFalse((root / 'out').exists())
            link = zipfile.ZipInfo('LaurinOS/link'); link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, 'w') as package: package.writestr(link, '../../etc/shadow')
            with self.assertRaises(updates.UpdateError): source.extract_archive(archive, root / 'out')
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('LaurinOS/VERSION', '0.62.0')
                package.writestr('LaurinOS/./VERSION', '0.62.0')
            with self.assertRaises(updates.UpdateError): source.extract_archive(archive, root / 'out')
    def test_download_size_limit_and_truncated_response(self):
        class Response(io.BytesIO):
            headers = {'Content-Length': '10'}
        with patch.object(source, 'open_url', return_value=Response(b'123')):
            with self.assertRaises(updates.UpdateError): source.download('https://github.com/a')
        with patch.object(source, 'open_url', return_value=Response(b'123')):
            with self.assertRaises(updates.UpdateError): source.download('https://github.com/a', limit=2)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.store = service.StateStore(Path(self.temp.name) / 'state')
        self.manager = service.UpdateManager(self.store)
        self.record_patch = patch.object(service, 'installed_record', return_value=receipt())
        self.record_patch.start()
    def tearDown(self):
        self.record_patch.stop(); self.temp.cleanup()
    def test_status_uses_cache_without_network_and_offline_check_preserves_offer(self):
        release = source.parse_release(release_payload())
        with self.store.transaction() as state: state.update(release=release, last_checked=123)
        with patch.object(source, 'release_metadata', side_effect=updates.UpdateError('offline')) as network:
            self.assertTrue(self.manager.status()['update_available'])
            network.assert_not_called()
            self.manager.check()
            self.assertTrue(self.manager.check_lock.acquire(timeout=2))
            self.manager.check_lock.release()
        status = self.manager.status()
        self.assertEqual(status['release'], release)
        self.assertEqual(status['last_checked'], 123)
        self.assertEqual(status['check_error'], 'offline')
        self.assertFalse(status['checking'])
    def test_check_throttle_and_no_release_response(self):
        with self.store.transaction() as state: state['last_attempt'] = time.time()
        with patch.object(source, 'release_metadata') as network:
            self.manager.check(); network.assert_not_called()
        with self.store.transaction() as state: state['last_attempt'] = 0
        with patch.object(source, 'release_metadata', return_value=None):
            self.manager.check()
            self.assertTrue(self.manager.check_lock.acquire(timeout=2)); self.manager.check_lock.release()
        self.assertFalse(self.manager.status()['update_available'])
    def test_install_pins_cached_tag_and_launches_separate_worker_once(self):
        with self.store.transaction() as state: state['release'] = source.parse_release(release_payload())
        with patch.object(service, 'job_active', return_value=False), patch.object(service.subprocess, 'run') as run:
            with self.assertRaises(updates.UpdateError): self.manager.install('v9.9.9')
            run.assert_not_called()
            self.manager.install('v0.62.0')
            command = run.call_args.args[0]
            self.assertEqual(command[0], 'systemd-run')
            self.assertIn('--collect', command)
            job = self.store.read()['job']; self.assertEqual(job['status'], 'queued')
            self.assertEqual(command[-1], job['id'])
            with self.assertRaises(updates.UpdateError): self.manager.install('v0.62.0')
            self.assertEqual(run.call_count, 2)
    def test_worker_start_failure_is_persisted(self):
        with self.store.transaction() as state: state['release'] = source.parse_release(release_payload())
        with patch.object(service, 'job_active', return_value=False), patch.object(service.subprocess, 'run', side_effect=[Mock(), subprocess.CalledProcessError(1, 'systemd-run')]):
            with self.assertRaises(updates.UpdateError): self.manager.install('v0.62.0')
        self.assertEqual(self.store.read()['job']['status'], 'failed')
    def test_recovery_marks_abandoned_job_but_leaves_running_worker(self):
        with self.store.transaction() as state: state['job'] = {'id': 'test', 'status': 'running', 'updated_at': 0}
        with patch.object(service, 'job_active', return_value=True): self.manager.recover()
        self.assertEqual(self.store.read()['job']['status'], 'running')
        with patch.object(service, 'job_active', return_value=False): self.manager.recover()
        self.assertEqual(self.store.read()['job']['status'], 'failed')
    def test_daemon_restart_preserves_worker_job(self):
        with self.store.transaction() as state: state.update(checking=True, job={'id': 'live', 'status': 'running'})
        service.UpdateManager(self.store)
        self.assertEqual(self.store.read()['job']['status'], 'running')
        self.assertFalse(self.store.read()['checking'])


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent); self.root = Path(self.temp.name)
        self.base = self.root / 'installed'; self.base.mkdir()
        self.store = service.StateStore(self.root / 'state')
        spec = importlib.util.spec_from_file_location('test_update_deploy', ROOT / 'tools/deploy.py')
        self.deploy = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.deploy)
        self.old, _ = self.deploy.stage_release(ROOT, self.base)
        self.deploy.activate(self.base, self.old, live=False)
        self.new_source = self.root / 'source'
        shutil.copytree(ROOT, self.new_source, ignore=shutil.ignore_patterns('.git', 'dist', '__pycache__'))
        (self.new_source / 'VERSION').write_text('0.62.0\n')
        manifest = json.loads((self.new_source / 'manifest.json').read_text()); manifest['version'] = '0.62.0'
        (self.new_source / 'manifest.json').write_text(json.dumps(manifest))
        self.archive = self.root / 'LaurinOS-0.62.0.zip'
        with zipfile.ZipFile(self.archive, 'w', compression=zipfile.ZIP_DEFLATED) as package:
            for file in self.new_source.rglob('*'):
                if file.is_file(): package.write(file, 'LaurinOS/' + str(file.relative_to(self.new_source)))
        self.checksum = hashlib.sha256(self.archive.read_bytes()).hexdigest() + '  ' + self.archive.name + '\n'
        payload = release_payload(); payload['assets'][0]['size'] = self.archive.stat().st_size; payload['assets'][1]['size'] = len(self.checksum)
        self.release = source.parse_release(payload)
        with self.store.transaction() as state:
            state['job'] = {'id': 'job', 'status': 'queued', 'release': self.release, 'tag': self.release['tag']}
        self.patches = [patch.object(service, 'maintenance_locks', return_value=nullcontext()),
                        patch.object(service, 'load_deployer', return_value=self.deploy),
                        patch.object(source, 'release_metadata', return_value=self.release),
                        patch.object(source, 'download', side_effect=self.download),
                        patch.object(self.deploy, 'install_launchers'), patch.object(self.deploy, 'apply_units'),
                        patch.object(self.deploy, 'restart_services')]
        for item in self.patches: item.start()
    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()
    def download(self, url, target=None, **kwargs):
        if target is None: return self.checksum.encode()
        shutil.copyfile(self.archive, target)
    def apply(self): service.apply_job(self.store, 'job', self.base, self.root / 'cache')
    def test_verified_release_stages_and_activates_then_records_success(self):
        data = self.root / 'home/kids/save'; data.parent.mkdir(parents=True); data.write_bytes(b'parent and save data')
        self.apply()
        self.assertNotEqual((self.base / 'current').resolve(), self.old)
        self.assertEqual(service.installed_record(self.base)['source_version'], '0.62.0')
        self.assertEqual((self.base / 'previous').resolve(), self.old)
        self.assertEqual(data.read_bytes(), b'parent and save data')
        self.assertEqual(self.store.read()['job']['status'], 'succeeded')
        self.assertEqual(self.store.read()['job']['progress'], 100)
        self.assertEqual(list((self.root / 'cache').iterdir()), [])
    def test_tampering_and_changed_assets_never_activate(self):
        self.checksum = '0' * 64 + '  ' + self.archive.name
        with self.assertRaises(updates.UpdateError): self.apply()
        self.assertEqual((self.base / 'current').resolve(), self.old)
        self.assertEqual(self.store.read()['job']['status'], 'failed')
    def test_service_failure_rolls_back_and_records_failure(self):
        self.deploy.restart_services.side_effect = [subprocess.CalledProcessError(1, 'systemctl'), None]
        with self.assertRaises(subprocess.CalledProcessError): self.apply()
        self.assertEqual((self.base / 'current').resolve(), self.old)
        self.assertEqual(self.store.read()['job']['status'], 'failed')
    def test_release_edit_is_rejected_before_download(self):
        changed = copy.deepcopy(self.release); changed['archive']['size'] += 1
        with patch.object(source, 'release_metadata', return_value=changed), patch.object(source, 'download') as download:
            with self.assertRaises(updates.UpdateError): self.apply()
            download.assert_not_called()
        self.assertEqual((self.base / 'current').resolve(), self.old)
    def test_archive_version_must_match_release_tag(self):
        with patch.object(source, 'extract_archive', return_value=ROOT):
            with self.assertRaises(updates.UpdateError): self.apply()
        self.assertEqual((self.base / 'current').resolve(), self.old)
    def test_low_disk_space_refuses_update_before_download(self):
        with patch.object(service.shutil, 'disk_usage', return_value=Mock(free=1)), patch.object(source, 'download') as download:
            with self.assertRaises(updates.UpdateError): self.apply()
            download.assert_not_called()
        self.assertEqual((self.base / 'current').resolve(), self.old)


class SocketTests(unittest.TestCase):
    def test_unauthorized_peer_cannot_trigger_install(self):
        handler = service.UpdateHandler.__new__(service.UpdateHandler)
        handler.connection = Mock()
        handler.rfile = io.BytesIO(b'{"action":"install","tag":"v0.62.0"}\n')
        handler.wfile = io.BytesIO()
        handler.server = Mock()
        with patch.object(service, 'authorized_peer', return_value=False): handler.handle()
        self.assertFalse(json.loads(handler.wfile.getvalue())['ok'])
        handler.server.manager.install.assert_not_called()
    def test_unknown_actions_and_extra_parameters_are_rejected(self):
        for message in [{'action': 'shell', 'tag': 'rm'}, {'action': 'install', 'tag': 'v0.62.0', 'url': 'https://other.invalid'}]:
            handler = service.UpdateHandler.__new__(service.UpdateHandler)
            handler.connection = Mock(); handler.server = Mock()
            handler.rfile = io.BytesIO((json.dumps(message) + '\n').encode()); handler.wfile = io.BytesIO()
            with patch.object(service, 'authorized_peer', return_value=True): handler.handle()
            self.assertFalse(json.loads(handler.wfile.getvalue())['ok'])
            handler.server.manager.install.assert_not_called()


if __name__ == '__main__': unittest.main()
