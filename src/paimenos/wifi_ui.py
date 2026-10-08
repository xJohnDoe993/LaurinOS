"""Lokale WLAN-Verwaltung nach Anmeldung im Elternbereich."""
from paimenos.i18n import t
import json
import shutil
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea, QComboBox, QLineEdit, QMessageBox, QCheckBox, QLabel
from paimenos.images import TaskSignals, submit_task
from paimenos.wifi import wifi_request, validate_password
from paimenos.parent_ui import STYLE, button, label


def plain_label(text, muted=False):
    widget = label(text, muted)
    widget.setTextFormat(Qt.PlainText)
    return widget


def confirm(parent, title, text):
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(title); dialog.setTextFormat(Qt.PlainText); dialog.setText(text)
    dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No); dialog.setDefaultButton(QMessageBox.No)
    return dialog.exec_() == QMessageBox.Yes


def signal_icon(strength):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="42" height="36" viewBox="0 0 42 36">']
    for i, height in enumerate((7, 14, 21, 28)):
        color = '#ffb347' if strength >= (i*25+1) else '#344358'
        parts.append(f'<rect x="{i*10+2}" y="{32-height}" width="7" height="{height}" rx="2" fill="{color}"/>')
    parts.append('</svg>')
    pixmap = QPixmap(); pixmap.loadFromData(''.join(parts).encode(), 'SVG')
    widget = QLabel(); widget.setPixmap(pixmap); widget.setFixedSize(44, 38)
    return widget


class WifiCredentials(QDialog):
    def __init__(self, parent, network=None):
        super().__init__(parent)
        self.network = network
        self.setWindowTitle(t('WLAN verbinden')); self.setStyleSheet(STYLE); self.resize(470, 330)
        layout = QVBoxLayout(self)
        heading = plain_label(network['name'] if network else t('Verstecktes Netzwerk')); heading.setObjectName('heading')
        layout.addWidget(heading)
        self.ssid = QLineEdit(); self.ssid.setPlaceholderText(t('Netzwerkname (SSID)')); self.ssid.setMaxLength(32)
        self.security = QComboBox()
        for name, key in (('WPA / WPA2', 'wpa-psk'), ('WPA3', 'sae'), (t('Offen · ohne Passwort'), 'open')):
            self.security.addItem(name, key)
        if not network:
            layout.addWidget(plain_label(t('Netzwerkname'))); layout.addWidget(self.ssid)
            layout.addWidget(plain_label(t('Sicherheit'))); layout.addWidget(self.security)
        self.password_label = plain_label(t('WLAN-Passwort'))
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.Password); self.password.setMaxLength(64)
        self.password.setPlaceholderText(t('Passwort des Routers'))
        self.show_password = QCheckBox(t('Passwort anzeigen'))
        self.show_password.toggled.connect(lambda shown:self.password.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password))
        layout.addWidget(self.password_label); layout.addWidget(self.password); layout.addWidget(self.show_password)
        self.notice = plain_label(t('Das Netzwerk wird nach erfolgreicher Verbindung gespeichert.'), True); layout.addWidget(self.notice)
        row = QHBoxLayout(); row.addWidget(button(t('Abbrechen'), self.reject, secondary=True)); row.addWidget(button(t('Verbinden'), self.validate)); layout.addLayout(row)
        self.security.currentIndexChanged.connect(self.update_fields)
        self.password.returnPressed.connect(self.validate); self.ssid.returnPressed.connect(self.validate)
        self.update_fields()

    def update_fields(self):
        key = self.network['key'] if self.network else self.security.currentData()
        for widget in (self.password_label, self.password, self.show_password):
            widget.setVisible(key in ('wpa-psk', 'sae'))

    def validate(self):
        key = self.network['key'] if self.network else self.security.currentData()
        try:
            if not self.network and not 1 <= len(self.ssid.text().encode('utf-8')) <= 32:
                raise ValueError(t('Netzwerkname muss 1 bis 32 Bytes lang sein.'))
            validate_password(self.password.text(), key)
        except ValueError as exc:
            self.notice.setText(str(exc)); return
        self.accept()


