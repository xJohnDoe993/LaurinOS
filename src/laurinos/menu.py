#!/usr/bin/env python3
from laurinos.paths import CONFIG_DIR, USER_DATA_DIR
from laurinos.paths import STATE_DIR
import json, os, shlex, shutil, socket, subprocess, sys, fcntl, traceback, threading, signal
from collections import deque
from laurinos.images import (TaskSignals, submit_task, decode_image, thumbnail, scan_images,
                            prepare_tuxpaint_image, select_tuxpaint_image, tuxpaint_command)
from laurinos.diagnostics import collect_diagnostics, diagnostics_text, log_event
from laurinos.state import read_settings, update_settings, atomic_json, remaining_seconds
from laurinos.parent_ui import ParentDialog
from laurinos.categories import CATEGORIES, available_categories, filter_category
from laurinos.controller import ControllerReader
from laurinos.network_status import NetworkStatus
from laurinos.webapp import prepare_profile, browser_command
from datetime import date
from PyQt5 import sip
from PyQt5.QtCore import Qt, QTimer, QTime, QDate, QSize
from PyQt5.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QImageReader, QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox, QInputDialog, QDialog,
    QCheckBox, QSpinBox, QFormLayout, QLineEdit, QScrollArea,
    QAbstractScrollArea, QStackedWidget, QShortcut, QPlainTextEdit, QToolButton
)

APPS_FILE = str(CONFIG_DIR / "apps.json")
SETTINGS_FILE = str(CONFIG_DIR / "settings.json")
ICONS_DIR = str(USER_DATA_DIR / "icons")
WEBAPP_BASE = os.path.expanduser("~/.mozilla/laurinos-webapps")
OVERLAY_SCRIPT = "/usr/local/lib/laurinos/current/run.py"

COLOR_PALETTE = [
    ("#FF9F00", "🍊 Orange"),
    ("#34C759", "🍏 Grün"),
    ("#007AFF", "🌊 Blau"),
    ("#AF52DE", "🍇 Violett"),
    ("#FF2D55", "🍓 Pink"),
    ("#FFCC00", "🍌 Gelb"),
    ("#5AC8FA", "🩵 Hellblau"),
    ("#34495E", "🩶 Graphit")
]

def find_program(name):
    for candidate in ([name, "luanti"] if name == "minetest" else [name]):
        found = shutil.which(candidate)
        if found:
            return found
        for directory in ("/usr/games", "/usr/local/games", "/usr/bin"):
            path = os.path.join(directory, candidate)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None

def is_online():
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=0.5):
            return True
    except OSError:
        return False

def media_roots():
    roots = []
    for base in ("/run/media/kids", "/media/kids"):
        try:
            for name in os.listdir(base):
                path = os.path.join(base, name)
                if os.path.isdir(path) and os.path.ismount(path):
                    roots.append(path)
        except OSError:
            pass
    return sorted(set(roots))

def has_media_attached():
    return bool(media_roots())

def get_battery_status():
    try:
        power_supply = "/sys/class/power_supply"
        if not os.path.isdir(power_supply):
            return None

        batteries = []
        for name in sorted(os.listdir(power_supply)):
            path = os.path.join(power_supply, name)
            if not os.path.isdir(path):
                continue
            try:
                with open(os.path.join(path, "type"), "r", encoding="utf-8") as f:
                    supply_type = f.read().strip().lower()
            except OSError:
                continue
            if supply_type != "battery":
                continue

            capacity = None
            try:
                with open(os.path.join(path, "capacity"), "r", encoding="utf-8") as f:
                    value = int(f.read().strip())
                if 0 <= value <= 100:
                    capacity = value
            except (OSError, ValueError):
                pass

            try:
                with open(os.path.join(path, "status"), "r", encoding="utf-8") as f:
                    status = f.read().strip().lower()
            except OSError:
                status = ""

            if capacity is not None:
                batteries.append((capacity, status))

        if not batteries:
            return None

        capacity = round(sum(item[0] for item in batteries) / len(batteries))
        statuses = {item[1] for item in batteries}
        charging = bool(statuses & {"charging", "full"})
        return capacity, charging
    except Exception:
        return None

def load_json(path):
    if path == SETTINGS_FILE:
        return read_settings()
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        if path == APPS_FILE:
            return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
        return value
    except (OSError, ValueError):
        return [] if path == APPS_FILE else {}

def save_json(path, data):
    try:
        if path == SETTINGS_FILE:
            update_settings(data)
        else:
            atomic_json(path, data)
        return True
    except Exception as exc:
        QMessageBox.critical(None, "Fehler", f"Speichern fehlgeschlagen: {exc}")
        return False

class LaurinOSTile(QPushButton):
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setFixedSize(220, 170)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)

        self.icon_label = QLabel(self)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: none;")

        pixmap = self.load_tile_pixmap(item)
        if not pixmap.isNull():
            self.icon_label.setPixmap(pixmap.scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self.title_label = QLabel(item.get("title", ""), self)
        self.title_label.setFont(QFont("DejaVu Sans", 15, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: white; background: transparent; border: none;")

        layout.addWidget(self.icon_label, 1)
        layout.addWidget(self.title_label, 0)

        self.setStyleSheet("""
            LaurinOSTile {
                background: rgba(255, 255, 255, 0.22);
                border: 3px solid rgba(255, 255, 255, 0.6);
                border-radius: 20px;
            }
            LaurinOSTile:hover {
                background: rgba(255, 255, 255, 0.40);
                border: 4px solid #FFFFFF;
            }
            LaurinOSTile:focus {
                background: rgba(255, 255, 255, 0.45);
                border: 6px solid #FFFFFF;
            }
        """)

    def load_tile_pixmap(self, item):
        icon_file = item.get("icon_file")
        if icon_file:
            path = os.path.join(ICONS_DIR, icon_file)
            candidates = [path]
            stem, ext = os.path.splitext(path)
            if ext.lower() != ".svg":
                candidates.append(stem + ".svg")
            for candidate in candidates:
                if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                    pix = QPixmap(candidate)
                    if not pix.isNull():
                        return pix

        icon_theme = item.get("icon_theme")
        if icon_theme and QIcon.hasThemeIcon(icon_theme):
            return QIcon.fromTheme(icon_theme).pixmap(128, 128)

        icon_text = item.get("icon_text")
        if icon_text:
            fallback = QPixmap(100, 100)
            fallback.fill(Qt.transparent)
            painter = QPainter(fallback)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QColor("white"))
            painter.setFont(QFont("DejaVu Sans", 48))
            painter.drawText(fallback.rect(), Qt.AlignCenter, icon_text)
            painter.end()
            return fallback

        fallback = QPixmap(100, 100)
        fallback.fill(Qt.transparent)
        painter = QPainter(fallback)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(255, 255, 255, 60))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, 100, 100, 20, 20)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("DejaVu Sans", 42, QFont.Bold))
        char = (item.get("title") or "?")[0].upper()
        painter.drawText(fallback.rect(), Qt.AlignCenter, char)
        painter.end()
        return fallback


