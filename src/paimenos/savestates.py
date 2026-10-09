"""Select the newest state and prepare RetroArch's explicit auto-load path."""
import os
from pathlib import Path
import re
import shutil
import tempfile


def write_status(marker, status):
    """Atomically persist whether this game may be resumed after a restart."""
    marker = Path(marker)
    fd, temporary = tempfile.mkstemp(prefix='.session-', dir=marker.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(status)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, marker)
        directory = os.open(marker.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare_resume(states, game):
    states, game = Path(states), Path(game)
    folder = states / game.parent.name
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink() or folder.resolve().parent != states.resolve():
        raise ValueError('Unsafe savestate directory')
    marker = folder / 'session-status'
    # Older installations have no status: recover an existing save once.
    resume_allowed = not marker.exists() or marker.read_text() != 'clean'
    # Legacy content-directory sorting, including optional core subdirectories.
    # Never take a same-named ROM's state from a different game ID.
    pattern = re.compile(re.escape(game.stem) + r'\.state(?:\d+|\.auto)?$')
    candidates = []
    for directory, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
        for name in files:
            path = Path(directory) / name
            if pattern.fullmatch(name) and not path.is_symlink() and path.is_file():
                stat = path.stat()
                if stat.st_size:
                    candidates.append((stat.st_mtime_ns, str(path), path))
    target_dir = folder / 'paimenos-resume'
    target_dir.mkdir(exist_ok=True)
    if target_dir.is_symlink():
        raise ValueError('Unsafe resume directory')
    base = target_dir / (game.stem + '.state')
    target = Path(str(base) + '.auto')
    selected = max(candidates, key=lambda item: (item[0], item[2] == target, item[1]))[2] if candidates and resume_allowed else None
    if target.is_symlink():
        raise ValueError('Unsafe resume state')
    if selected is not None and selected != target:
        if target.exists():
            fd, backup = tempfile.mkstemp(prefix=target.name + '.previous-', dir=target_dir)
            os.close(fd)
            shutil.copy2(target, backup)
        fd, temporary = tempfile.mkstemp(prefix='.resume-', dir=target_dir)
        try:
            with os.fdopen(fd, 'wb') as out, selected.open('rb') as source:
                shutil.copyfileobj(source, out)
                out.flush()
                os.fsync(out.fileno())
            # A copied old state must not appear newer than a real save.
            shutil.copystat(selected, temporary)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return base, selected, marker
