import io
import tempfile
import unittest
import zipfile
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from werkzeug.datastructures import FileStorage
from paimenos import emulator_catalog as catalog, emulator_service as service, emulators


def archive(extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        for name in ('GC/dsp_coef.bin', 'GC/dsp_rom.bin', 'GameSettings/TEST.ini'):
            z.writestr('dolphin-emu/Sys/' + name, b'fixture')
        if extra:
            z.writestr(extra, b'invalid')
    return buffer.getvalue()


class DolphinTests(unittest.TestCase):
    def test_optional_selection_and_formats(self):
        self.assertNotIn('dolphin', catalog.RECOMMENDED)
        self.assertEqual(catalog.selection('dolphin,n64'), ['dolphin', 'n64'])
        self.assertIn('.rvz', catalog.CATALOG['dolphin']['extensions'])

    def test_assets_install_and_readiness_require_complete_sys_tree(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(catalog, 'SHARED_SYSTEM', Path(tmp)), patch.object(service, 'SHARED_SYSTEM', Path(tmp)), patch.object(service, 'download', return_value=archive()) as download:
            self.assertFalse(catalog.assets_ready('dolphin'))
            service.install_dolphin_assets()
            self.assertTrue(catalog.assets_ready('dolphin'))
            service.install_dolphin_assets()
            download.assert_called_once_with('https://buildbot.libretro.com/assets/system/Dolphin.zip')
            with patch.object(catalog, 'core_path', return_value='/core.so'), patch.object(catalog.shutil, 'which', return_value='/retroarch'):
                self.assertTrue(next(x for x in catalog.status() if x['id'] == 'dolphin')['ready'])

    def test_bad_archive_does_not_replace_existing_assets(self):
        for name in ('dolphin-emu/../../escape', '/escape', 'unexpected/file'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp, patch.object(catalog, 'SHARED_SYSTEM', Path(tmp)), patch.object(service, 'SHARED_SYSTEM', Path(tmp)), patch.object(service, 'download', return_value=archive(name)):
                previous = Path(tmp) / 'dolphin-emu/keep'
                previous.parent.mkdir()
                previous.write_text('old')
                with self.assertRaises(ValueError):
                    service.install_dolphin_assets()
                self.assertEqual(previous.read_text(), 'old')

    def test_reinstall_repairs_missing_assets_with_existing_core(self):
        with patch.object(service, 'installation_lock', return_value=nullcontext()), patch.object(service.subprocess, 'check_output', return_value='amd64'), patch.object(service.shutil, 'which', return_value='/retroarch'), patch.object(service, 'core_path', return_value='/dolphin.so'), patch.object(service, 'install_dolphin_assets') as assets, patch.object(service, 'install_profiles'), patch.object(service, 'command') as command:
            result = service.install_selected(['dolphin'], report=lambda *a, **k: None)
            self.assertTrue(result['dolphin']['ok'])
            assets.assert_called_once()
            command.assert_not_called()

    def test_gamecube_image_above_other_console_limit_is_streamed_into_menu(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(emulators, 'ROOT', Path(tmp)), patch.object(emulators, 'LIMIT', 16), patch.object(emulators, 'ready', return_value=True), patch.object(emulators.parents, 'app_transaction', return_value=nullcontext()), patch.object(emulators.parents, 'read_apps', return_value=[]), patch.object(emulators.parents, 'atomic_json') as save:
            game = FileStorage(stream=io.BytesIO(b'x' * 40), filename='game.rvz')
            app_id = emulators.upload_game('dolphin', 'GameCube', [game])
            self.assertEqual((Path(tmp) / 'roms' / app_id / 'game.rvz').stat().st_size, 40)
            self.assertEqual(save.call_args.args[1][0]['emulator'], 'dolphin')
            oversized = FileStorage(stream=io.BytesIO(b'x' * 145), filename='large.iso')
            with self.assertRaises(ValueError):
                emulators.upload_game('dolphin', 'Too large', [oversized])
