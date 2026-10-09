"""Cross-process priority for screen-time and parent views."""
import fcntl
from paimenos.paths import STATE_DIR
from paimenos.state import read_settings, remaining_seconds


def screen_time_expired():
    try:
        return remaining_seconds(read_settings()) == 0
    except (OSError, ValueError, KeyError, TypeError):
        # Missing/corrupt settings must never grant access to child applications.
        return True


def _open_guard():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return open(STATE_DIR / 'paimenos-protected-view.lock', 'a')


class ViewGuard:
    """A live lease; process exit releases it without leaving a stale flag."""
    def __init__(self):
        self.file = _open_guard()
        try:
            fcntl.flock(self.file, fcntl.LOCK_SH)
        except BaseException:
            self.file.close()
            raise

    def close(self):
        self.file.close()


def protected_view_active():
    try:
        with _open_guard() as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        return False
    except OSError:
        return True


def child_access_blocked():
    return screen_time_expired() or protected_view_active()
