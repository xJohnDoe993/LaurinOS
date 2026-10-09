import io
import signal
import subprocess
import sys
import unittest
from unittest.mock import Mock
from paimenos.emulator_session import Session


class SessionTests(unittest.TestCase):
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
