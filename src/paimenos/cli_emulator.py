#!/usr/bin/python3
from paimenos.i18n import t, setup_qt
import sys
from paimenos.emulators import launch
try:
    launch(*sys.argv[1:])
except Exception as exc:
    print(t('PaimenOS Emulatorstart fehlgeschlagen: ') + str(exc), file=sys.stderr, flush=True)
    from PyQt5.QtWidgets import QApplication, QMessageBox
    app = QApplication([])
    setup_qt(app)
    QMessageBox.warning(None, 'Emulator', str(exc))
    sys.exit(1)
