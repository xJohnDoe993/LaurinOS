"""Local photo/video discovery, independent of Qt and playback codecs."""
import os

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".mpg", ".mpeg",
              ".3gp", ".mts", ".m2ts", ".ts", ".ogv"}


def is_video(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def scan_media(roots, cancelled, extensions=None):
    extensions = IMAGE_EXTS | VIDEO_EXTS if extensions is None else extensions
    found = set()
    for root in roots:
        for directory, subdirs, names in os.walk(root):
            if cancelled.is_set():
                return []
            subdirs[:] = [name for name in subdirs
                          if not name.startswith(".") and name != "System Volume Information"]
            for name in names:
                if cancelled.is_set():
                    return []
                if os.path.splitext(name)[1].lower() in extensions:
                    path = os.path.join(directory, name)
                    if os.path.isfile(path) and not os.path.islink(path):
                        found.add(path)
    return sorted(found, key=lambda path: (os.path.basename(path).casefold(), path))
