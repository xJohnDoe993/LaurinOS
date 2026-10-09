"""Opaque fullscreen protection, including secondary displays and modal dialogs."""
from PyQt5.QtCore import QEvent, QObject, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QWidget
from paimenos.screen_guard import ViewGuard


class ForegroundGuard(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.lease = None
        self.covers = {}
        self.window.setWindowFlags(self.window.windowFlags() | Qt.FramelessWindowHint |
                                   Qt.WindowStaysOnTopHint)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.raise_windows)
        self.window.installEventFilter(self)
        app = QApplication.instance()
        app.aboutToQuit.connect(self.release)
        self.window.destroyed.connect(self.release)
        app.screenAdded.connect(self.sync_screens)
        app.screenRemoved.connect(self.sync_screens)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Show:
            if self.lease is None:
                self.lease = ViewGuard()
            self.sync_screens()
            self.timer.start(250)
            QTimer.singleShot(0, self.raise_windows)
        elif event.type() == QEvent.Hide:
            self.release()
        return super().eventFilter(watched, event)

    def sync_screens(self, *args):
        if self.lease is None:
            return
        screens = QApplication.screens()
        main = self.window.screen() or QApplication.primaryScreen()
        for screen in list(self.covers):
            if screen not in screens or screen is main:
                cover = self.covers.pop(screen)
                cover.hide()
                cover.deleteLater()
        for screen in screens:
            if screen is main:
                continue
            if screen not in self.covers:
                cover = QWidget()
                cover.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint |
                                     Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
                cover.setAttribute(Qt.WA_ShowWithoutActivating)
                cover.setAutoFillBackground(True)
                cover.setPalette(self.window.palette())
                self.covers[screen] = cover
            cover = self.covers[screen]
            cover.setGeometry(screen.geometry())
            if not cover.isVisible():
                cover.show()

    def raise_windows(self):
        if self.lease is None or not self.window.isVisible():
            return
        self.sync_screens()
        for cover in self.covers.values():
            cover.raise_()
        self.window.raise_()
        target = QApplication.activeModalWidget() or QApplication.activePopupWidget()
        ancestor = target
        while ancestor is not None and ancestor is not self.window:
            ancestor = ancestor.parentWidget()
        if ancestor is not self.window:
            target = self.window
        target.raise_()
        if QApplication.activeWindow() is not target:
            target.activateWindow()

    def release(self, *args):
        self.timer.stop()
        for cover in self.covers.values():
            cover.hide()
            cover.deleteLater()
        self.covers.clear()
        if self.lease is not None:
            self.lease.close()
            self.lease = None
