"""Keep a timed-out emulator alive; request a checkpoint before freezing it.

The private stdin pipe avoids exposing RetroArch's command interface on the LAN.
A save request is best effort: cores without serialization still retain their
live session. Only the child we own is signalled, never unrelated applications.
"""
import signal
import subprocess
import time

from paimenos.screen_guard import screen_time_expired


class Session:
    def __init__(self, process):
        self.process = process
        self.deadline = None
        self.paused = False

    def command(self, command):
        try:
            self.process.stdin.write((command + '\n').encode('ascii'))
            self.process.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def tick(self, expired, now):
        if not expired:
            if self.paused:
                self.process.send_signal(signal.SIGCONT)
                self.paused = False
            self.deadline = None
        elif self.deadline is None:
            # Auto-indexing advances the selected slot before saving.
            self.command('SAVE_STATE')
            self.deadline = now + 2.0
            print('Screen time: checkpoint requested (not confirmed); preserving live session.', flush=True)
        elif not self.paused and now >= self.deadline:
            self.process.send_signal(signal.SIGSTOP)
            self.paused = True

    def resume(self):
        if self.paused:
            self.process.send_signal(signal.SIGCONT)
            self.paused = False


def run_session(command):
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    session = Session(process)
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        while process.poll() is None:
            if stopping:
                session.resume()
                session.command('QUIT')
                try:
                    return process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    return process.wait(timeout=3)
            try:
                session.tick(screen_time_expired(), time.monotonic())
            except ProcessLookupError:
                break
            time.sleep(0.1)
        return process.wait()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        # Never leave an orphaned stopped process if supervision fails.
        if process.poll() is None:
            try:
                session.resume()
            except ProcessLookupError:
                pass
        process.stdin.close()
