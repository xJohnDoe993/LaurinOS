"""Vollbildstatus der zugehörigen Firefox-Fenster über X11 lesen."""
import os
import time
from Xlib import Xatom, display, error


class FullscreenTracker:
    def __init__(self, target_pid, display_factory=None):
        self.target_pid = target_pid
        self.enabled = display_factory is not None or bool(os.environ.get('DISPLAY'))
        self.factory = display_factory or display.Display
        self.connection = None
        self.retry_after = 0
        self.atoms = {}

    @staticmethod
    def values(window, atom, kind):
        prop = window.get_full_property(atom, kind)
        return [] if prop is None else list(prop.value)

    def is_fullscreen(self):
        if not self.enabled or time.monotonic() < self.retry_after:
            return False
        try:
            if self.connection is None:
                self.connection = self.factory()
                self.atoms = {name: self.connection.intern_atom(name) for name in
                    ('_NET_CLIENT_LIST_STACKING', '_NET_CLIENT_LIST', '_NET_WM_PID',
                     '_NET_WM_STATE', '_NET_WM_STATE_FULLSCREEN')}
            root = self.connection.screen().root
            windows = self.values(root, self.atoms['_NET_CLIENT_LIST_STACKING'], Xatom.WINDOW)
            if not windows:
                windows = self.values(root, self.atoms['_NET_CLIENT_LIST'], Xatom.WINDOW)
            for window_id in windows:
                try:
                    window = self.connection.create_resource_object('window', int(window_id))
                    owner = self.values(window, self.atoms['_NET_WM_PID'], Xatom.CARDINAL)
                    if not owner or int(owner[0]) != self.target_pid:
                        continue
                    states = self.values(window, self.atoms['_NET_WM_STATE'], Xatom.ATOM)
                    if self.atoms['_NET_WM_STATE_FULLSCREEN'] in states:
                        return True
                except error.BadWindow:
                    # Das Fenster kann zwischen Auflisten und Abfragen schließen.
                    continue
            return False
        except (error.DisplayError, error.ConnectionClosedError, error.XError, OSError):
            self.close()
            self.retry_after = time.monotonic() + 2
            # Bei fehlenden Informationen den Weg zum Menü erreichbar halten.
            return False

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            except (error.DisplayError, error.ConnectionClosedError, OSError):
                pass
            self.connection = None