class CameraImageViewer(QWidget):
    """Bildbetrachter im Kamerafenster: keine verschachtelte Dialog-Kette."""
    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.images = []
        self.index = 0
        self.zoom = 1.0
        self.pixmap = QPixmap()
        self.shortcuts = []
        self.load_generation = 0
        self.load_cancelled = threading.Event()
        self.task_signals = TaskSignals(self)
        self.task_signals.completed.connect(self.task_completed)
        layout = QVBoxLayout(self)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(False)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.image_label)
        layout.addWidget(self.scroll, 1)
        self.name_label = QLabel(self)
        self.name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label)
        controls = QGridLayout()
        for index, (text, callback) in enumerate((
            ("← Vorheriges", lambda: self.step(-1)),
            ("Nächstes →", lambda: self.step(1)),
            ("−", lambda: self.change_zoom(1 / 1.25)),
            ("+", lambda: self.change_zoom(1.25)),
            ("Einpassen", self.reset_zoom),
            ("🎨 Tux Paint", self.open_tuxpaint),
            ("Zur Übersicht", browser.show_overview),
        )):
            button = QPushButton(text, self)
            button.setAutoDefault(False)
            button.setDefault(False)
            button.clicked.connect(callback)
            controls.addWidget(button, index // 4, index % 4)
            if text == "🎨 Tux Paint":
                self.paint_button = button
        layout.addLayout(controls)
        help_label = QLabel("← / ↑ vorheriges Bild · → / ↓ nächstes Bild · + / − Zoom · Esc Übersicht", self)
        help_label.setAlignment(Qt.AlignCenter)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        for key, callback in (
            (Qt.Key_Left, lambda: self.step(-1)),
            (Qt.Key_Up, lambda: self.step(-1)),
            (Qt.Key_Right, lambda: self.step(1)),
            (Qt.Key_Down, lambda: self.step(1)),
            (Qt.Key_Plus, lambda: self.change_zoom(1.25)),
            (Qt.Key_Equal, lambda: self.change_zoom(1.25)),
            (Qt.Key_Minus, lambda: self.change_zoom(1 / 1.25)),
            (Qt.Key_Escape, browser.show_overview),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.setFocusPolicy(Qt.StrongFocus)

    def open_images(self, paths, path):
        self.images = list(paths)
        self.index = self.images.index(path)
        self.load_image()
        self.setFocus(Qt.OtherFocusReason)

    def cancel_pending(self):
        self.load_cancelled.set()
        self.load_cancelled = threading.Event()
        self.load_generation += 1
        self.paint_button.setEnabled(True)
        self.paint_button.setText("🎨 Tux Paint")

    def load_image(self):
        self.cancel_pending()
        self.zoom = 1.0
        self.pixmap = QPixmap()
        self.image_label.clear()
        self.image_label.setText("Bild wird geladen …")
        self.image_label.resize(400, 80)
        path = self.images[self.index]
        self.update_name()
        submit_task(lambda: decode_image(path), ("image", self.load_generation, path),
                    self.task_signals, self.load_cancelled)
        self.scroll.horizontalScrollBar().setValue(0)
        self.scroll.verticalScrollBar().setValue(0)

    def update_name(self):
        if self.images:
            self.name_label.setText(f"{self.index + 1} / {len(self.images)} · "
                                   f"{os.path.basename(self.images[self.index])} · {round(self.zoom * 100)} %")

    def task_completed(self, token, value, error):
        kind, generation, path = token
        if generation != self.load_generation:
            return
        if kind == "image":
            if error:
                self.image_label.setText(error)
                log_event("Bilder", f"{os.path.basename(path)}: {error}")
                return
            self.pixmap = QPixmap.fromImage(value)
            self.render_image()
        elif kind == "paint":
            self.paint_button.setEnabled(True)
            self.paint_button.setText("🎨 Tux Paint")
            if error:
                log_event("Tux Paint", error)
                QMessageBox.warning(self, "Tux Paint", f"Arbeitskopie konnte nicht erstellt werden:\n{error}")
                return
            menu = self.browser.parent()
            if not menu or getattr(menu, "active_process", None) is not None:
                return
            if "tuxpaint" in read_settings().get("disabled_apps", []):
                return
            try:
                select_tuxpaint_image(value)
                log_event("Tux Paint", "Arbeitskopie vorbereitet: " + os.path.basename(value["file"]))
                menu.launch({"command": find_program("tuxpaint"), "id": "tuxpaint"}, return_window=self.browser)
            except Exception as exc:
                log_event("Tux Paint", str(exc))
                QMessageBox.warning(self, "Tux Paint", f"Bild konnte nicht geöffnet werden:\n{exc}")

    def step(self, offset):
        target = min(max(0, self.index + offset), len(self.images) - 1)
        if target != self.index:
            self.index = target
            self.load_image()

    def reset_zoom(self):
        self.zoom = 1.0
        self.render_image()

    def change_zoom(self, factor):
        self.zoom = min(5.0, max(0.25, self.zoom * factor))
        self.render_image()

    def render_image(self):
        if sip.isdeleted(self):
            return
        if not self.images:
            return
        self.update_name()
        if self.pixmap.isNull():
            return
        viewport = self.scroll.viewport().size()
        fitted = self.pixmap.size().scaled(viewport, Qt.KeepAspectRatio)
        target = QSize(max(1, round(fitted.width() * self.zoom)),
                       max(1, round(fitted.height() * self.zoom)))
        # Die Anzeige nicht über die Auflösung der eingelesenen Vorschau vergrößern.
        if max(target.width(), target.height()) > 4096:
            target.scale(4096, 4096, Qt.KeepAspectRatio)
        self.image_label.setPixmap(self.pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.image_label.resize(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.render_image)

    def open_tuxpaint(self):
        if not self.images or not self.paint_button.isEnabled():
            return
        if not find_program("tuxpaint"):
            QMessageBox.information(self, "Tux Paint", "Tux Paint ist nicht installiert.")
            return
        if "tuxpaint" in read_settings().get("disabled_apps", []):
            QMessageBox.information(self, "Tux Paint", "Tux Paint wurde im Elternbereich deaktiviert.")
            return
        if getattr(self.browser.parent(), "active_process", None) is not None:
            return
        path = self.images[self.index]
        self.paint_button.setEnabled(False)
        self.paint_button.setText("Bild vorbereiten …")
        submit_task(lambda: prepare_tuxpaint_image(path), ("paint", self.load_generation, path),
                    self.task_signals, self.load_cancelled)


class CameraBrowser(QDialog):
    PAGE_SIZE = 60

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📷 Kamera – Bilder")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setModal(True)
        bg = read_settings().get("bg_color", "#FF9F00")
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background: {bg}; }}
            QLabel {{ color: white; font-size: 16px; }}
            QPushButton, QToolButton {{ background: rgba(255,255,255,0.25); color: white;
                border: 2px solid white; border-radius: 12px; padding: 10px;
                font-size: 16px; font-weight: bold; }}
            QPushButton:hover, QToolButton:hover {{ background: rgba(255,255,255,0.45); }}
        """)
        layout = QVBoxLayout(self)
        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack)
        self.overview = QWidget(self)
        root = QVBoxLayout(self.overview)
        header = QHBoxLayout()
        title = QLabel("📷 Kamera / SD-Karte / USB", self)
        title.setFont(QFont("DejaVu Sans", 22, QFont.Bold))
        root.addWidget(title)
        header.addStretch()
        for text, callback in (("Aktualisieren", self.reload_images),
                               ("Medium auswerfen", self.eject_media),
                               ("Hauptmenü", self.reject)):
            button = QPushButton(text, self)
            button.setAutoDefault(False)
            button.clicked.connect(callback)
            header.addWidget(button)
        root.addLayout(header)
        self.info = QLabel(self)
        root.addWidget(self.info)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(15)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)
        self.stack.addWidget(self.overview)
        self.viewer = CameraImageViewer(self)
        self.stack.addWidget(self.viewer)
        self.images = []
        self.last_path = None
        self.page = 0
        self.generation = 0
        self.cancelled = threading.Event()
        self.task_signals = TaskSignals(self)
        self.task_signals.completed.connect(self.task_completed)
        self.image_buttons = {}
        self.thumbnail_queue = deque()
        self.thumbnail_running = 0
        self.scanning = False
        pages = QHBoxLayout()
        self.page_previous = QPushButton("← Seite", self)
        self.page_next = QPushButton("Seite →", self)
        self.page_previous.clicked.connect(lambda: self.change_page(-1))
        self.page_next.clicked.connect(lambda: self.change_page(1))
        self.page_label = QLabel(self)
        self.page_label.setAlignment(Qt.AlignCenter)
        for button in (self.page_previous, self.page_next):
            button.setAutoDefault(False)
        pages.addWidget(self.page_previous)
        pages.addWidget(self.page_label, 1)
        pages.addWidget(self.page_next)
        root.addLayout(pages)
        self.roots_signature = tuple(self.media_roots())
        self.media_timer = QTimer(self)
        self.media_timer.timeout.connect(self.check_media)
        self.media_timer.start(1500)
        self.reload_images()

    def media_roots(self):
        return media_roots()

    def check_media(self):
        roots = tuple(self.media_roots())
        if roots != self.roots_signature:
            self.roots_signature = roots
            self.viewer.cancel_pending()
            self.stack.setCurrentWidget(self.overview)
            self.reload_images()

    def reset_jobs(self):
        self.cancelled.set()
        self.cancelled = threading.Event()
        self.generation += 1
        self.thumbnail_queue.clear()
        self.thumbnail_running = 0

    def clear_grid(self):
        while self.grid.count():
            widget = self.grid.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.image_buttons = {}

    def reload_images(self):
        self.reset_jobs()
        self.clear_grid()
        self.images = []
        self.page = 0
        roots = self.media_roots()
        self.roots_signature = tuple(roots)
        self.page_previous.setEnabled(False)
        self.page_next.setEnabled(False)
        self.page_label.clear()
        if not roots:
            self.scanning = False
            self.info.setText("Bitte Kamera-Speicherkarte oder USB-Medium einstecken.")
            return
        self.info.setText("Bilder werden gesucht … Du kannst jederzeit zurückgehen.")
        self.scanning = True
        cancel = self.cancelled
        submit_task(lambda: scan_images(roots, cancel), ("scan", self.generation, ""),
                    self.task_signals, cancel)

    def task_completed(self, token, value, error):
        kind, generation, path = token
        if generation != self.generation:
            return
        if kind == "scan":
            self.scanning = False
            if error:
                self.info.setText("Bilder konnten nicht gesucht werden: " + error)
                log_event("Medien", error)
                return
            self.images = value
            self.render_page()
        elif kind == "thumb":
            self.thumbnail_running -= 1
            button = self.image_buttons.get(path)
            if button:
                if error:
                    button.setText("Nicht lesbar\n" + os.path.basename(path))
                    button.setToolTip(path + "\n" + error)
                else:
                    button.setIcon(QIcon(QPixmap.fromImage(value)))
                    button.setIconSize(QSize(180, 135))
            self.schedule_thumbnails()

    def change_page(self, offset):
        maximum = max(0, (len(self.images) - 1) // self.PAGE_SIZE)
        target = min(maximum, max(0, self.page + offset))
        if target != self.page:
            self.page = target
            self.render_page()

    def render_page(self):
        self.reset_jobs()
        self.clear_grid()
        self.info.setText(f"{len(self.images)} Bild(er) gefunden.")
        pages = max(1, (len(self.images) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page_label.setText(f"Seite {self.page + 1} / {pages}")
        self.page_previous.setEnabled(self.page > 0)
        self.page_next.setEnabled(self.page + 1 < pages)
        columns = max(1, (QApplication.primaryScreen().availableGeometry().width() - 80) // 225)
        start = self.page * self.PAGE_SIZE
        for index, path in enumerate(self.images[start:start + self.PAGE_SIZE]):
            name = os.path.basename(path)
            button = QToolButton(self.container)
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setText(name if len(name) <= 23 else name[:20] + "…")
            button.setFixedSize(210, 190)
            button.setToolTip(path)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, p=path: self.preview(p))
            self.grid.addWidget(button, index // columns, index % columns)
            self.image_buttons[path] = button
            self.thumbnail_queue.append(path)
        if not self.images:
            self.grid.addWidget(QLabel("Keine unterstützten Bilder gefunden.", self), 0, 0)
        self.schedule_thumbnails()

    def schedule_thumbnails(self):
        while self.thumbnail_queue and self.thumbnail_running < 2:
            path = self.thumbnail_queue.popleft()
            self.thumbnail_running += 1
            submit_task(lambda p=path: thumbnail(p), ("thumb", self.generation, path),
                        self.task_signals, self.cancelled)

    def preview(self, path):
        if path not in self.images:
            return
        self.last_path = path
        self.stack.setCurrentWidget(self.viewer)
        self.viewer.open_images(self.images, path)
        QTimer.singleShot(0, self.viewer.render_image)

    def show_overview(self):
        if self.viewer.images:
            self.last_path = self.viewer.images[self.viewer.index]
        self.stack.setCurrentWidget(self.overview)
        self.viewer.cancel_pending()
        if self.last_path in self.images:
            wanted = self.images.index(self.last_path) // self.PAGE_SIZE
            if wanted != self.page:
                self.page = wanted
                self.render_page()
        button = self.image_buttons.get(self.last_path)
        if button:
            button.setFocus(Qt.OtherFocusReason)
            self.scroll.ensureWidgetVisible(button)

    def reject(self):
        # Auch Esc/Alt-F4 im Bildbetrachter kehrt zuerst zur Übersicht zurück.
        if self.stack.currentWidget() is self.viewer:
            self.show_overview()
        else:
            self.reset_jobs()
            self.viewer.cancel_pending()
            self.media_timer.stop()
            super().reject()

    def closeEvent(self, event):
        # Fenster-Schließen behandelt denselben Rückweg wie Esc.
        event.ignore()
        self.reject()

    def eject_media(self):
        roots = self.media_roots()
        if not roots:
            QMessageBox.information(self, "Kamera", "Kein Medium ist eingehängt.")
            return
        root = roots[0]
        if len(roots) > 1:
            choice, ok = QInputDialog.getItem(self, "Auswerfen", "Welches Medium?", roots, 0, False)
            if not ok:
                return
            root = choice
        try:
            source = subprocess.check_output(["findmnt", "--mountpoint", root, "-o", "SOURCE", "-n"],
                                             text=True, timeout=5).strip()
            marker = os.path.join(str(STATE_DIR), "laurinos-ejected.json")
            lock_path = os.path.join(str(STATE_DIR), "laurinos-media-operation.lock")
            with open(lock_path, "a", encoding="utf-8") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    with open(marker, encoding="utf-8") as handle:
                        ejected = json.load(handle)
                except (OSError, ValueError):
                    ejected = []
                result = subprocess.run(["udisksctl", "unmount", "-b", source, "--no-user-interaction"],
                                        capture_output=True, text=True, timeout=20)
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or "Auswerfen fehlgeschlagen.")
                atomic_json(marker, sorted(set(ejected + [source])))
            self.reload_images()
        except Exception as exc:
            QMessageBox.warning(self, "Auswerfen", f"Medium konnte nicht ausgeworfen werden:\n{exc}")



class ColorPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎨 Hintergrundfarbe wählen")
        self.setFixedSize(420, 260)
        self.selected_color = None

        settings = load_json(SETTINGS_FILE)
        current_bg = settings.get("bg_color", "#FF9F00")

        self.setStyleSheet("""
            QDialog { background: #222; }
            QLabel { color: white; font-size: 18px; font-weight: bold; }
        """)

        layout = QVBoxLayout(self)
        label = QLabel("Wähle deine Lieblingsfarbe:", self)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        grid = QGridLayout()
        grid.setSpacing(15)
        self.color_buttons = []

        for i, (hex_code, name) in enumerate(COLOR_PALETTE):
            btn = QPushButton(name, self)
            btn.setMinimumSize(85, 60)
            btn.setCursor(Qt.PointingHandCursor)
            
            border_style = "4px solid white" if hex_code.lower() == current_bg.lower() else "2px solid rgba(255,255,255,0.5)"
            
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_code};
                    color: white; font-size: 14px; font-weight: bold;
                    border: {border_style}; border-radius: 12px;
                }}
                QPushButton:hover, QPushButton:focus {{ border: 4px solid #FFF; }}
            """)
            btn.setFocusPolicy(Qt.StrongFocus)
            btn.clicked.connect(lambda checked=False, col=hex_code: self.choose_color(col))
            grid.addWidget(btn, i // 4, i % 4)
            self.color_buttons.append(btn)

        layout.addLayout(grid)
        self.color_buttons[0].setFocus(Qt.OtherFocusReason)

    def controller_action(self, action):
        if action == 'back':
            self.reject()
            return
        focused = self.focusWidget()
        index = self.color_buttons.index(focused) if focused in self.color_buttons else 0
        if action == 'activate':
            self.color_buttons[index].click()
            return
        step = {'left': -1, 'right': 1, 'up': -4, 'down': 4}.get(action, 0)
        target = max(0, min(len(self.color_buttons) - 1, index + step))
        self.color_buttons[target].setFocus(Qt.OtherFocusReason)

    def choose_color(self, hex_code):
        self.selected_color = hex_code
        self.accept()


class DiagnosticsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Geräte-Diagnose")
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        layout.addWidget(self.text, 1)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Aktualisieren", self)
        self.refresh_button.clicked.connect(self.refresh)
        close = QPushButton("Zurück", self)
        close.clicked.connect(self.reject)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.signals = TaskSignals(self)
        self.signals.completed.connect(self.completed)
        self.refresh()

    def refresh(self):
        self.text.setPlainText("Diagnose wird gesammelt …")
        self.refresh_button.setEnabled(False)
        submit_task(collect_diagnostics, "diagnostics", self.signals)

    def completed(self, token, value, error):
        self.refresh_button.setEnabled(True)
        self.text.setPlainText(error if error else diagnostics_text(value))



class LaurinOSMenu(QWidget):
    def __init__(self):
        super().__init__()
        self.active_process = None
        self.return_window = None
        self.camera_browser = None
        self.overlay_proc = None
        self.setWindowTitle("LaurinOS Kinder-Menü")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(40, 20, 40, 30)

        top_layout = QHBoxLayout()
        time_box = QVBoxLayout()
        self.time_label = QLabel()
        self.time_label.setFont(QFont("DejaVu Sans", 38, QFont.Bold))
        self.date_label = QLabel()
        self.date_label.setFont(QFont("DejaVu Sans", 16))

        time_box.addWidget(self.time_label)
        time_box.addWidget(self.date_label)
        top_layout.addLayout(time_box)

        self.battery_label = QLabel()
        self.battery_label.setFont(QFont("DejaVu Sans", 18, QFont.Bold))
        self.battery_label.setMinimumWidth(105)
        self.battery_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.battery_label.setToolTip("Akku")
        top_layout.addWidget(self.battery_label)

        top_layout.addStretch()

        self.timer_info_label = QLabel()
        self.timer_info_label.setFont(QFont("DejaVu Sans", 16, QFont.Bold))
        top_layout.addWidget(self.timer_info_label)

        color_btn = QPushButton("🎨 Farbe")
        color_btn.setObjectName("colorBtn")
        color_btn.setMinimumSize(120, 50)
        color_btn.setCursor(Qt.PointingHandCursor)
        color_btn.clicked.connect(self.open_color_picker)
        top_layout.addWidget(color_btn)

        parent_btn = QPushButton("🔒 Eltern-Bereich")
        parent_btn.setObjectName("parentBtn")
        parent_btn.setMinimumSize(180, 50)
        parent_btn.setCursor(Qt.PointingHandCursor)
        parent_btn.clicked.connect(self.open_parent_menu)
        top_layout.addWidget(parent_btn)
        self.toolbar_buttons = [color_btn, parent_btn]
        for btn in self.toolbar_buttons:
            btn.setFocusPolicy(Qt.StrongFocus)
        self.last_tile_index = 0

        self.main_layout.addLayout(top_layout)

        self.selected_category = 'all'
        self.visible_categories = ['all']
        self.category_bar = QWidget()
        category_layout = QHBoxLayout(self.category_bar)
        category_layout.setContentsMargins(0, 4, 0, 4)
        category_layout.addStretch()
        self.category_buttons = {}
        for key, title in CATEGORIES:
            btn = QPushButton()
            btn.setIcon(QIcon(os.path.expanduser('~/.local/share/laurinos/icons/category-' + key + '.svg')))
            btn.setIconSize(QSize(38, 38))
            btn.setFixedSize(76, 62)
            btn.setToolTip(title)
            btn.setAccessibleName(title)
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, category=key: self.select_category(category))
            category_layout.addWidget(btn)
            self.category_buttons[key] = btn
        category_layout.addStretch()
        self.main_layout.addWidget(self.category_bar)

        self.app_scroll = QScrollArea(self)
        self.app_scroll.setWidgetResizable(True)
        self.app_scroll.setFrameShape(QAbstractScrollArea.NoFrame)
        self.app_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.app_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.app_scroll.setFocusPolicy(Qt.StrongFocus)
        self.app_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.18); width: 18px; margin: 4px 0 4px 8px; border-radius: 9px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.85); min-height: 55px; border-radius: 9px;
            }
            QScrollBar::handle:vertical:hover { background: white; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        self.app_container = QWidget()
        self.grid_layout = QGridLayout(self.app_container)
        self.grid_layout.setContentsMargins(4, 10, 12, 12)
        self.grid_layout.setHorizontalSpacing(24)
        self.grid_layout.setVerticalSpacing(24)
        self.app_scroll.setWidget(self.app_container)
        self.main_layout.addWidget(self.app_scroll, 1)
        self.app_buttons = []
        self.controller_hint = QLabel('Steuerkreuz / linker Stick: wählen · Bestätigungstaste: öffnen · Schultertasten: Kategorie · Start: Farbe / Eltern · Rechte Taste: zurück')
        self.controller_hint.setFont(QFont('DejaVu Sans', 12))
        self.controller_hint.setWordWrap(True)
        self.controller_hint.setAlignment(Qt.AlignCenter)
        self.controller_hint.hide()
        self.main_layout.addWidget(self.controller_hint)

        self.network_status = NetworkStatus()
        self.last_online_state = None
        self.last_media_state = None
        self.config_signature = None

        self.apply_theme()
        self.reload_apps()

        timer = QTimer(self)
        timer.timeout.connect(self.update_clock_and_net)
        timer.start(3000)
        self.update_clock_and_net()
        self.controller = ControllerReader(self, self.controller_enabled)
        self.controller.action.connect(self.controller_action)
        self.controller.available_changed.connect(lambda count: self.controller_hint.setVisible(count > 0))
        self.controller_hint.setVisible(bool(self.controller.devices))

    def apply_theme(self):
        settings = load_json(SETTINGS_FILE)
        bg_color = settings.get("bg_color", "#FF9F00")

        self.setStyleSheet(f"""
            QWidget {{ background: {bg_color}; }}
            QLabel {{ color: white; }}
            QPushButton#parentBtn {{
                background: rgba(0, 0, 0, 0.3); color: white; border: 3px solid white; border-radius: 20px; font-size: 18px; font-weight: bold;
            }}
            QPushButton#parentBtn:hover {{ background: rgba(0, 0, 0, 0.5); }}
            QPushButton#colorBtn {{
                background: rgba(255, 255, 255, 0.3); color: white; border: 3px solid white; border-radius: 20px; font-size: 18px; font-weight: bold;
            }}
            QPushButton#colorBtn:hover {{ background: rgba(255, 255, 255, 0.5); color: #333; }}
            QPushButton#parentBtn:focus, QPushButton#colorBtn:focus {{ border: 4px solid #FFE66D; }}
        """)

        try:
            subprocess.Popen(["/usr/bin/xsetroot", "-solid", bg_color])
        except Exception:
            pass

    def open_color_picker(self):
        dlg = ColorPickerDialog(self)
        if dlg.exec_() == QDialog.Accepted and dlg.selected_color:
            settings = load_json(SETTINGS_FILE)
            save_json(SETTINGS_FILE, {"bg_color": dlg.selected_color})
            self.apply_theme()

    def reload_apps(self):
        focused = self.focusWidget()
        focused_id = focused.item.get('id') if focused in self.app_buttons else None
        toolbar_focus = focused if focused in self.toolbar_buttons else None
        online = self.network_status.value()
        media_present = has_media_attached()

        self.last_online_state = online
        self.last_media_state = media_present

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.app_buttons = []

        all_apps = load_json(APPS_FILE)
        settings = load_json(SETTINGS_FILE)
        disabled = set(settings.get("disabled_apps", []))

        visible_apps = []
        for app in all_apps:
            app_id = app.get("id")
            app_type = app.get("type")

            if app_id in disabled:
                continue

            if app.get("enabled") is False:
                continue

            if not online and app_type == "webapp":
                continue

            if app_type == "camera" and not media_present:
                continue

            visible_apps.append(app)

        tabs_enabled = settings.get('category_tabs') is True
        self.category_bar.setVisible(tabs_enabled)
        self.visible_categories = available_categories(visible_apps)
        if not tabs_enabled or self.selected_category not in self.visible_categories:
            self.selected_category = 'all'
        for key, btn in self.category_buttons.items():
            btn.setVisible(key in self.visible_categories)
            btn.setChecked(key == self.selected_category)
            btn.setStyleSheet('background:white;border:4px solid #172335;border-radius:16px;' if key == self.selected_category else 'background:rgba(255,255,255,0.65);border:2px solid transparent;border-radius:16px;')
        visible_apps = filter_category(visible_apps, self.selected_category)

        visible_apps.sort(key=lambda item: (
            2 if item.get("id") == "poweroff" else 1 if item.get("type") == "camera" else 0,
            str(item.get("title", "")).casefold()
        ))
        for row in range(self.grid_layout.rowCount()):
            self.grid_layout.setRowStretch(row, 0)
        available_width = QApplication.primaryScreen().availableGeometry().width() - 100
        self.grid_columns = min(4, max(1, (available_width + 24) // 244))
        for i, item in enumerate(visible_apps):
            tile = LaurinOSTile(item)
            tile.clicked.connect(lambda checked=False, x=item: self.launch(x))

            row, col = divmod(i, self.grid_columns)
            self.grid_layout.addWidget(tile, row, col)
            self.app_buttons.append(tile)

        for col in range(4):
            self.grid_layout.setColumnStretch(col, 0)
        self.grid_layout.setRowStretch((len(visible_apps) + self.grid_columns - 1) // self.grid_columns, 1)

        for current, nxt in zip(self.app_buttons, self.app_buttons[1:]):
            QWidget.setTabOrder(current, nxt)

        if self.app_buttons:
            self.last_tile_index = next((i for i, btn in enumerate(self.app_buttons)
                                         if btn.item.get('id') == focused_id), 0)
            self.focus_tile(self.last_tile_index)
        if toolbar_focus is not None:
            toolbar_focus.setFocus(Qt.OtherFocusReason)

    def select_category(self, category):
        if category not in self.visible_categories or not self.category_bar.isVisible():
            return
        self.selected_category = category
        self.reload_apps()
        self.app_scroll.verticalScrollBar().setValue(0)
        self.focus_tile(0)

    def cycle_category(self, direction):
        if self.category_bar.isVisible() and self.visible_categories:
            index = self.visible_categories.index(self.selected_category)
            self.select_category(self.visible_categories[(index + direction) % len(self.visible_categories)])

    def focus_tile(self, index):
        if self.app_buttons:
            self.last_tile_index = max(0, min(len(self.app_buttons) - 1, index))
            tile = self.app_buttons[self.last_tile_index]
            tile.setFocus(Qt.OtherFocusReason)
            self.app_scroll.ensureWidgetVisible(tile, 30, 30)

    def controller_enabled(self):
        if self.active_process is not None or not self.isVisible():
            return False
        if QApplication.applicationState() != Qt.ApplicationActive:
            return False
        modal = QApplication.activeModalWidget()
        # Nur der Kinder-Farbwähler ist per Controller bedienbar, keine PIN/Eltern-Dialoge.
        if modal is not None:
            return isinstance(modal, ColorPickerDialog) and modal.parent() is self
        return QApplication.activeWindow() is self

    def controller_action(self, action):
        if not self.controller_enabled():
            return
        modal = QApplication.activeModalWidget()
        if modal is not None:
            modal.controller_action(action)
            return
        if action in ('category_prev', 'category_next'):
            self.cycle_category(-1 if action == 'category_prev' else 1)
            return
        focused = self.focusWidget()
        if action == 'toolbar':
            self.toolbar_buttons[0].setFocus(Qt.OtherFocusReason)
            return
        if focused in self.toolbar_buttons:
            index = self.toolbar_buttons.index(focused)
            if action == 'activate':
                focused.click()
            elif action in ('back', 'down'):
                self.focus_tile(self.last_tile_index)
            elif action in ('left', 'right'):
                target = max(0, min(1, index + (1 if action == 'right' else -1)))
                self.toolbar_buttons[target].setFocus(Qt.OtherFocusReason)
            return
        if not self.app_buttons:
            self.toolbar_buttons[0].setFocus(Qt.OtherFocusReason)
            return
        index = self.app_buttons.index(focused) if focused in self.app_buttons else self.last_tile_index
        if action == 'activate':
            self.app_buttons[index].click()
        elif action == 'back':
            self.focus_tile(0)
        elif action == 'up' and index < self.grid_columns:
            self.last_tile_index = index
            self.toolbar_buttons[0].setFocus(Qt.OtherFocusReason)
        else:
            step = {'left': -1, 'right': 1, 'up': -self.grid_columns, 'down': self.grid_columns}.get(action, 0)
            self.focus_tile(index + step)

    def closeEvent(self, event):
        self.controller.close()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        key = event.key()

        if key in (Qt.Key_Tab, Qt.Key_Backtab):
            super().keyPressEvent(event)
            return

        if not self.app_buttons:
            super().keyPressEvent(event)
            return

        focused = self.focusWidget()
        try:
            index = self.app_buttons.index(focused)
        except ValueError:
            index = 0

        target = index
        if key == Qt.Key_Left:
            target = max(0, index - 1)
        elif key == Qt.Key_Right:
            target = min(len(self.app_buttons) - 1, index + 1)
        elif key == Qt.Key_Up:
            target = max(0, index - self.grid_columns)
        elif key == Qt.Key_Down:
            candidate = index + self.grid_columns
            target = min(len(self.app_buttons) - 1, candidate)
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.app_buttons[index].click()
            return
        elif key == Qt.Key_Home:
            target = 0
        elif key == Qt.Key_End:
            target = len(self.app_buttons) - 1
        else:
            super().keyPressEvent(event)
            return

        if target != index:
            self.app_buttons[target].setFocus(Qt.OtherFocusReason)
            self.app_scroll.ensureWidgetVisible(self.app_buttons[target], 30, 30)
        event.accept()

    def open_parent_menu(self):
        settings = load_json(SETTINGS_FILE)
        correct_pin = settings["pin"]

        pin, ok = QInputDialog.getText(
            self, "🔒 Eltern-PIN", "Bitte Eltern-PIN eingeben:", QLineEdit.Password
        )

        if ok and pin == correct_pin:
            dlg = ParentDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                self.reload_apps()
        elif ok:
            QMessageBox.warning(self, "Falsch", "Falscher PIN!")

    def launch(self, item, return_window=None):
        if getattr(self, "active_process", None) is not None:
            return
        if item.get("command") == "__POWEROFF__":
            subprocess.Popen(["systemctl", "poweroff"], start_new_session=True)
            return
        if item.get("command") == "__CAMERA__":
            dialog = getattr(self, "camera_browser", None)
            if dialog is None or sip.isdeleted(dialog):
                dialog = CameraBrowser(self)
                self.camera_browser = dialog
                dialog.finished.connect(lambda result, browser=dialog: self.camera_finished(browser))
            # Kein exec_(): hide() beim Start von Tux Paint würde dessen
            # verschachtelte Ereignisschleife beenden und das Fenster löschen.
            dialog.showFullScreen()
            dialog.raise_()
            dialog.activateWindow()
            return
        url = item.get("url")
        if url:
            # Profilname darf das Profilverzeichnis nicht verlassen.
            profile = os.path.basename(item.get("profile") or "webapp")
            if profile in (".", ".."):
                profile = "webapp"
            profile_dir = os.path.join(WEBAPP_BASE, profile)
            user_js = os.path.expanduser("~/.mozilla/firefox/laurinos-user.js")
            try:
                prepare_profile(profile_dir, user_js)
            except OSError as exc:
                log_event("Webapp", str(exc))
                QMessageBox.warning(self, "Webapp", f"Webapp konnte nicht vorbereitet werden:\n{exc}")
                return
            cmd = browser_command(profile_dir, url)
        else:
            cmd = shlex.split(item.get("command", ""))
            if cmd:
                cmd[0] = find_program(cmd[0]) or cmd[0]
        if cmd and (item.get("id") == "tuxpaint" or os.path.basename(cmd[0]) == "tuxpaint"):
            cmd = tuxpaint_command(cmd[0], cmd[1:])
        if not cmd:
            return
        self.return_window = return_window
        # Der Menü-Knopf beendet Firefox absichtlich mit SIGTERM.
        self.expected_exit_codes = {0, -signal.SIGTERM} if url else {0}
        self.overlay_proc = None
        try:
            log_path = os.path.join(str(STATE_DIR), "laurinos-application.log")
            # Pro Start begrenzt: kein über Monate wachsendes gemeinsames Log.
            self.application_log = open(log_path, "w", encoding="utf-8")
            log_event("Anwendung", "Start: " + os.path.basename(cmd[0]))
            self.active_process = subprocess.Popen(cmd, start_new_session=True,
                                                   stdout=self.application_log, stderr=self.application_log)
        except Exception as exc:
            if getattr(self, "application_log", None):
                self.application_log.close()
            log_event("Anwendung", str(exc))
            QMessageBox.critical(self, "Fehler", f"Fehler beim Starten:\n{exc}")
            return
        self.hide()
        if return_window:
            return_window.hide()
        if url:
            try:
                self.overlay_proc = subprocess.Popen([sys.executable, "-I", OVERLAY_SCRIPT, "close_overlay", str(self.active_process.pid)])
            except OSError as exc:
                print(f"Schließen-Overlay konnte nicht gestartet werden: {exc}", file=sys.stderr)
        self.process_timer = QTimer(self)
        self.process_timer.timeout.connect(self.check_process)
        self.process_timer.start(250)

    def check_process(self):
        if self.active_process is None or self.active_process.poll() is None:
            return
        self.process_timer.stop()
        self.process_timer.deleteLater()
        if self.overlay_proc and self.overlay_proc.poll() is None:
            self.overlay_proc.terminate()
        code = self.active_process.returncode
        self.application_log.close()
        self.active_process = None
        target = self.return_window
        self.return_window = None
        if target is None or sip.isdeleted(target):
            target = self
        self.showFullScreen()
        target.showFullScreen()
        target.raise_()
        target.activateWindow()
        if code not in self.expected_exit_codes:
            log_event("Anwendung", f"Programm mit Fehlercode {code} beendet.")
            QMessageBox.warning(target, "Programmstart", f"Das Programm wurde mit Fehlercode {code} beendet.\n"
                                "Details stehen im Elternbereich unter Geräte-Diagnose.")

    def camera_finished(self, browser):
        if getattr(self, "camera_browser", None) is browser:
            self.camera_browser = None
        if getattr(self, "return_window", None) is browser:
            self.return_window = None
        browser.deleteLater()
        if getattr(self, "active_process", None) is None:
            self.showFullScreen()
            self.raise_()
            self.activateWindow()

    def update_clock_and_net(self):
        self.time_label.setText(QTime.currentTime().toString("HH:mm"))
        self.date_label.setText(QDate.currentDate().toString("dddd, d. MMMM yyyy"))

        battery = get_battery_status()
        if battery is None:
            self.battery_label.clear()
            self.battery_label.setToolTip("")
        else:
            capacity, charging = battery
            if capacity >= 80:
                icon = "🔋"
            elif capacity >= 50:
                icon = "🔋"
            elif capacity >= 20:
                icon = "🪫"
            else:
                icon = "🪫"
            prefix = "⚡ " if charging else ""
            self.battery_label.setText(f"{prefix}{icon} {capacity}%")
            self.battery_label.setToolTip(
                f"Akku: {capacity}%" + (" – wird geladen" if charging else "")
            )

        request_file = os.path.join(str(STATE_DIR), "laurinos-menu.raise")
        if os.path.exists(request_file):
            os.unlink(request_file)
            if getattr(self, "active_process", None) is None:
                target = QApplication.activeModalWidget() or self
                target.showFullScreen()
                target.raise_()
                target.activateWindow()
        current_online = self.network_status.value()
        current_media = has_media_attached()

        settings = load_json(SETTINGS_FILE)
        signature = (os.stat(APPS_FILE).st_mtime_ns if os.path.exists(APPS_FILE) else 0,
                     tuple(settings.get("disabled_apps", [])), settings.get("bg_color"), settings.get("category_tabs", False))
        config_changed = signature != self.config_signature
        if config_changed:
            self.config_signature = signature
            self.apply_theme()
        if config_changed or current_online != self.last_online_state or current_media != self.last_media_state:
            self.reload_apps()

        settings = load_json(SETTINGS_FILE)
        limit_min = settings.get("daily_limit_minutes", 0)
        bonus_min = settings.get("bonus_minutes", 0)
        total_limit_min = limit_min + bonus_min

        if limit_min > 0:
            used_sec = settings.get("today_used_seconds", 0)
            rem_sec = max(0, (total_limit_min * 60) - used_sec)
            rem_min = rem_sec // 60
            self.timer_info_label.setText(f"⏳ Restzeit: {rem_min} Min.")
        else:
            self.timer_info_label.setText("")

def report_exception(kind, value, trace):
    # Qt-Slot-Ausnahmen nachvollziehbar machen, statt das Menü still zu beenden.
    details = "".join(traceback.format_exception(kind, value, trace))
    print(details, file=sys.stderr)
    try:
        with open(os.path.join(str(STATE_DIR), "laurinos-errors.log"), "a", encoding="utf-8") as handle:
            handle.write(details + "\n")
    except OSError:
        pass
    QMessageBox.critical(QApplication.activeWindow(), "LaurinOS-Fehler", str(value))

if __name__ == "__main__":
    instance = open(os.path.join(str(STATE_DIR), "laurinos-menu.lock"), "a")
    try:
        fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        Path = os.path.join(str(STATE_DIR), "laurinos-menu.raise")
        with open(Path, "w", encoding="utf-8"):
            pass
        sys.exit(0)
    sys.excepthook = report_exception
    app = QApplication(sys.argv)
    window = LaurinOSMenu()
    window.showFullScreen()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec_())