class ParentWifi(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t('PaimenOS · WLAN')); self.setStyleSheet(STYLE)
        self.resize(820, 650)
        if self.screen():
            area = self.screen().availableGeometry(); self.resize(min(820, area.width()-32), min(650, area.height()-32))
        self.state, self.pending, self.closed, self.signature = None, False, False, None
        self.pending_action, self.queued = '', None
        self.advanced_command = None
        self.signals = TaskSignals(self); self.signals.completed.connect(self.completed)
        layout = QVBoxLayout(self); layout.setContentsMargins(22, 20, 22, 16); layout.setSpacing(12)
        heading = plain_label(t('WLAN & Internet')); heading.setObjectName('heading'); layout.addWidget(heading)
        layout.addWidget(plain_label(t('Netzwerk auswählen und verbinden. Gespeicherte Netzwerke verbinden sich auf Wunsch automatisch.'), True))
        row = QHBoxLayout()
        self.adapters = QComboBox(); self.adapters.currentIndexChanged.connect(self.adapter_changed)
        self.power_button = button(t('WLAN einschalten'), self.power, secondary=True)
        self.scan_button = button(t('Netzwerke suchen'), self.scan)
        row.addWidget(self.adapters, 1); row.addWidget(self.power_button); row.addWidget(self.scan_button); layout.addLayout(row)
        self.status = plain_label(t('WLAN-Verwaltung wird geladen …'), True); layout.addWidget(self.status)
        self.cancel_button = button(t('Verbindungsaufbau abbrechen'), lambda:self.run('cancel'), secondary=True)
        self.cancel_button.hide(); layout.addWidget(self.cancel_button)
        self.networks = QScrollArea(); self.networks.setWidgetResizable(True); layout.addWidget(self.networks, 1)
        row = QHBoxLayout()
        self.hidden_button = button(t('Verstecktes Netzwerk'), self.hidden, secondary=True)
        row.addWidget(self.hidden_button); row.addWidget(button(t('Erweiterte Einstellungen'), self.advanced, secondary=True)); row.addStretch()
        row.addWidget(button(t('Zurück'), self.reject, secondary=True)); layout.addLayout(row)
        self.timer = QTimer(self); self.timer.setInterval(2000); self.timer.timeout.connect(self.refresh); self.timer.start()
        for widget in (self.power_button, self.scan_button, self.hidden_button):
            widget.setEnabled(False)
        self.refresh()

    def refresh(self):
        self.run('status')

    def run(self, action, **values):
        if self.closed:
            return
        if self.pending:
            # Eine kurze Statusabfrage darf einen Klick nicht verschlucken.
            if action != 'status' and self.pending_action == 'status' and self.queued is None:
                self.queued = (action, values)
                if self.state:
                    self.render(self.state)
            return
        self.pending = True
        self.pending_action = action
        if action != 'status' and self.state:
            self.render(self.state)
        submit_task(lambda:wifi_request(action, **values), action, self.signals)

    def completed(self, action, value, error):
        self.pending = False
        self.pending_action = ''
        if self.closed:
            return
        if error:
            if self.state:
                self.render(self.state)
            self.status.setText(error)
        else:
            self.render(value)
        if self.queued:
            action, values = self.queued
            self.queued = None
            self.run(action, **values)

    def selected_adapter(self):
        return next((a for a in self.state['adapters'] if a['path'] == self.adapters.currentData()), None) if self.state else None

    def adapter_changed(self):
        if self.state:
            self.signature = None; self.render(self.state)

    def power(self):
        if not self.state:
            return
        if self.state['powered'] and not confirm(self, t('WLAN ausschalten?'), t('WLAN ausschalten? Die Internetverbindung und der Zugriff auf den Web-Elternbereich über WLAN werden unterbrochen.')):
            return
        self.run('power_off' if self.state['powered'] else 'power_on')

    def scan(self):
        if self.selected_adapter():
            self.run('scan', adapter=self.adapters.currentData())

    def connect_network(self, network):
        if network['profile']:
            self.run('connect', adapter=network['adapter'], profile=network['profile']); return
        if not network['supported']:
            self.status.setText(t('Dieses Netzwerk bitte über „Erweiterte Einstellungen“ am Laptop einrichten.')); return
        if network['key'] in ('open', 'owe'):
            self.run('connect', adapter=network['adapter'], network=network['path']); return
        dialog = WifiCredentials(self, network)
        if dialog.exec_() == QDialog.Accepted:
            password = dialog.password.text(); dialog.password.clear()
            self.run('connect', adapter=network['adapter'], network=network['path'], password=password)
        dialog.deleteLater()

    def hidden(self):
        device = self.adapters.currentData()
        dialog = WifiCredentials(self)
        if dialog.exec_() == QDialog.Accepted:
            values = dict(adapter=device, ssid=dialog.ssid.text(), security=dialog.security.currentData(), password=dialog.password.text())
            dialog.password.clear(); self.run('hidden', **values)
        dialog.deleteLater()

    def disconnect(self, adapter):
        if confirm(self, t('WLAN-Verbindung trennen?'), t('Die Verbindung trennen? Internet und Web-Elternbereich über dieses WLAN sind danach nicht erreichbar.')):
            self.run('disconnect', adapter=adapter)

    def forget(self, profile):
        if confirm(self, t('Netzwerk vergessen?'), '„' + profile['name'] + t('“ vergessen? Beim nächsten Verbinden ist das WLAN-Passwort erneut nötig.')):
            self.run('forget', profile=profile['path'])

    def advanced(self):
        if self.pending_action not in ('', 'status') or self.queued or (self.state and self.state['operation']):
            QMessageBox.information(self, t('WLAN'), t('Bitte den laufenden WLAN-Vorgang zuerst abschließen oder abbrechen.'))
            return
        parent = self.parent()
        menu = parent.parent() if parent else None
        if not menu or not hasattr(menu, 'launch'):
            QMessageBox.warning(self, t('WLAN'), t('Der Netzwerkeditor muss aus dem Elternmenü geöffnet werden.'))
            return
        editor = shutil.which('nm-connection-editor')
        if not editor:
            QMessageBox.warning(self, t('WLAN'), t('Der Netzwerkeditor fehlt. Bitte das WLAN-Update installieren.'))
            return
        self.advanced_command = [editor]
        self.accept()

    def render(self, state):
        self.state = state
        paths = [(a['path'], a['name']) for a in state['adapters']]
        if [(self.adapters.itemData(i), self.adapters.itemText(i)) for i in range(self.adapters.count())] != paths:
            selected = self.adapters.currentData(); self.adapters.blockSignals(True); self.adapters.clear()
            for path, name in paths:
                self.adapters.addItem(name, path)
            index = self.adapters.findData(selected)
            if index >= 0:
                self.adapters.setCurrentIndex(index)
            self.adapters.blockSignals(False)
        adapter = self.selected_adapter()
        busy = self.pending or bool(state['operation'])
        ready = bool(adapter) and adapter['ready'] and state['powered'] and state['hardware']
        self.adapters.setEnabled(not busy and not state['scan'])
        self.power_button.setEnabled(not busy and state['available'] and bool(state['adapters']))
        self.power_button.setText(t('WLAN ausschalten') if state['powered'] else t('WLAN einschalten'))
        self.scan_button.setEnabled(not busy and ready and not state['scan'])
        self.scan_button.setText(t('Suche läuft …') if state['scan'] else t('Netzwerke suchen'))
        self.hidden_button.setEnabled(not busy and ready)
        self.cancel_button.setVisible(bool(state['operation'])); self.cancel_button.setEnabled(not self.pending)
        if not state['available']:
            status = t('Netzwerkdienst nicht verfügbar.')
        elif not adapter:
            status = t('Kein WLAN-Adapter gefunden.')
        elif not state['hardware']:
            status = t('WLAN durch Flugmodus / Hardware-Schalter blockiert.')
        elif not state['powered']:
            status = t('WLAN ist ausgeschaltet.')
        elif not adapter['managed']:
            status = t('Dieser Adapter wird nicht vom Netzwerkdienst verwaltet.')
        elif adapter['problem']:
            status = adapter['problem']
        elif adapter['connected']:
            status = t('Verbunden mit „') + adapter['network'] + '“'
            if adapter['addresses']:
                status += ' · ' + ', '.join(adapter['addresses'])
            if state['connectivity'] == 2:
                status += t(' · Anmeldung im Browser erforderlich.')
            elif state['connectivity'] == 3:
                status += t(' · Internet momentan eingeschränkt.')
        else:
            status = t('WLAN eingeschaltet · Netzwerk auswählen oder suchen.')
        self.status.setText(state['error'] or (state['message'] + '\n' + status if state['message'] else status))
        signature = json.dumps([self.adapters.currentData(), state['networks'], state['saved'], busy, ready], sort_keys=True)
        if signature == self.signature:
            return
        self.signature = signature
        position = self.networks.verticalScrollBar().value()
        content = QWidget(); layout = QVBoxLayout(content)
        device = self.adapters.currentData()
        for saved, heading in ((True, t('Gespeicherte Netzwerke')), (False, t('Netzwerke in der Nähe'))):
            title = plain_label(heading); title.setStyleSheet('font-size:18px;font-weight:bold;'); layout.addWidget(title)
            entries = state['saved'] if saved else [n for n in state['networks'] if n['adapter'] == device and not n['profile']]
            if not entries:
                layout.addWidget(plain_label(t('Noch keine Netzwerke gespeichert.') if saved else t('Keine weiteren Netzwerke gefunden. „Netzwerke suchen“ aktualisiert die Liste.'), True))
            for item in entries:
                card = QWidget(); card.setObjectName('card'); inner = QVBoxLayout(card)
                row = QHBoxLayout()
                matching = next((n for n in state['networks'] if n['adapter'] == device and n['profile'] == item['path']), None) if saved else item
                row.addWidget(signal_icon(matching['strength'] if matching else 0)); row.addWidget(plain_label(item['name']), 1)
                inner.addLayout(row)
                connected = device in item['adapters'] if saved else item['connected']
                details = t('Verbunden') if connected else t('Gespeichert') if saved else t('Gefunden')
                if matching:
                    details += t(' · {value0}% Signal · {value1}', value0=matching['strength'], value1=matching['security'])
                elif saved:
                    details += t(' · Momentan nicht in Reichweite') if device not in item['available'] else ''
                inner.addWidget(plain_label(details, True)); row = QHBoxLayout()
                control = button(t('Trennen') if connected else t('Verbinden'), lambda checked=False, i=item, s=saved, c=connected, d=device: self.disconnect(d) if c else self.run('connect', adapter=d, profile=i['path']) if s else self.connect_network(i), secondary=connected)
                control.setEnabled(not busy and ready and (not saved or device in item['available'])); row.addWidget(control)
                if saved:
                    remove = button(t('Vergessen'), lambda checked=False, p=item:self.forget(p), danger=True)
                    remove.setEnabled(not busy and not item['connected']); row.addWidget(remove)
                    auto = QCheckBox(t('Automatisch verbinden')); auto.setChecked(item['autoconnect']); auto.setEnabled(not busy)
                    auto.toggled.connect(lambda enabled, p=item:self.run('autoconnect', profile=p['path'], enabled='1' if enabled else '0'))
                    inner.addWidget(auto)
                elif not item['supported']:
                    control.setText(t('Erweitert einrichten')); control.clicked.disconnect(); control.clicked.connect(self.advanced)
                row.addStretch(); inner.addLayout(row); layout.addWidget(card)
        layout.addStretch(); old = self.networks.takeWidget()
        if old:
            old.deleteLater()
        self.networks.setWidget(content); self.networks.verticalScrollBar().setValue(position)

    def done(self, result):
        self.closed = True; self.queued = None; self.timer.stop(); super().done(result)
