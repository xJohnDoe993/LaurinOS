import io
import signal
import subprocess
import sys
import unittest
from unittest.mock import Mock
from paimenos.emulator_session import Session
from pathlib import Path
import os
import tempfile
import time


class SessionTests(unittest.TestCase):
    def test_menu_service_allows_supervised_shutdown(self):
        root = Path(__file__).resolve().parents[1]
        unit = (root / 'systemd/user/paimenos-menu.service').read_text()
        self.assertIn('KillMode=mixed', unit)
        self.assertIn('TimeoutStopSec=20', unit)

    def test_real_supervisor_quits_running_and_stopped_child_cleanly(self):
        root = Path(__file__).resolve().parents[1]
        for expired in (False, True):
            with self.subTest(expired=expired), tempfile.TemporaryDirectory(dir=root.parent) as folder:
                folder = Path(folder)
                child_code = (
                    'import os,sys\nfrom pathlib import Path\n'
                    'p=Path(sys.argv[1]);(p/"ready").write_text("ready")\n'
                    'for line in sys.stdin:\n'
                    ' if line.strip()=="QUIT":\n'
                    '  (p/"game.state.auto").write_bytes(b"session at shutdown");break\n')
                supervisor_code = (
                    'import sys,os\nfrom pathlib import Path\nfrom paimenos import emulator_session as e\n'
                    'tick=e.Session.tick\n'
                    'def checked_tick(self,*args):\n'
                    ' tick(self,*args)\n'
                    ' if self.paused and not Path(sys.argv[3],"stopped").exists():\n'
                    '  pid,status=os.waitpid(self.process.pid,os.WUNTRACED)\n'
                    '  assert os.WIFSTOPPED(status)\n'
                    '  Path(sys.argv[3],"stopped").write_text("stopped")\n'
                    'e.Session.tick=checked_tick\n'
                    'e.screen_time_expired=lambda:sys.argv[1]=="True"\n'
                    'raise SystemExit(e.run_session([sys.executable,"-u","-c",sys.argv[2],sys.argv[3]], Path(sys.argv[3])/"session-status"))\n')
                proc = subprocess.Popen([sys.executable, '-u', '-c', supervisor_code,
                    str(expired), child_code, str(folder)],
                    env=dict(os.environ, PYTHONPATH=str(root / 'src')), stdout=subprocess.DEVNULL, start_new_session=True)
                try:
                    deadline = time.monotonic() + 5
                    ready = False
                    while time.monotonic() < deadline:
                        if (folder / ('stopped' if expired else 'ready')).exists():
                            ready = True
                            break
                        time.sleep(.02)
                    self.assertTrue(ready, 'Child did not reach the expected running/stopped state')
                    proc.terminate()
                    self.assertEqual(proc.wait(timeout=5), 0)
                    self.assertEqual((folder / 'game.state.auto').read_bytes(), b'session at shutdown')
                    self.assertEqual((folder / 'session-status').read_text(), 'running')
                finally:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL); proc.wait(timeout=3)

    def setUp(self):
        self.process = Mock(stdin=io.BytesIO())
        self.session = Session(self.process)

    def test_save_once_then_pause_and_resume_with_bonus(self):
        self.session.tick(True, 10)
        self.session.tick(True, 11)
        self.assertEqual(self.process.stdin.getvalue(), b'SAVE_STATE\n')
        self.process.send_signal.assert_not_called()
        self.session.tick(True, 12)
        self.session.tick(True, 13)
        self.process.send_signal.assert_called_once_with(signal.SIGSTOP)
        self.session.tick(False, 14)
        self.assertEqual(self.process.send_signal.call_args.args, (signal.SIGCONT,))
        self.session.tick(True, 20)
        self.assertEqual(self.process.stdin.getvalue().count(b'SAVE_STATE'), 2)

    def test_bonus_during_save_cancels_pending_pause(self):
        self.session.tick(True, 10)
        self.session.tick(False, 11)
        self.session.tick(False, 15)
        self.process.send_signal.assert_not_called()

    def test_broken_command_pipe_still_preserves_live_session(self):
        self.process.stdin = Mock()
        self.process.stdin.write.side_effect = BrokenPipeError
        self.session.tick(True, 10)
        self.session.tick(True, 12)
        self.process.send_signal.assert_called_once_with(signal.SIGSTOP)

    def test_real_process_retains_state_across_pause(self):
        # A real child models a running game and answers through its own pipe.
        child = subprocess.Popen([sys.executable, '-u', '-c',
            'import sys\nfor line in sys.stdin:\n print(line.strip(), flush=True)'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        session = Session(child)
        try:
            session.tick(True, 0)
            self.assertEqual(child.stdout.readline(), b'SAVE_STATE\n')
            session.tick(True, 2)
            # waitpid verifies the OS actually stopped our own child.
            import os
            pid, status = os.waitpid(child.pid, os.WUNTRACED)
            self.assertTrue(os.WIFSTOPPED(status))
            session.tick(False, 3)
            session.command('CONTINUED')
            self.assertEqual(child.stdout.readline(), b'CONTINUED\n')
        finally:
            session.resume()
            child.terminate()
            child.wait(timeout=3)
            child.stdin.close()
            child.stdout.close()
