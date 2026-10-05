"""Lokale Bluetooth-Verwaltung nach Anmeldung im Elternbereich."""
import json
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea, QComboBox, QLineEdit, QMessageBox
from laurinos.images import TaskSignals, submit_task
from laurinos.bluetooth import bluetooth_request
from laurinos.parent_ui import STYLE, button, label


def plain_label(text, muted=False):
    widget = label(text, muted)
    widget.setTextFormat(Qt.PlainText)
    return widget


class ParentBluetooth(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Bluetooth-Geräte')
        self.resize(820, 650)
        self.setStyleSheet(STYLE)
        self.state, self.pending, self.closed, self.close_after = None, False, False, False
        self.prompt_id, self.signature = '', None
        self.signals = TaskSignals(self)
        self.signals.completed.connect(self.completed)
        layout = QVBoxLayout(self)
        heading = plain_label('Controller, Kopfhörer & mehr'); heading.setObjectName('heading')
        layout.addWidget(heading)
        layout.addWidget(plain_label('Gerät einschalten und dessen Kopplungstaste gedrückt halten, bis die Anzeige blinkt. Dann suchen und das Gerät koppeln.', True))
        layout.addWidget(plain_label('Nach dem Verbinden: Steuerkreuz oder linker Stick zum Wählen, Bestätigungstaste zum Öffnen. Start öffnet Farbe / Eltern, die rechte Taste geht zurück. Der Elternbereich bleibt PIN-geschützt.', True))
        row = QHBoxLayout()
        self.adapters = QComboBox(); self.adapters.currentIndexChanged.connect(self.adapter_changed)
        self.power_button = button('Bluetooth einschalten', self.power, secondary=True)
        self.scan_button = button('Geräte suchen', self.scan)
        row.addWidget(self.adapters, 1); row.addWidget(self.power_button); row.addWidget(self.scan_button)
        layout.addLayout(row)
        self.status = plain_label('Bluetooth-Verwaltung wird geladen …', True); layout.addWidget(self.status)
        self.prompt_box = QWidget(); self.prompt_box.setObjectName('card')
        prompt_layout = QVBoxLayout(self.prompt_box)
        self.prompt_text, self.code = plain_label(''), plain_label('')
        self.code.setObjectName('metric')
        self.pin = QLineEdit(); self.pin.setPlaceholderText('PIN / Code laut Geräte-Anleitung')
        prompt_layout.addWidget(self.prompt_text); prompt_layout.addWidget(self.code); prompt_layout.addWidget(self.pin)
        prompt_buttons = QHBoxLayout()
        self.accept_button = button('Bestätigen', self.answer)
        self.reject_button = button('Abbrechen', lambda:self.run('cancel'), danger=True)
        prompt_buttons.addWidget(self.accept_button); prompt_buttons.addWidget(self.reject_button)
        prompt_layout.addLayout(prompt_buttons)
        self.pin.returnPressed.connect(self.answer)
        self.prompt_box.hide(); layout.addWidget(self.prompt_box)
        self.cancel_button = button('Laufenden Vorgang abbrechen', lambda:self.run('cancel'), secondary=True)
        self.cancel_button.hide(); layout.addWidget(self.cancel_button)
        self.devices = QScrollArea(); self.devices.setWidgetResizable(True); layout.addWidget(self.devices, 1)
        row = QHBoxLayout()
        row.addWidget(plain_label('Suche endet nach 30 Sekunden. Kopplungen bleiben gespeichert.', True), 1)
        row.addWidget(button('Zurück', self.reject, secondary=True)); layout.addLayout(row)
        self.timer = QTimer(self); self.timer.setInterval(1500); self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.power_button.setEnabled(False); self.scan_button.setEnabled(False)
        self.refresh()

    def refresh(self):
        self.run('status')

    def run(self, action, **values):
        if self.pending or self.closed:
            return
        self.pending = True
        if action != 'status' and self.state:
            self.render(self.state)
        submit_task(lambda:bluetooth_request(action, **values), action, self.signals)

    def completed(self, action, value, error):
        self.pending = False
        if self.closed:
            return
        if self.close_after and action == 'cancel':
            self.close_after = False
            self.done(QDialog.Rejected)
            return
        if error:
            if self.state:
                self.render(self.state)
            self.status.setText(error)
        else:
            self.render(value)

    def selected_adapter(self):
        if not self.state:
            return None
        return next((a for a in self.state['adapters'] if a['path'] == self.adapters.currentData()), None)

    def adapter_changed(self):
        if self.state:
            self.signature = None
            self.render(self.state)

    def confirm(self, title, text):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title); dialog.setTextFormat(Qt.PlainText); dialog.setText(text)
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No); dialog.setDefaultButton(QMessageBox.No)
        return dialog.exec_() == QMessageBox.Yes

    def power(self):
        adapter = self.selected_adapter()
        if not adapter:
            return
        if adapter['powered'] and any(d['connected'] and d['adapter'] == adapter['path'] for d in self.state['devices']):
            if not self.confirm('Bluetooth ausschalten?', 'Verbundene Controller und Kopfhörer werden getrennt. Bluetooth ausschalten?'):
                return
        self.run('power_off' if adapter['powered'] else 'power_on', adapter=adapter['path'])

    def scan(self):
        adapter = self.selected_adapter()
        if adapter:
            self.run('stop_scan' if self.state['scan'] else 'scan', adapter=adapter['path'])

    def answer(self):
        if self.state and self.state['prompt'] and self.state['prompt']['kind'] != 'display':
            self.run('answer', prompt_id=self.state['prompt']['id'], accept='1', value=self.pin.text())

    def remove(self, device):
        if self.confirm('Gerät entfernen?', f'„{device["name"]}“ entfernen? Danach muss das Gerät erneut gekoppelt werden.'):
            self.run('remove', device=device['path'])

    def render(self, state):
        self.state = state
        adapter_paths = [(a['path'], a['name']) for a in state['adapters']]
        existing = [(self.adapters.itemData(i), self.adapters.itemText(i)) for i in range(self.adapters.count())]
        if existing != adapter_paths:
            selected = self.adapters.currentData()
            self.adapters.blockSignals(True); self.adapters.clear()
            for path, name in adapter_paths:
                self.adapters.addItem(name, path)
            index = self.adapters.findData(selected)
            if index >= 0:
                self.adapters.setCurrentIndex(index)
            self.adapters.blockSignals(False)
        adapter = self.selected_adapter()
        busy = self.pending or bool(state['operation'])
        self.adapters.setEnabled(not busy and bool(adapter) and not state['scan'])
        self.power_button.setEnabled(not busy and bool(adapter))
        self.scan_button.setEnabled(not busy and bool(adapter))
        self.power_button.setText('Bluetooth ausschalten' if adapter and adapter['powered'] else 'Bluetooth einschalten')
        self.scan_button.setText('Suche beenden' if state['scan'] else 'Geräte suchen')
        status = state['error'] or state['message']
        if not status:
            status = 'Kein Bluetooth-Adapter gefunden. Bei Bedarf USB-Bluetooth-Adapter anschließen.' if not adapter else 'Bluetooth ist eingeschaltet.' if adapter['powered'] else 'Bluetooth ist ausgeschaltet.'
        self.status.setText(status)
        prompt = state['prompt']
        self.prompt_box.setVisible(bool(prompt))
        self.cancel_button.setVisible(bool(state['operation']) and not prompt)
        self.cancel_button.setEnabled(not self.pending)
        if prompt:
            kind = prompt['kind']; input_code = kind in ('pin', 'passkey')
            instructions = 'Code bzw. PIN laut Geräte-Anleitung eingeben.' if input_code else 'Stimmt dieser Code mit dem anderen Gerät überein?' if kind == 'confirm' else 'Code auf der Bluetooth-Tastatur eingeben und Enter drücken.' if kind == 'display' else 'Kopplung mit diesem Gerät erlauben?'
            self.prompt_text.setText(prompt['name'] + '\n' + instructions)
            self.code.setText(prompt['code']); self.pin.setVisible(input_code)
            self.accept_button.setVisible(kind != 'display')
            self.accept_button.setEnabled(not self.pending); self.reject_button.setEnabled(not self.pending)
            if self.prompt_id != prompt['id']:
                self.prompt_id = prompt['id']; self.pin.clear(); self.pin.setMaxLength(6 if kind == 'passkey' else 16)
                if input_code:
                    self.pin.setFocus()
        else:
            self.prompt_id = ''
        signature = json.dumps([self.adapters.currentData(), state['devices'], busy], sort_keys=True)
        if signature == self.signature:
            return
        self.signature = signature
        position = self.devices.verticalScrollBar().value()
        content = QWidget(); layout = QVBoxLayout(content)
        visible = [d for d in state['devices'] if d['adapter'] == self.adapters.currentData()]
        for paired, heading in ((True, 'Gespeicherte Geräte'), (False, 'Gefundene Geräte')):
            title = plain_label(heading); title.setStyleSheet('font-size:18px;font-weight:bold;'); layout.addWidget(title)
            matching = [d for d in visible if d['paired'] == paired]
            if not matching:
                layout.addWidget(plain_label('Noch keine Geräte gekoppelt.' if paired else '„Geräte suchen“ starten und Kopplungsmodus am Gerät aktivieren.', True))
            for device in matching:
                card = QWidget(); card.setObjectName('card'); inner = QVBoxLayout(card)
                inner.addWidget(plain_label(device['name']))
                inner.addWidget(plain_label(device['address'] + ' · ' + ('Verbunden' if device['connected'] else 'Gekoppelt' if paired else 'Gefunden'), True))
                row = QHBoxLayout()
                action = 'disconnect' if device['connected'] else 'connect' if paired else 'pair'
                control = button('Trennen' if action == 'disconnect' else 'Verbinden' if paired else 'Koppeln && verbinden', lambda checked=False, a=action, d=device:self.run(a, device=d['path']), secondary=action == 'disconnect')
                control.setEnabled(not busy); row.addWidget(control)
                if paired:
                    remove = button('Entfernen', lambda checked=False, d=device:self.remove(d), danger=True)
                    remove.setEnabled(not busy); row.addWidget(remove)
                row.addStretch(); inner.addLayout(row); layout.addWidget(card)
        layout.addStretch()
        old = self.devices.takeWidget()
        if old:
            old.deleteLater()
        self.devices.setWidget(content)
        self.devices.verticalScrollBar().setValue(position)

    def reject(self):
        if self.state and self.state['operation'] and not self.close_after:
            if self.pending:
                self.status.setText('Bitte kurz warten, bis die laufende Anfrage beendet ist.')
                return
            if not self.confirm('Vorgang abbrechen?', 'Die laufende Bluetooth-Kopplung/Verbindung abbrechen und zurückgehen?'):
                return
            self.close_after = True
            self.run('cancel')
            return
        super().reject()

    def done(self, result):
        self.closed = True
        self.timer.stop()
        super().done(result)
