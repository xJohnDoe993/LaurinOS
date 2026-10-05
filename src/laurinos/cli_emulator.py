#!/usr/bin/python3
import sys
from laurinos.emulators import launch
try:
    launch(*sys.argv[1:])
except Exception as exc:
    print('LaurinOS Emulatorstart fehlgeschlagen: ' + str(exc), file=sys.stderr, flush=True)
    from PyQt5.QtWidgets import QApplication, QMessageBox
    app = QApplication([])
    QMessageBox.warning(None, 'Emulator', str(exc))
    sys.exit(1)
