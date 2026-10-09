import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from paimenos.savestates import prepare_resume, write_status
from paimenos.emulator_session import run_session


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.states = self.root / 'states'
        self.game = self.root / 'roms' / 'rom-123' / 'Game.sfc'
        self.folder = self.states / self.game.parent.name
        self.folder.mkdir(parents=True)

    def save(self, name, content, timestamp):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        os.utime(path, ns=(timestamp, timestamp))
        return path

    def test_newest_numbered_checkpoint_is_staged_for_native_auto_load(self):
        self.save('Game.state.auto', b'older', 10)
        selected = self.save('Snes9x/Game.state4', b'checkpoint', 20)
        self.save('Game.state5', b'', 30)
        self.save('Other.state9', b'other game', 40)
        base, source, marker = prepare_resume(self.states, self.game)
        self.assertEqual(source, selected)
        self.assertEqual(Path(str(base) + '.auto').read_bytes(), b'checkpoint')
        self.assertEqual(selected.read_bytes(), b'checkpoint')
        self.assertEqual(prepare_resume(self.states, self.game)[1], Path(str(base) + '.auto'))
        self.assertFalse(list(base.parent.glob('*.previous-*')))

    def test_clean_exit_disables_resume_without_deleting_saves(self):
        saved = self.save('Game.state.auto', b'state', 10)
        _, _, marker = prepare_resume(self.states, self.game)
        write_status(marker, 'clean')
        self.assertIsNone(prepare_resume(self.states, self.game)[1])
        self.assertEqual(saved.read_bytes(), b'state')
        write_status(marker, 'running')
        self.assertIsNotNone(prepare_resume(self.states, self.game)[1])

    def test_missing_state_and_other_rom_do_not_resume(self):
        other = self.states / 'rom-other'
        other.mkdir()
        (other / 'Game.state.auto').write_bytes(b'wrong game')
        self.assertIsNone(prepare_resume(self.states, self.game)[1])

    def test_real_normal_exit_clears_status_but_crash_preserves_it(self):
        _, _, marker = prepare_resume(self.states, self.game)
        with patch('paimenos.emulator_session.screen_time_expired', return_value=False):
            self.assertEqual(run_session([sys.executable, '-c', 'pass'], marker), 0)
            self.assertEqual(marker.read_text(), 'clean')
            self.assertEqual(run_session([sys.executable, '-c', 'raise SystemExit(1)'], marker), 1)
            self.assertEqual(marker.read_text(), 'running')

    def test_failed_launch_restores_previous_status(self):
        _, _, marker = prepare_resume(self.states, self.game)
        write_status(marker, 'clean')
        with self.assertRaises(FileNotFoundError):
            run_session(['/no/such/emulator'], marker)
        self.assertEqual(marker.read_text(), 'clean')

    def test_launcher_disables_auto_load_after_regular_exit(self):
        from paimenos import emulators
        self.game.parent.mkdir(parents=True)
        self.game.write_bytes(b'ROM')
        self.save('Game.state1', b'checkpoint', 10)
        with patch.object(emulators, 'ROOT', self.root), patch.object(emulators, 'core_path', return_value='/cores/snes9x_libretro.so'), patch.object(emulators, 'ready', return_value=True), patch.object(emulators.controllers, 'effective_autoconfig', return_value=self.root), patch('paimenos.emulator_session.run_session', return_value=0) as run:
            emulators.launch('snes', str(self.game))
            cfg = self.root / 'retroarch-paimenos-snes.cfg'
            self.assertIn('libretro_directory = "/cores"', cfg.read_text())
            self.assertIn('libretro_info_path = ', cfg.read_text())
            self.assertIn('core_info_cache_enable = "false"', cfg.read_text())
            self.assertIn('savestate_auto_load = "true"', cfg.read_text())
            args = run.call_args.args[0]
            self.assertNotIn('--savestate', args)
            target = self.folder / 'paimenos-resume'
            self.assertIn('savestate_directory = "' + str(target) + '"', cfg.read_text())
            for option in ('sort_savestates_enable', 'sort_savestates_by_content_enable', 'savestates_in_content_dir'):
                self.assertIn(option + ' = "false"', cfg.read_text())
            self.assertEqual((target / 'Game.state.auto').read_bytes(), b'checkpoint')
            write_status(run.call_args.kwargs['resume_marker'], 'clean')
            emulators.launch('snes', str(self.game))
            self.assertIn('savestate_auto_load = "false"', cfg.read_text())

    def test_recover_actual_retroarch_120_legacy_path_without_changing_original(self):
        legacy = self.root / '.config/retroarch/states'
        saved = legacy / self.game.parent.name / 'Snes9x' / 'Game.state.auto'
        saved.parent.mkdir(parents=True)
        saved.write_bytes(b'previous interrupted game')
        base, source, marker = prepare_resume(self.states, self.game, [legacy])
        self.assertEqual(source, saved)
        self.assertEqual(Path(str(base) + '.auto').read_bytes(), saved.read_bytes())
        write_status(marker, 'clean')
        self.assertIsNone(prepare_resume(self.states, self.game, [legacy])[1])
        self.assertEqual(saved.read_bytes(), b'previous interrupted game')

    def test_legacy_same_filename_in_other_game_is_not_imported(self):
        legacy = self.root / 'legacy'
        other = legacy / 'rom-other/Snes9x'
        other.mkdir(parents=True)
        (other / 'Game.state.auto').write_bytes(b'wrong ROM')
        self.assertIsNone(prepare_resume(self.states, self.game, [legacy])[1])
