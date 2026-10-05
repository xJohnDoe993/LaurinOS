import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from laurinos import state, emulator_catalog, webapp, wifi, controller_profiles

class RuntimeTests(unittest.TestCase):
    def test_settings_missing_do_not_enable_default_pin(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder, patch.object(state, 'SETTINGS_FILE', str(Path(folder) / 'settings.json')):
            with self.assertRaises(ValueError):
                state.read_settings()
            self.assertFalse((Path(folder) / 'settings.json').exists())
    def test_settings_updates_preserve_parent_preferences(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            path = Path(folder) / 'settings.json'
            subprocess.run([sys.executable, str(ROOT / 'tools/initialize-settings.py'), str(path), '456789'], check=True)
            with patch.object(state, 'SETTINGS_FILE', str(path)):
                state.update_settings({'daily_limit_minutes': 30})
                result = state.update_settings({'bonus_minutes': 5})
                self.assertEqual(result['pin'], '456789')
                self.assertEqual(result['daily_limit_minutes'], 30)
                self.assertEqual(state.remaining_seconds(result), 35 * 60)
    def test_settings_corruption_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            path = Path(folder) / 'settings.json';path.write_text('{bad json')
            with patch.object(state, 'SETTINGS_FILE', str(path)):
                with self.assertRaises(json.JSONDecodeError):state.read_settings()
                self.assertEqual(path.read_text(), '{bad json')
    def test_emulator_selection_aliases_dedup_and_invalid_input(self):
        self.assertEqual(emulator_catalog.selection('nes,gb,nes'), ['nes', 'gb'])
        self.assertEqual(emulator_catalog.selection('none'), [])
        self.assertEqual(len(emulator_catalog.selection('all')), 10)
        with self.assertRaises(ValueError):emulator_catalog.selection('unknown')
    def test_webapp_profile_gets_resource_css_and_preserves_preferences(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            profile = Path(folder)
            (profile / 'user.js').write_text('user_pref("example", true);\n')
            webapp.prepare_profile(str(profile), str(profile / "missing-template.js"))
            self.assertIn('user_pref("example", true)', (profile / 'user.js').read_text())
            self.assertEqual((profile / 'chrome/laurinos-webapp.css').read_text(), (ROOT / 'assets/webapp.css').read_text())
            webapp.prepare_profile(str(profile), str(profile / "missing-template.js"))
            self.assertEqual((profile / 'chrome/userChrome.css').read_text().count(webapp.CHROME_IMPORT), 1)
    def test_defaults_generate_valid_app_json_for_empty_native_selection(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            web = subprocess.check_output([sys.executable, str(ROOT / 'tools/default-webapps.py')], text=True).strip()
            target = Path(folder) / 'apps.json'
            subprocess.run([sys.executable, str(ROOT / 'tools/render-config.py'), str(ROOT / 'data/apps.json.in'), str(target), 'APP_ENTRIES=', 'WEBAPP_ENTRIES=' + web], check=True)
            apps = json.loads(target.read_text())
            self.assertEqual(apps[-1]['id'], 'poweroff')
            self.assertTrue(any(app['type'] == 'webapp' for app in apps))
    def test_gamepad_filter_accepts_gamepad_rejects_keyboard(self):
        # sysfs words are ordered high-to-low; 304 is BTN_GAMEPAD, 30 is KEY_A.
        import struct
        width = struct.calcsize('@L') * 8
        def bits(code):
            words = [0] * (code // width + 1)
            words[code // width] = 1 << (code % width)
            return ' '.join(format(v, 'x') for v in reversed(words))
        with patch('laurinos.input_devices.Path.read_text', return_value=bits(304)):
            self.assertTrue(controller_profiles.possible_gamepad('/dev/input/event7'))
        with patch('laurinos.input_devices.Path.read_text', return_value=bits(30)):
            self.assertFalse(controller_profiles.possible_gamepad('/dev/input/event7'))
