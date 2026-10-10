"""Local parent tabs for USB backups and updates, using the same backends as the web."""
from datetime import datetime

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox,
    QMessageBox, QPlainTextEdit, QProgressBar)

from paimenos.i18n import t
from paimenos.images import TaskSignals, submit_task
from paimenos.parent_ui import label, button, card, scroll_page


def gib(size):
    return t('{value0} GiB', value0=f'{size / 1073741824:.1f}')


class BackupsTab(QWidget):
    """Same selection and confirmation rules as assets/parent-web/backups.html."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from paimenos import backups
        self.backups = backups
        page, layout = scroll_page()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(page)
        top = card(layout, t('USB-Medium'))
        top.addWidget(label(t('USB-Medium anschließen und laufende Spiele und Apps beenden. Das Medium wird nicht formatiert. Backups sind unverschlüsselt.'), True))
        row = QHBoxLayout()
        self.device = QComboBox(); self.device.currentIndexChanged.connect(self.load_backups)
        row.addWidget(self.device, 1)
        self.reload_button = button(t('Medien und Backups neu einlesen'), self.load_drives, secondary=True)
        row.addWidget(self.reload_button)
        top.addLayout(row)
        self.status = label('', True); top.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.setTextVisible(False); self.progress.hide()
        top.addWidget(self.progress)
        self.recover_button = button(t('Unterbrochene Wiederherstellung reparieren'), lambda: self.start('recover', []))
        self.recover_button.hide(); top.addWidget(self.recover_button)

        self.create_card = card(layout, t('Backup erstellen'))
        self.group_boxes = {}
        labels = backups.labels()
        for key in backups.offered():
            box = QCheckBox(labels[key])
            box.setChecked(key != 'files')  # Personal files can be large: opt in.
            self.group_boxes[key] = box
            self.create_card.addWidget(box)
        self.create_button = button(t('Auf USB sichern'), self.create_backup)
        self.create_card.addWidget(self.create_button)

        found_card = card(layout, t('Erkannte Backups'))
        found_card.addWidget(label(t('Beim Wiederherstellen werden gleichnamige Dateien ersetzt; zusätzliche vorhandene Dateien bleiben erhalten. Die Prüfsummen werden vor der Übernahme geprüft. Emulatoren und Apps müssen auf diesem Gerät separat installiert sein.'), True))
        self.found = QVBoxLayout(); found_card.addLayout(self.found)
        layout.addStretch()

        self.signals = TaskSignals(self); self.signals.completed.connect(self.completed)
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(1000)
        self.was_running = False
        self.poll()
        self.load_drives()

    def load_drives(self):
        self.reload_button.setEnabled(False)
        self.status.setText(t('USB-Medien werden gesucht …'))
        submit_task(self.backups.drives, 'drives', self.signals)

    def load_backups(self, *args):
        device = self.device.currentData()
        self.clear_found()
        if device:
            submit_task(lambda: self.backups.available(device), ('found', device), self.signals)

    def completed(self, token, value, error):
        if token == 'drives':
            self.reload_button.setEnabled(True)
            selected = self.device.currentData()
            self.device.blockSignals(True); self.device.clear()
            for drive in ([] if error else value or []):
                self.device.addItem(drive['label'] + ' · ' + gib(drive['free']) + ' ' + t('frei'), drive['id'])
            index = self.device.findData(selected)
            self.device.setCurrentIndex(max(0, index))
            self.device.blockSignals(False)
            if error:
                self.status.setText(error)
            elif not self.device.count():
                self.status.setText(t('Kein eingebundenes USB-Medium erkannt. Bitte anschließen und erneut einlesen.'))
            else:
                self.status.setText(self.backups.job_status()['message'])
            self.update_buttons()
            self.load_backups()
        elif isinstance(token, tuple) and token[0] == 'found' and token[1] == self.device.currentData():
            if error:
                self.status.setText(error)
            self.render_found([] if error else value or [])

    def clear_found(self):
        while self.found.count():
            widget = self.found.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def render_found(self, found):
        self.clear_found()
        if not found:
            self.found.addWidget(label(t('Keine vollständigen PaimenOS-Backups auf diesem Medium gefunden.'), True))
        labels = self.backups.labels()
        for backup in found:
            box = QWidget(); box.setObjectName('card'); inner = QVBoxLayout(box)
            inner.addWidget(label(backup['date'] + ' · ' + gib(backup['size'])))
            groups = {}
            for key in backup['groups']:
                check = QCheckBox(labels.get(key, key)); check.setChecked(True)
                groups[key] = check; inner.addWidget(check)
            confirm = QCheckBox(t('Vorhandene Dateien der Auswahl dürfen ersetzt werden.'))
            inner.addWidget(confirm)
            restore = button(t('Auswahl wiederherstellen'), lambda checked=False, b=backup, g=groups, c=confirm: self.restore(b, g, c))
            restore.setProperty('backup_action', True)
            inner.addWidget(restore)
            self.found.addWidget(box)
        self.update_buttons()

    def selected(self, boxes):
        return [key for key, box in boxes.items() if box.isChecked()]

    def create_backup(self):
        self.start('create', self.selected(self.group_boxes))

    def restore(self, backup, groups, confirm):
        if not confirm.isChecked():
            QMessageBox.warning(self, t('USB-Backups'), t('Bitte das Ersetzen vorhandener Dateien bestätigen.'))
            return
        self.start('restore', self.selected(groups), backup['id'])

    def start(self, action, groups, backup_id=''):
        try:
            self.backups.start(action, self.device.currentData() or '', groups, backup_id)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, t('USB-Backups'), str(exc))
            return
        self.poll()

    def update_buttons(self):
        running = self.backups.job_status()['status'] == 'running'
        has_device = bool(self.device.currentData())
        self.create_button.setEnabled(has_device and not running)
        self.reload_button.setEnabled(not running)
        for widget in self.findChildren(type(self.create_button)):
            if widget.property('backup_action'):
                widget.setEnabled(has_device and not running)

    def poll(self):
        job = self.backups.job_status()
        running = job['status'] == 'running'
        self.progress.setVisible(running or job['status'] in ('complete', 'error'))
        self.progress.setValue(int(100 * job['done'] / job['total']) if job['total'] else 0)
        self.recover_button.setVisible(job['recovery_needed'] and not running)
        if running or self.was_running:
            self.status.setText(job['message'])
        if self.was_running and not running:
            self.load_backups()  # A new backup or restored data changes what is listed.
        self.was_running = running
        self.update_buttons()

    def stop(self):
        self.timer.stop()


class UpdatesTab(QWidget):
    """Check and start updates through the privileged update service, like the web page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from paimenos import updates
        self.updates = updates
        page, layout = scroll_page()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(page)
        info = card(layout, t('PaimenOS-Updates'))
        self.summary = label(''); self.summary.setObjectName('metric'); info.addWidget(self.summary)
        self.details = label('', True); info.addWidget(self.details)
        row = QHBoxLayout()
        self.check_button = button(t('Nach Updates suchen'), lambda: self.request('check'), secondary=True)
        self.install_button = button(t('Update installieren'), self.install)
        row.addWidget(self.check_button); row.addWidget(self.install_button); row.addStretch()
        info.addLayout(row)
        self.job_label = label('', True); info.addWidget(self.job_label)
        self.job_progress = QProgressBar(); self.job_progress.setTextVisible(False); self.job_progress.hide()
        info.addWidget(self.job_progress)
        notes = card(layout, t('Release-Notizen'))
        self.notes = QPlainTextEdit(); self.notes.setReadOnly(True); self.notes.setMinimumHeight(220)
        notes.addWidget(self.notes)
        layout.addStretch()
        self.state = None
        self.pending = False
        self.signals = TaskSignals(self); self.signals.completed.connect(self.completed)
        self.timer = QTimer(self); self.timer.timeout.connect(lambda: self.request('status')); self.timer.start(3000)
        self.request('status')

    def request(self, action, tag=None):
        if self.pending:
            return
        self.pending = True
        self.check_button.setEnabled(False); self.install_button.setEnabled(False)
        submit_task(lambda: self.updates.update_request(action, tag), action, self.signals)

    def completed(self, token, value, error):
        self.pending = False
        if error:
            self.summary.setText(t('Update-Dienst nicht erreichbar') if token == 'status' else t('Anfrage fehlgeschlagen'))
            self.details.setText(error)
            self.check_button.setEnabled(True)
            return
        self.render(value)

    def render(self, state):
        self.state = state
        job = state.get('job')
        busy = bool(job) and job.get('status') in ('queued', 'running')
        release = state.get('release') or {}
        self.summary.setText(t('Update läuft') if busy else t('Prüfung läuft') if state.get('checking') else
                             t('Prüfung fehlgeschlagen') if state.get('check_error') else
                             t('Update verfügbar') if state.get('update_available') else
                             t('Kein neueres Update') if state.get('last_checked') else t('Noch nicht geprüft'))
        checked = state.get('last_checked')
        lines = [t('Installiert: ') + str(state.get('current_version', '?'))]
        if release:
            lines.append(t('Neueste Version: ') + str(release.get('version', '?')))
        lines.append(t('Letzte erfolgreiche Prüfung: ') + (datetime.fromtimestamp(checked).strftime('%d.%m.%Y %H:%M')
                                                         if checked else t('Noch keine erfolgreiche Prüfung')))
        if state.get('check_error'):
            lines.append(str(state['check_error']))
        if release.get('source_override'):
            lines.append(t('Abweichende Release-Quelle: Installation nur im Web-Elternbereich möglich.'))
        self.details.setText('\n'.join(lines))
        self.notes.setPlainText(str(release.get('notes') or ''))
        self.job_progress.setVisible(bool(job))
        self.job_label.setVisible(bool(job))
        if job:
            self.job_label.setText(str(job.get('message', '')))
            self.job_progress.setValue(max(0, min(100, int(job.get('progress') or 0))))
        self.check_button.setEnabled(not busy and not state.get('checking'))
        self.install_button.setEnabled(bool(state.get('update_available')) and not busy
                                      and not release.get('source_override'))

    def install(self):
        release = (self.state or {}).get('release') or {}
        if not release.get('tag'):
            return
        answer = QMessageBox.question(self, t('Update installieren'), t('Version {value0} installieren? Benötigte Debian-Pakete werden bei Bedarf nachinstalliert. Apps und Spiele vorher schließen. Die PaimenOS-Dienste und die Kindersitzung starten neu.', value0=release.get('version', '')))
        if answer == QMessageBox.Yes:
            self.request('install', release['tag'])

    def stop(self):
        self.timer.stop()
