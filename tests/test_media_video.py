import os
import subprocess
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from laurinos.media_files import scan_media, is_video, IMAGE_EXTS


class MediaDiscoveryTests(unittest.TestCase):
    def test_mixed_media_case_nested_names_and_hidden_directories(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            root = Path(folder)
            names = ['DCIM/ä Urlaub.MOV', 'DCIM/b.MP4', 'a.JPG', 'b.txt',
                     '.cache/hidden.mp4', 'System Volume Information/hidden.jpg']
            for name in names:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.touch()
            result = scan_media([root, root], threading.Event())
            self.assertEqual([Path(p).name for p in result], ['a.JPG', 'b.MP4', 'ä Urlaub.MOV'])
            self.assertEqual(scan_media([root], threading.Event(), IMAGE_EXTS), [str(root / 'a.JPG')])
            self.assertTrue(is_video(result[-1])); self.assertFalse(is_video(result[0]))

    def test_cancelled_scan_and_links_do_not_open_other_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            root = Path(folder)
            (root / 'clip.mp4').touch()
            (root / 'linked.mp4').symlink_to(root / 'clip.mp4')
            (root / 'directory.mp4').mkdir()
            self.assertEqual(scan_media([root], threading.Event()), [str(root / 'clip.mp4')])
            cancelled = threading.Event(); cancelled.set()
            self.assertEqual(scan_media([root], cancelled), [])


try:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PyQt5.QtCore import QObject, QUrl, pyqtSignal
    from PyQt5.QtWidgets import QApplication, QDialog, QWidget
    from laurinos import video
    HAS_QT = True
except ImportError:
    HAS_QT = False


if HAS_QT:
    class FakeContent:
        def __init__(self, url=None): self.url = url

    class FakePlayer(QObject):
        positionChanged = pyqtSignal(int)
        durationChanged = pyqtSignal(int)
        seekableChanged = pyqtSignal(bool)
        stateChanged = pyqtSignal(int)
        mediaStatusChanged = pyqtSignal(int)
        error = pyqtSignal(int)
        NoError, ResourceError, FormatError = 0, 1, 2
        StoppedState, PlayingState, PausedState = 0, 1, 2
        LoadedMedia, BufferedMedia, EndOfMedia, InvalidMedia = 3, 6, 7, 8

        def __init__(self, parent):
            super().__init__(parent)
            self.content = FakeContent()
            self.current_state, self.current_status, self.current_position = 0, 3, 0
            self.volume, self.stops = 0, 0
        def setVideoOutput(self, output): self.output = output
        def setVolume(self, volume): self.volume = volume
        def setMedia(self, content): self.content = content
        def state(self): return self.current_state
        def mediaStatus(self): return self.current_status
        def position(self): return self.current_position
        def isSeekable(self): return True
        def errorString(self): return 'Test decoder error'
        def play(self):
            self.current_state = self.PlayingState
            self.stateChanged.emit(self.current_state)
        def pause(self):
            self.current_state = self.PausedState
            self.stateChanged.emit(self.current_state)
        def stop(self):
            self.stops += 1
            self.current_state = self.StoppedState
            self.stateChanged.emit(self.current_state)
        def setPosition(self, position):
            self.current_position = position
            self.positionChanged.emit(position)


@unittest.skipUnless(HAS_QT, 'Optional Qt widget tests require PyQt5.')
class VideoWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        try:
            from laurinos import menu
        except ImportError as exc:
            raise unittest.SkipTest('Camera widget tests need menu dependencies: ' + str(exc))
        cls.menu = menu

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        self.clip = str(self.root / 'Urlaub #1 ä.MP4'); Path(self.clip).touch()
        self.second = str(self.root / 'second.mov'); Path(self.second).touch()
        self.photo = str(self.root / 'photo.jpg'); Path(self.photo).touch()
        self.patches = [patch.object(video, 'load_backend', return_value=(FakePlayer, FakeContent, QWidget)),
                        patch.object(video, 'log_event'),
                        patch.object(self.menu, 'read_settings', return_value={'bg_color': '#FF9F00'}),
                        patch.object(self.menu, 'media_roots', return_value=[]),
                        patch.object(self.menu, 'submit_task')]
        for item in self.patches: item.start()
        self.browser = self.menu.CameraBrowser()
        self.viewer = self.browser.video_viewer
        self.browser.images = [self.clip, self.photo, self.second]
    def tearDown(self):
        self.browser.done(QDialog.Rejected)
        self.browser.deleteLater(); self.app.processEvents()
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def test_video_local_url_and_photo_navigation_stay_separate(self):
        self.browser.preview(self.clip)
        self.assertIs(self.browser.stack.currentWidget(), self.viewer)
        self.assertEqual(self.viewer.paths, [self.clip, self.second])
        self.assertEqual(self.viewer.player.content.url.toLocalFile(), self.clip)
        self.assertEqual(self.viewer.player.state(), FakePlayer.PlayingState)
        self.browser.preview(self.photo)
        self.assertEqual(self.browser.viewer.images, [self.photo])
        self.assertIsNone(self.viewer.player.content.url)

    def test_pause_seek_volume_and_replay_at_end(self):
        self.browser.preview(self.clip)
        self.viewer.play_button.click()
        self.assertEqual(self.viewer.player.state(), FakePlayer.PausedState)
        self.viewer.duration_changed(8000)
        self.viewer.position_slider.setValue(500)
        self.assertEqual(self.viewer.player.position(), 4000)
        self.assertEqual(self.viewer.time_label.text(), '0:04 / 0:08')
        self.viewer.volume_slider.setValue(30)
        self.assertEqual(self.viewer.player.volume, 30)
        self.viewer.player.current_status = FakePlayer.EndOfMedia
        self.viewer.status_changed(FakePlayer.EndOfMedia)
        self.viewer.play_button.click()
        self.assertEqual(self.viewer.player.position(), 0)
        self.assertEqual(self.viewer.player.state(), FakePlayer.PlayingState)

    def test_back_and_close_release_file_and_ignore_late_errors(self):
        self.browser.preview(self.clip)
        self.browser.reject()
        self.assertIs(self.browser.stack.currentWidget(), self.browser.overview)
        self.assertFalse(self.viewer.active)
        self.assertIsNone(self.viewer.player.content.url)
        video.log_event.reset_mock()
        self.viewer.player.error.emit(FakePlayer.FormatError)
        video.log_event.assert_not_called()
        self.browser.preview(self.second)
        self.browser.done(QDialog.Accepted)
        self.assertIsNone(self.viewer.player.content.url)
        self.assertFalse(self.browser.media_timer.isActive())

    def test_unplug_stops_playback_and_clears_overview(self):
        self.browser.preview(self.clip)
        self.browser.roots_signature = ('/media/kids/camera',)
        self.browser.check_media()
        self.assertIsNone(self.viewer.player.content.url)
        self.assertFalse(self.viewer.active)
        self.assertEqual(self.browser.images, [])
        self.assertIs(self.browser.stack.currentWidget(), self.browser.overview)

    def test_decode_failure_does_not_prevent_next_clip(self):
        self.browser.preview(self.clip)
        self.viewer.player.error.emit(FakePlayer.FormatError)
        self.assertFalse(self.viewer.play_button.isEnabled())
        self.assertIn('nicht abgespielt', self.viewer.status_label.text())
        self.viewer.next_button.click()
        self.assertEqual(self.viewer.path, self.second)
        self.assertTrue(self.viewer.play_button.isEnabled())
        self.assertEqual(self.viewer.player.state(), FakePlayer.PlayingState)

    def test_eject_releases_video_before_unmount(self):
        self.browser.preview(self.clip)
        def unmount(command, **kwargs):
            self.assertEqual(command[:2], ['udisksctl', 'unmount'])
            self.assertIsNone(self.viewer.player.content.url)
            self.assertFalse(self.viewer.active)
            return subprocess.CompletedProcess(command, 0, stdout='', stderr='')
        with patch.object(self.menu, 'media_roots', return_value=['/media/kids/camera']), \
                patch.object(self.menu, 'STATE_DIR', self.root), \
                patch.object(self.menu.subprocess, 'check_output', return_value='/dev/test1\n'), \
                patch.object(self.menu.subprocess, 'run', side_effect=unmount):
            self.browser.eject_media()

    def test_escape_returns_to_overview_then_closes(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        self.browser.preview(self.clip)
        self.browser.show(); self.browser.activateWindow(); self.viewer.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.viewer, Qt.Key_Escape)
        self.assertIs(self.browser.stack.currentWidget(), self.browser.overview)
        self.assertIsNone(self.viewer.player.content.url)
        QTest.keyClick(self.browser, Qt.Key_Escape)
        self.assertFalse(self.browser.isVisible())

    def test_missing_multimedia_keeps_photos_and_overview_available(self):
        with patch.object(video, 'load_backend', side_effect=ImportError('missing multimedia')):
            viewer = video.CameraVideoViewer(self.browser)
        viewer.open_videos([self.clip], self.clip)
        self.assertIsNone(viewer.player)
        self.assertFalse(viewer.play_button.isEnabled())
        self.assertIn('Eltern', viewer.status_label.text())
        self.browser.preview(self.photo)
        self.assertIs(self.browser.stack.currentWidget(), self.browser.viewer)
        viewer.stop(); viewer.deleteLater()


if __name__ == '__main__': unittest.main()
