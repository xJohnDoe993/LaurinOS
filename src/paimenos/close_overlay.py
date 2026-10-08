#!/usr/bin/env python3
"""Menü-Knopf im freigehaltenen Bereich der Firefox-Leiste."""
import os
import signal
import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QPushButton, QWidget
from paimenos.webapp import BAR_HEIGHT, MENU_WIDTH
from paimenos.fullscreen import FullscreenTracker


class CloseButtonOverlay(QWidget):
    def __init__(self, target_pid, close_pid=None):
        super().__init__()
        self.target_pid = target_pid
        self.close_pid = close_pid or target_pid
        self.fullscreen = FullscreenTracker(target_pid)
        self.pidfd = None
        try:
            if hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'):
                self.pidfd = os.pidfd_open(self.close_pid)
        except OSError:
            pass
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                            Qt.X11BypassWindowManagerHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.button = QPushButton('⌂ Zum Menü', self)
        self.button.setFocusPolicy(Qt.NoFocus)
        self.button.setAccessibleName('Webapp schließen und zum Kinder-Menü zurückkehren')
        self.button.setToolTip('Zurück zu deinen Apps und Spielen')
        self.button.setStyleSheet('''QPushButton {
            background:#ffb347;color:#172234;font-family:"DejaVu Sans";
            font-size:18px;font-weight:bold;border-radius:10px;
            border:1px solid #ffd497;
        } QPushButton:hover {background:#ffc477;}
        QPushButton:pressed {background:#ed9a30;}
        QPushButton:disabled {background:#304562;color:#b4c0d1;}''')
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.close_target)
        self.place_button()
        QApplication.primaryScreen().geometryChanged.connect(self.place_button)
        self.monitor = QTimer(self)
        self.monitor.timeout.connect(self.update_overlay)
        self.monitor.start(250)

    def place_button(self, *args):
        screen = QApplication.primaryScreen().geometry()
        height = BAR_HEIGHT - 20
        self.setGeometry(screen.right() - MENU_WIDTH - 11, screen.top() + 10, MENU_WIDTH, height)
        self.button.setGeometry(0, 0, MENU_WIDTH, height)

    def close_target(self):
        self.button.setEnabled(False)
        try:
            if self.pidfd is not None:
                signal.pidfd_send_signal(self.pidfd, signal.SIGTERM)
            else:
                os.kill(self.close_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as exc:
            self.button.setEnabled(True)
            self.button.setToolTip('Schließen fehlgeschlagen: ' + str(exc))
            return
        QApplication.quit()

    def check_target(self):
        try:
            if self.pidfd is not None:
                import select
                if not select.select([self.pidfd], [], [], 0)[0]:
                    return True
            else:
                os.kill(self.target_pid, 0)
                return True
        except ProcessLookupError:
            pass
        except OSError:
            return True
        QApplication.quit()
        return False

    def update_overlay(self):
        if not self.check_target():
            return
        if self.fullscreen.is_fullscreen():
            self.hide()
        elif not self.isVisible():
            # WA_ShowWithoutActivating bleibt gesetzt: das Video verliert
            # beim Verlassen des Vollbilds weder Fokus noch Tastaturbedienung.
            self.place_button()
            self.show()

    def closeEvent(self, event):
        self.monitor.stop()
        self.fullscreen.close()
        if self.pidfd is not None:
            os.close(self.pidfd)
            self.pidfd = None
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    if len(sys.argv) > 1:
        pid = int(sys.argv[1])
        if pid <= 1:
            raise ValueError('Ungültiger Webapp-Prozess.')
        overlay = CloseButtonOverlay(pid, int(sys.argv[2]) if len(sys.argv) > 2 else None)
        overlay.update_overlay()
        sys.exit(app.exec_())
