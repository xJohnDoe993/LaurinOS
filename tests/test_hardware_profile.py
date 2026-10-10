import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from unittest.mock import patch

from paimenos import hardware_profile as hp
from paimenos import emulator_video as video

MEM = 'MemTotal:       16303000 kB\n'


def cpu(model):
    return 'processor\t: 0\nmodel name\t: ' + model + '\n'


class DetectTests(unittest.TestCase):
    def test_suggestions_follow_cpu_generation_and_tier(self):
        cases = {
            'Intel(R) Core(TM) i5-4300U CPU @ 1.90GHz': 'ultra-low',
            'Intel(R) Core(TM) i3-7100U CPU @ 2.40GHz': 'ultra-low',
            'Intel(R) Celeron(R) N4020 CPU @ 1.10GHz': 'ultra-low',
            'Intel(R) Core(TM) i5 CPU       M 520  @ 2.40GHz': 'ultra-low',
            'Intel(R) Core(TM) i7-920 CPU @ 2.67GHz': 'ultra-low',
            'Intel(R) Core(TM) i5-5300U CPU @ 2.30GHz': 'low',
            'Intel(R) Core(TM) i7-7500U CPU @ 2.70GHz': 'low',
            'Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz': 'medium',
            'Intel(R) Core(TM) i5-10210U CPU @ 1.60GHz': 'medium',
            'Intel(R) Core(TM) i5-1035G1 CPU @ 1.00GHz': 'medium',
            '11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz': 'high',
            '12th Gen Intel(R) Core(TM) i7-1260P': 'high',
            'Intel(R) Core(TM) Ultra 5 125U': 'high',
            'AMD Ryzen 5 2500U with Radeon Vega Mobile Gfx': 'low',
            'AMD Ryzen 5 4500U with Radeon Graphics': 'medium',
            'AMD Ryzen 3 5300U with Radeon Graphics': 'medium',
            'AMD Ryzen 7 5800H with Radeon Graphics': 'high',
            'AMD A6-9225 RADEON R4, 5 COMPUTE CORES 2C+3G': 'ultra-low',
            'Some Unknown CPU': 'low',
        }
        for model, expected in cases.items():
            with self.subTest(model=model):
                self.assertEqual(hp.detect(cpu(model), MEM), expected)

    def test_little_memory_lowers_the_suggestion(self):
        self.assertEqual(hp.detect(cpu('Intel(R) Core(TM) i7-1260P'), 'MemTotal: 2900000 kB\n'), 'ultra-low')
        self.assertEqual(hp.detect(cpu('Intel(R) Core(TM) i7-1260P'), 'MemTotal: 3900000 kB\n'), 'low')
        self.assertEqual(hp.detect(cpu('Intel(R) Core(TM) i7-1260P'), 'MemTotal: 5900000 kB\n'), 'low')
        self.assertEqual(hp.detect(cpu('Intel(R) Core(TM) i7-1260P'), 'MemTotal: 7900000 kB\n'), 'high')

    def test_missing_or_invalid_file_falls_back_to_previous_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'profile'
            with patch.object(hp, 'PROFILE_FILE', path):
                self.assertEqual(hp.current(), 'low')
                path.write_text('turbo\n')
                self.assertEqual(hp.current(), 'low')
                path.write_text('high\n')
                self.assertEqual(hp.current(), 'high')


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def test_luanti_keeps_user_keys_and_replaces_managed_ones(self):
        conf = self.home / '.minetest/minetest.conf'
        conf.parent.mkdir()
        conf.write_text('name = Kind\nviewing_range = 500\n# viewing_range = 1\nviewing_range = 600\n')
        self.assertEqual(hp.apply_luanti('ultra-low', self.home), [conf])
        text = conf.read_text()
        self.assertIn('name = Kind\n', text)
        self.assertIn('# viewing_range = 1\n', text)
        self.assertEqual(text.count('viewing_range = 50\n'), 1)
        self.assertNotIn('600', text)
        self.assertIn('enable_dynamic_shadows = false', text)
        self.assertEqual(hp.apply_luanti('ultra-low', self.home), [])

    def test_fresh_flatpak_install_gets_settings_before_first_start(self):
        apps = self.home / '.config/paimenos/apps.json'
        apps.parent.mkdir(parents=True)
        apps.write_text(json.dumps([{'id': 'minetest', 'flatpak_id': 'org.luanti.luanti'}]))
        changed = hp.apply_luanti('high', self.home)
        conf = self.home / '.var/app/org.luanti.luanti/.minetest/minetest.conf'
        self.assertEqual(changed, [conf])
        self.assertIn('enable_dynamic_shadows = true', conf.read_text())
        self.assertFalse((self.home / '.minetest').exists())

    def test_symlinked_luanti_folders_are_not_followed(self):
        target = self.home / 'elsewhere'; target.mkdir()
        (self.home / '.minetest').symlink_to(target)
        self.assertEqual(hp.apply_luanti('low', self.home), [])
        self.assertFalse((target / 'minetest.conf').exists())

    def test_no_luanti_means_no_new_folders(self):
        self.assertEqual(hp.apply_luanti('low', self.home), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_firefox_preferences_scale_with_profile(self):
        self.assertIn('"dom.ipc.processCount", 1', hp.firefox_preferences('ultra-low'))
        self.assertIn('"ui.prefersReducedMotion", 1', hp.firefox_preferences('low'))
        self.assertEqual(hp.firefox_preferences('high'), '')


class EmulatorProfileTests(unittest.TestCase):
    def test_low_profile_keeps_previous_efficient_defaults(self):
        self.assertEqual(video.core_settings('psp', 'low')['ppsspp_internal_resolution'], '480x272')
        self.assertEqual(video.core_settings('psp', 'low')['ppsspp_texture_anisotropic_filtering'], '2x')
        self.assertEqual(video.core_settings('n64', 'low')['mupen64plus-next-EnableFBEmulation'], 'True')
        self.assertEqual(video.core_settings('ps1', 'low')['beetle_psx_internal_resolution'], '1x(native)')
        self.assertEqual(video.video_settings('snes', 'low')['video_threaded'], 'false')

    def test_profiles_scale_resolution_and_costly_options(self):
        self.assertEqual(video.video_settings('snes', 'ultra-low')['video_threaded'], 'true')
        self.assertEqual(video.core_settings('psp', 'ultra-low')['ppsspp_auto_frameskip'], 'enabled')
        self.assertEqual(video.core_settings('n64', 'ultra-low')['mupen64plus-EnableFBEmulation'], 'False')
        self.assertEqual(video.core_settings('psp', 'medium')['ppsspp_internal_resolution'], '960x544')
        self.assertEqual(video.core_settings('n64', 'high')['mupen64plus-next-EnableNativeResFactor'], '3')
        self.assertEqual(video.core_settings('ps1', 'high')['beetle_psx_internal_resolution'], '4x')
        self.assertEqual(video.core_settings('dolphin', 'high')['dolphin_efb_scale'], '2')

    def test_profile_file_is_read_when_no_profile_is_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'profile'
            path.write_text('medium\n')
            with patch.object(hp, 'PROFILE_FILE', path):
                self.assertEqual(video.core_settings('psp')['ppsspp_internal_resolution'], '960x544')


if __name__ == '__main__':
    unittest.main()
