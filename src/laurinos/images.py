"""Bildarbeit außerhalb des GUI-Threads; QPixmap bleibt im GUI-Thread."""
import hashlib
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QImageReader

CACHE_DIR = os.path.expanduser("~/.cache/laurinos/thumbnails")
TUXPAINT_DIR = os.path.expanduser("~/.tuxpaint")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
_prune_lock = threading.Lock()
_last_prune = 0.0


class TaskSignals(QObject):
    completed = pyqtSignal(object, object, str)


class ImageTask(QRunnable):
    def __init__(self, operation, token, signals, cancelled=None):
        super().__init__()
        self.operation, self.token, self.signals = operation, token, signals
        self.cancelled = cancelled

    def run(self):
        if self.cancelled and self.cancelled.is_set():
            return
        value, error = None, ""
        try:
            value = self.operation()
        except Exception as exc:
            error = str(exc)
        if self.cancelled and self.cancelled.is_set():
            return
        try:
            self.signals.completed.emit(self.token, value, error)
        except RuntimeError:
            # Empfänger wurde inzwischen geschlossen; kein Zugriff auf GUI-Objekte.
            pass


def submit_task(operation, token, signals, cancelled=None):
    pool = QThreadPool.globalInstance()
    pool.setMaxThreadCount(2)
    pool.start(ImageTask(operation, token, signals, cancelled))


def decode_image(path, maximum=2560):
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        if size.width() * size.height() > 120_000_000:
            raise ValueError("Das Bild ist zu groß (mehr als 120 Millionen Pixel).")
        if max(size.width(), size.height()) > maximum:
            size.scale(maximum, maximum, Qt.KeepAspectRatio)
            reader.setScaledSize(size)
    image = reader.read()
    if image.isNull():
        raise ValueError("Bild nicht lesbar oder Medium entfernt: " + reader.errorString())
    if max(image.width(), image.height()) > maximum:
        return image.scaled(maximum, maximum, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return image


def save_png(image, destination):
    directory = os.path.dirname(destination)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".image-", suffix=".png", dir=directory)
    os.close(fd)
    try:
        if not image.save(temporary, "PNG"):
            raise OSError("Bild konnte nicht als PNG gespeichert werden.")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def thumbnail(path):
    stat = os.stat(path)
    key = hashlib.sha256((os.path.realpath(path) + f"|{stat.st_mtime_ns}|{stat.st_size}|v1").encode()).hexdigest()
    destination = os.path.join(CACHE_DIR, key + ".png")
    cached = QImage(destination) if os.path.isfile(destination) else QImage()
    if not cached.isNull():
        return cached
    image = decode_image(path, 180)
    image = image.scaled(180, 145, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    try:
        save_png(image, destination)
        prune_cache()
    except OSError:
        pass  # Fehlender Cache darf die Bildanzeige nicht verhindern.
    return image


def prune_cache():
    global _last_prune
    with _prune_lock:
        now = time.monotonic()
        if now - _last_prune < 60:
            return
        _last_prune = now
        files = [entry for entry in os.scandir(CACHE_DIR) if entry.name.endswith(".png") and entry.is_file()]
        if len(files) > 500:
            for entry in sorted(files, key=lambda entry: entry.stat().st_mtime)[:-500]:
                try:
                    os.unlink(entry.path)
                except OSError:
                    pass


def scan_images(roots, cancelled):
    found = []
    for root in roots:
        for directory, subdirs, names in os.walk(root):
            if cancelled.is_set():
                return []
            subdirs[:] = [name for name in subdirs if not name.startswith(".") and name != "System Volume Information"]
            for name in names:
                if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                    found.append(os.path.join(directory, name))
    return sorted(set(found), key=lambda path: (os.path.basename(path).casefold(), path))


def prepare_tuxpaint_image(path):
    """Arbeitskopie speichern. current_id wird erst im GUI vor dem Start gesetzt."""
    image = decode_image(path, 2560)
    image_id = datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:8]
    destination = os.path.join(TUXPAINT_DIR, "saved", image_id + ".png")
    # Transparenz auf eine weiße Zeichenfläche reduzieren.
    from PyQt5.QtGui import QPainter
    canvas = QImage(image.size(), QImage.Format_RGB32)
    canvas.fill(Qt.white)
    painter = QPainter(canvas)
    painter.drawImage(0, 0, image)
    painter.end()
    save_png(canvas, destination)
    thumb = canvas.scaled(92, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    try:
        save_png(thumb, os.path.join(TUXPAINT_DIR, "saved", ".thumbs", image_id + "-t.png"))
    except OSError:
        pass
    return {"image_id": image_id, "file": destination, "savedir": TUXPAINT_DIR}


def select_tuxpaint_image(prepared):
    directory = prepared["savedir"]
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".current-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            # Tux Paint entfernt das letzte Zeichen; die abschließende Zeile ist nötig.
            handle.write(prepared["image_id"] + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, os.path.join(directory, "current_id.txt"))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def tuxpaint_command(program, extra=()):
    # Laut Debian 12/13 unterstützt: Vollbild in nativer Displayauflösung.
    args = list(extra)
    filtered = []
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--savedir":
            skip_next = True
            continue
        if arg == "--fullscreen":
            skip_next = index + 1 < len(args) and args[index + 1] in ("yes", "no", "native")
            continue
        if arg in ("--windowed", "--startblank", "--nosave", "--lockfile") or arg.startswith(("--fullscreen=", "--savedir=")):
            continue
        filtered.append(arg)
    return [program] + filtered + ["--fullscreen=native", "--savedir", TUXPAINT_DIR,
                                  "--startlast", "--save", "--nolockfile"]
