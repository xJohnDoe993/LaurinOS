import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from unittest.mock import patch

from paimenos import backups as b


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.usb = self.base / 'usb'; self.usb.mkdir()
        self.root = self.base / 'emulators'; self.root.mkdir()
        self.state = self.base / 'state'; self.state.mkdir()
        self.apps = self.base / 'config/apps.json'; self.apps.parent.mkdir()
        self.apps.write_text('[]')
        self.mapping = {**{k: self.root / k for k in ('roms', 'saves', 'states', 'bios')},
                        'legacy_states': self.base / 'legacy', 'apps': self.apps}
        for patcher in (patch.object(b, 'ROOT', self.root), patch.object(b, 'STATE_DIR', self.state),
                        patch.object(b, 'JOURNAL', self.state / 'restore.json'),
                        patch.object(b, 'targets', return_value=self.mapping),
                        patch.object(b.parent, 'APPS_FILE', str(self.apps)),
                        patch.object(b, 'CHUNK', 4), patch.object(b.os.path, 'ismount', return_value=True),
                        patch.object(b, 'drives', return_value=[{'id':'usb','path':str(self.usb)}])):
            patcher.start(); self.addCleanup(patcher.stop)
        self.progress = lambda *args: None

    def put(self, key, name, content):
        p = self.mapping[key] / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def test_round_trip_selected_saves_with_chunks_preserves_other_files(self):
        save = self.put('saves', 'rom-1/test.srm', b'123456789')
        self.put('states', 'rom-1/session-status', b'running')
        name = b.create('usb', ['saves'], self.progress)
        self.assertEqual(len(b.available('usb')), 1)
        self.assertGreater(len(list((self.usb/'PaimenOS-Backups'/name).glob('*.part'))), 1)
        save.write_bytes(b'changed')
        keep = self.put('saves', 'other/new.srm', b'keep')
        b.restore('usb', name, ['saves'], self.progress)
        self.assertEqual(save.read_bytes(), b'123456789')
        self.assertEqual(keep.read_bytes(), b'keep')
        self.assertFalse(b.JOURNAL.exists())

    def test_corrupt_chunk_never_changes_live_files(self):
        save = self.put('saves', 'game.srm', b'1234')
        name = b.create('usb', ['saves'], self.progress)
        (self.usb/'PaimenOS-Backups'/name/'00000000.part').write_bytes(b'evil')
        save.write_bytes(b'current')
        with self.assertRaises(ValueError):
            b.restore('usb', name, ['saves'], self.progress)
        self.assertEqual(save.read_bytes(), b'current')

    def test_traversal_and_symlink_backup_are_rejected(self):
        self.put('bios', 'bios.bin', b'data')
        name = b.create('usb', ['bios'], self.progress)
        folder = self.usb/'PaimenOS-Backups'/name
        manifest = json.loads((folder/'manifest.json').read_text())
        manifest['files'][0]['path'] = '../../escape'
        (folder/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): b.restore('usb', name, ['bios'], self.progress)
        self.assertEqual(b.available('usb'), [])

    def test_rom_menu_commands_are_rebuilt_not_trusted(self):
        app_id = 'rom-' + 'a'*24
        self.put('roms', app_id + '/game.sfc', b'ROM')
        self.apps.write_text(json.dumps([{'id':app_id,'emulator':'snes','rom_entry':'game.sfc','title':'Game','command':'evil'}]))
        name = b.create('usb', ['roms'], self.progress)
        self.apps.write_text(json.dumps([{'id':'web','title':'keep'}]))
        b.restore('usb', name, ['roms'], self.progress)
        items = json.loads(self.apps.read_text())
        self.assertEqual(items[0]['id'], 'web')
        self.assertTrue(items[1]['command'].startswith('/usr/local/bin/paimenos-emulator snes '))
        self.assertNotIn('evil', items[1]['command'])

    def test_swap_failure_rolls_back_every_target(self):
        save = self.put('saves', 'game.srm', b'old')
        state = self.put('states', 'game.state', b'oldstate')
        name = b.create('usb', ['saves'], self.progress)
        save.write_bytes(b'current'); state.write_bytes(b'currentstate')
        real = os.replace
        def fail(source, target, *args, **kwargs):
            if Path(source).name.startswith('.restore-') and Path(target) == self.mapping['states']:
                raise OSError('simulated disk failure')
            return real(source, target, *args, **kwargs)
        with patch.object(b.os, 'replace', side_effect=fail), self.assertRaises(OSError):
            b.restore('usb', name, ['saves'], self.progress)
        self.assertEqual(save.read_bytes(), b'current')
        self.assertEqual(state.read_bytes(), b'currentstate')
        self.assertFalse(b.JOURNAL.exists())

    def test_recover_interrupted_swap(self):
        dest = self.put('saves', 'game.srm', b'old').parent
        token = 'a'*16
        old = dest.with_name('.previous-'+token+'-saves')
        new = dest.with_name('.restore-'+token+'-saves')
        new.mkdir(); (new/'game.srm').write_bytes(b'new')
        b.atomic_json(b.JOURNAL, {'token':token,'keys':['saves'],'existed':{'saves':True},'committed':False})
        os.replace(dest, old); os.replace(new, dest)
        b.recover()
        self.assertEqual((dest/'game.srm').read_bytes(), b'old')

    def test_busy_emulator_blocks_backup_and_restore(self):
        with b.data_lock():
            with self.assertRaises(ValueError):
                with b.data_lock(True): pass

    def test_usb_disconnected_and_partial_backup_not_offered(self):
        (self.usb/'PaimenOS-Backups').mkdir()
        (self.usb/'PaimenOS-Backups'/'.partial-backup').mkdir()
        self.assertEqual(b.available('usb'), [])
        with patch.object(b, 'drives', return_value=[]), self.assertRaises(ValueError):
            b.create('usb', ['bios'], self.progress)
