"""Video playback within the existing camera browser; optional on older installs."""
import os
from PyQt5.QtCore import Qt, QUrl, QEvent
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider, QShortcut
from laurinos.diagnostics import log_event


def load_backend():
    # A missing multimedia package must not prevent the menu or photos opening.
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget
    return QMediaPlayer, QMediaContent, QVideoWidget


def clock_text(milliseconds):
    seconds = max(0, int(milliseconds)) // 1000
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


class CameraVideoViewer(QWidget):
    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.paths, self.index, self.path = [], 0, ""
        self.active, self.failed = False, False
        self.duration = 0
        self.player = None
        self.surface = None
        self.video_fullscreen = False
        self.fullscreen_restore = None
        self.shortcuts = []
        layout = QVBoxLayout(self)
        self.name_label = QLabel(self)
        self.name_label.setTextFormat(Qt.PlainText)
        self.name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label)
        self.status_label = QLabel(self)
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        try:
            self.player_type, self.content_type, surface_type = load_backend()
            self.surface = surface_type(self)
            self.surface.setStyleSheet("background: black;")
            self.surface.setFocusPolicy(Qt.StrongFocus)
            self.surface.installEventFilter(self)
            layout.addWidget(self.surface, 1)
            self.player = self.player_type(self)
            self.player.setVideoOutput(self.surface)
            self.player.setVolume(70)
            self.player.positionChanged.connect(self.position_changed)
            self.player.durationChanged.connect(self.duration_changed)
            self.player.seekableChanged.connect(self.update_seekable)
            self.player.stateChanged.connect(self.state_changed)
            self.player.mediaStatusChanged.connect(self.status_changed)
            self.player.error.connect(self.playback_error)
        except (ImportError, OSError) as exc:
            log_event("Videos", "Videowiedergabe nicht eingerichtet: " + str(exc))
            layout.addStretch(1)
        seek = QHBoxLayout()
        self.position_slider = QSlider(Qt.Horizontal, self)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setEnabled(False)
        self.position_slider.sliderReleased.connect(self.seek)
        self.position_slider.valueChanged.connect(self.seek_changed)
        self.time_label = QLabel("0:00 / 0:00", self)
        seek.addWidget(self.position_slider, 1)
        seek.addWidget(self.time_label)
        layout.addLayout(seek)
        controls = QHBoxLayout()
        self.previous_button = self.button("← Vorheriges", lambda: self.step(-1), controls)
        self.play_button = self.button("▶ Wiedergabe", self.toggle_play, controls)
        self.next_button = self.button("Nächstes →", lambda: self.step(1), controls)
        self.fullscreen_button = self.button("⛶ Vollbild", self.toggle_fullscreen, controls)
        self.fullscreen_button.setEnabled(False)
        self.button("Zur Übersicht", browser.show_overview, controls)
        layout.addLayout(controls)
        volume = QHBoxLayout()
        volume.addWidget(QLabel("Lautstärke", self))
        self.volume_slider = QSlider(Qt.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.set_volume)
        volume.addWidget(self.volume_slider, 1)
        layout.addLayout(volume)
        help_label = QLabel("Doppelklick / F11: Vollbild · Leertaste: Pause · Esc: Zurück", self)
        help_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(help_label)
        for key, callback in ((Qt.Key_Space, self.toggle_play), (Qt.Key_Escape, self.escape),
                              (Qt.Key_F11, self.toggle_fullscreen)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.setFocusPolicy(Qt.StrongFocus)

    def button(self, text, callback, layout):
        button = QPushButton(text, self)
        button.setAutoDefault(False)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def eventFilter(self, watched, event):
        if watched is self.surface and event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            self.toggle_fullscreen()
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def toggle_fullscreen(self):
        self.set_fullscreen(not self.video_fullscreen)

    def set_fullscreen(self, enabled):
        if enabled == self.video_fullscreen:
            return
        if enabled and (not self.active or self.failed or self.player is None or self.surface is None):
            return
        # Keep the video in its existing modal browser: no second window, no
        # reparented QVideoWidget and no playback restart when changing view.
        if enabled:
            controls = [(widget, widget.isHidden()) for widget in self.findChildren(QWidget)
                        if widget.parent() is self and widget is not self.surface]
            layouts = [self.layout(), self.browser.layout()]
            self.fullscreen_restore = (controls,
                                       [(layout, layout.contentsMargins(), layout.spacing()) for layout in layouts],
                                       self.browser.windowState(), self.browser.geometry())
            for widget, _ in controls:
                widget.hide()
            for layout in layouts:
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(0)
            self.video_fullscreen = True
            if not self.browser.isFullScreen():
                self.browser.showFullScreen()
            self.surface.setFocus(Qt.OtherFocusReason)
        else:
            controls, layouts, window_state, geometry = self.fullscreen_restore
            self.video_fullscreen = False
            self.fullscreen_restore = None
            for widget, hidden in controls:
                widget.setVisible(not hidden)
            for layout, margins, spacing in layouts:
                layout.setContentsMargins(margins)
                layout.setSpacing(spacing)
            if not window_state & Qt.WindowFullScreen:
                self.browser.setWindowState(window_state)
                if not window_state & Qt.WindowMaximized:
                    self.browser.setGeometry(geometry)
            self.setFocus(Qt.OtherFocusReason)

    def escape(self):
        if self.video_fullscreen:
            self.set_fullscreen(False)
        else:
            self.browser.show_overview()

    def open_videos(self, paths, path):
        self.paths = list(paths)
        self.index = self.paths.index(path)
        self.load_video()
        self.setFocus(Qt.OtherFocusReason)

    def load_video(self):
        self.stop()
        self.path = self.paths[self.index]
        self.active, self.failed = True, False
        self.name_label.setText(f"{self.index + 1} / {len(self.paths)} · {os.path.basename(self.path)}")
        self.previous_button.setEnabled(self.index > 0)
        self.next_button.setEnabled(self.index + 1 < len(self.paths))
        self.duration = 0
        self.position_slider.setValue(0)
        self.position_slider.setEnabled(False)
        self.time_label.setText("0:00 / 0:00")
        self.play_button.setEnabled(self.player is not None)
        self.fullscreen_button.setEnabled(self.player is not None)
        self.volume_slider.setEnabled(self.player is not None)
        if self.player is None:
            self.status_label.setText("Videowiedergabe ist noch nicht eingerichtet. Bitte deine Eltern um Hilfe bitten.")
            return
        if not os.path.isfile(self.path):
            self.playback_error(self.player_type.ResourceError)
            return
        self.status_label.setText("Video wird geladen …")
        self.player.setMedia(self.content_type(QUrl.fromLocalFile(os.path.abspath(self.path))))
        if not self.failed:
            self.player.play()

    def stop(self):
        self.set_fullscreen(False)
        # Ignore queued backend errors while returning, unplugging or closing.
        self.active = False
        self.path = ""
        self.fullscreen_button.setEnabled(False)
        if self.player is not None:
            self.player.stop()
            self.player.setMedia(self.content_type())

    def step(self, offset):
        target = min(max(0, self.index + offset), len(self.paths) - 1)
        if target != self.index:
            self.index = target
            self.load_video()

    def toggle_play(self):
        if not self.active or self.failed or self.player is None:
            return
        if self.player.state() == self.player_type.PlayingState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == self.player_type.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()

    def set_volume(self, value):
        if self.player is not None:
            self.player.setVolume(value)

    def duration_changed(self, value):
        if self.active:
            self.duration = max(0, value)
            self.position_changed(self.player.position())
            self.update_seekable()

    def update_seekable(self, *_):
        self.position_slider.setEnabled(bool(self.active and not self.failed and self.duration
                                            and self.player and self.player.isSeekable()))

    def position_changed(self, value):
        if not self.active:
            return
        if not self.position_slider.isSliderDown():
            blocked = self.position_slider.blockSignals(True)
            self.position_slider.setValue(round(1000 * value / self.duration) if self.duration else 0)
            self.position_slider.blockSignals(blocked)
        self.time_label.setText(clock_text(value) + " / " + clock_text(self.duration))

    def seek_changed(self, *_):
        # Also seek for keyboard/groove clicks; dragging seeks on release.
        if not self.position_slider.isSliderDown():
            self.seek()

    def seek(self):
        if self.active and not self.failed and self.player is not None and self.player.isSeekable():
            self.player.setPosition(round(self.duration * self.position_slider.value() / 1000))

    def state_changed(self, state):
        if self.active:
            self.play_button.setText("⏸ Pause" if state == self.player_type.PlayingState else "▶ Wiedergabe")

    def status_changed(self, status):
        if not self.active or self.failed:
            return
        if status == self.player_type.EndOfMedia:
            self.status_label.setText("Video zu Ende. Du kannst es noch einmal abspielen.")
        elif status == self.player_type.InvalidMedia:
            self.playback_error(self.player_type.FormatError)
        elif status in (self.player_type.LoadedMedia, self.player_type.BufferedMedia):
            self.status_label.clear()

    def playback_error(self, error):
        if not self.active or self.failed or self.player is None or error == self.player_type.NoError:
            return
        self.failed = True
        self.set_fullscreen(False)
        self.player.stop()
        self.play_button.setEnabled(False)
        self.fullscreen_button.setEnabled(False)
        self.position_slider.setEnabled(False)
        self.status_label.setText("Dieses Video kann nicht abgespielt werden. Die Datei ist möglicherweise "
                                  "beschädigt, das Format wird nicht unterstützt oder das Medium wurde entfernt.")
        log_event("Videos", os.path.basename(self.path) + ": " + self.player.errorString())
