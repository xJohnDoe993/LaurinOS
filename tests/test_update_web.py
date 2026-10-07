"""Optional Flask integration tests; the baseline offline checks stay stdlib-only."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


@unittest.skipUnless(importlib.util.find_spec('flask'), 'Flask für Backend-Integrationstests nicht installiert')
class UpdateWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from paimenos import paths
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        with patch.object(paths, 'CONFIG_DIR', Path(cls.temp.name)):
            from paimenos import parent_web
        cls.web = parent_web
        cls.web.app.config['TESTING'] = True
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def setUp(self):
        self.client = self.web.app.test_client()
        self.settings = patch.object(self.web, 'read_settings', return_value={'pin': '678901'})
        self.settings.start()
    def tearDown(self): self.settings.stop()
    def authenticate(self):
        with self.client.session_transaction() as session:
            session.update(parent_authenticated=True, pin_fingerprint=self.web.pin_fingerprint(), csrf_token='test-csrf')
    def test_update_status_and_page_require_parent_login(self):
        with patch.object(self.web, 'update_request') as update:
            self.assertEqual(self.client.get('/updates').status_code, 302)
            self.assertEqual(self.client.get('/updates/status').status_code, 401)
            update.assert_not_called()
    def test_login_and_backend_share_local_logo_without_authentication(self):
        login = self.client.get('/login')
        self.assertEqual(login.status_code, 200)
        self.assertIn('/branding/logo.png', login.get_data(as_text=True))
        response = self.client.get('/branding/logo.png')
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'image/png')
            self.assertEqual(response.get_data(), (ROOT / 'assets/branding/paimenos-logo.png').read_bytes())
        finally:
            response.close()
        self.assertEqual(self.client.get('/branding/../manifest.json').status_code, 404)
        self.authenticate()
        self.assertIn('/branding/logo.png', self.client.get('/updates').get_data(as_text=True))
    def test_install_requires_csrf_even_with_parent_session(self):
        self.authenticate()
        with patch.object(self.web, 'update_request') as update:
            self.assertEqual(self.client.post('/updates/install', data={'tag': 'v0.62.0'}).status_code, 400)
            update.assert_not_called()
    def test_check_and_install_call_distinct_actions(self):
        self.authenticate()
        with patch.object(self.web, 'update_request', return_value={'ok': True}) as update:
            response = self.client.post('/updates/check', data={'csrf_token': 'test-csrf'})
            self.assertEqual(response.status_code, 200); update.assert_called_with('check', None)
            response = self.client.post('/updates/install', data={'csrf_token': 'test-csrf', 'tag': 'v0.62.0'})
            self.assertEqual(response.status_code, 200); update.assert_called_with('install', 'v0.62.0')
    def test_page_renders_without_remote_request_and_uses_correct_links(self):
        self.authenticate()
        with patch.object(self.web, 'update_request') as update:
            response = self.client.get('/updates')
            self.assertEqual(response.status_code, 200)
            text = response.get_data(as_text=True)
            self.assertIn('action("/updates/check")', text)
            self.assertIn('action("/updates/install", state.release.tag)', text)
            self.assertIn('release-banner', text)
            self.assertIn('body.set', text)
            self.assertIn('csrf_token', text)
            update.assert_not_called()
    def test_service_error_is_json_and_does_not_crash_backend(self):
        self.authenticate()
        with patch.object(self.web, 'update_request', side_effect=self.web.UpdateError('Dienst offline')):
            response = self.client.get('/updates/status')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json, {'ok': False, 'error': 'Dienst offline'})

    def test_apps_page_refreshes_old_camera_title_and_describes_videos(self):
        self.authenticate()
        camera = {'id': 'camera', 'type': 'camera', 'command': '__CAMERA__',
                  'title': 'Kamera / Bilder'}
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            path = Path(folder) / 'apps.json'
            path.write_text(json.dumps([camera]))
            with patch.object(self.web.parents, 'APPS_FILE', str(path)), \
                    patch.object(self.web, 'read_settings', return_value={'pin': '678901', 'disabled_apps': []}):
                response = self.client.get('/apps')
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn('<h3>Kamera / Bilder / Videos</h3>', text)
        self.assertIn('Kamera, Bilder &amp; Videos', text)
        self.assertNotIn('Kamera & Bilder', text)


if __name__ == '__main__': unittest.main()
