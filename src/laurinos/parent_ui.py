"""Lokaler Elternbereich mit denselben Verwaltungsfunktionen wie im Web."""
import os
import shlex
import shutil
import subprocess
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QTabWidget, QScrollArea, QCheckBox,
    QComboBox, QMessageBox, QColorDialog, QPlainTextEdit, QFileDialog, QProgressBar)
import laurinos.parent as parents
import laurinos.emulators as emulators
from laurinos.state import read_settings
from laurinos.images import TaskSignals, submit_task
from laurinos.diagnostics import collect_diagnostics, diagnostics_text

STYLE = '''
QDialog,QWidget {background:#101827;color:#f5f7fb;font-size:14px;}
QLabel {background:transparent;} QLabel#heading {font-size:25px;font-weight:bold;}
QLabel#muted {color:#b4c0d1;} QLabel#metric {font-size:23px;font-weight:bold;color:#ffb347;}
QWidget#card {background:#182335;border:1px solid #344358;border-radius:12px;}
QPushButton {background:#ffb347;color:#18202c;border:1px solid transparent;border-radius:8px;padding:10px 14px;font-weight:bold;min-height:22px;}
QPushButton:hover {background:#ffc477;} QPushButton:focus {border:2px solid #fff;}
QPushButton[secondary="true"] {background:#26374e;color:#f5f7fb;border-color:#46556a;}
QPushButton[danger="true"] {background:#462c36;color:#ffb1ac;border-color:#84505b;}
QPushButton:disabled {background:#253044;color:#8694a6;}
QLineEdit,QSpinBox,QComboBox,QPlainTextEdit {background:#182335;color:white;border:1px solid #52647d;border-radius:7px;padding:8px;selection-background-color:#46668d;}
QLineEdit:focus,QSpinBox:focus,QComboBox:focus {border:2px solid #ffb347;}
QCheckBox {spacing:10px;background:transparent;} QCheckBox::indicator {width:22px;height:22px;border:1px solid #7a8da8;border-radius:5px;background:#101827;}
QCheckBox::indicator:checked {background:#ffb347;border:2px solid #ffd79b;}
QTabWidget::pane {border:0;} QTabBar::tab {background:#182335;color:#b4c0d1;padding:12px 16px;margin:0 4px 12px 0;border-radius:8px;}
QTabBar::tab:selected {background:#2a3a50;color:white;} QScrollArea {border:0;}
QScrollBar:vertical {background:#101827;width:10px;margin:0;} QScrollBar::handle:vertical {background:#52647d;min-height:24px;border-radius:5px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;} QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:none;}
QProgressBar {border:0;background:#304057;border-radius:5px;height:10px;}
QProgressBar::chunk {background:#ffb347;border-radius:5px;}
'''


def label(text, muted=False):
    widget = QLabel(text)
    widget.setWordWrap(True)
    if muted:
        widget.setObjectName('muted')
    return widget


def button(text, callback, secondary=False, danger=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.PointingHandCursor)
    widget.setProperty('secondary', secondary)
    widget.setProperty('danger', danger)
    widget.clicked.connect(callback)
    return widget


def scroll_page():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(16)
    scroll.setWidget(content)
    return scroll, layout


def card(layout, title):
    widget = QWidget()
    widget.setObjectName('card')
    inner = QVBoxLayout(widget)
    inner.setContentsMargins(18, 16, 18, 16)
    heading = label(title)
    heading.setStyleSheet('font-size:18px;font-weight:bold;')
    inner.addWidget(heading)
    layout.addWidget(widget)
    return inner


class AppEditor(QDialog):
    def __init__(self, item=None, parent=None):
        super().__init__(parent)
        self.item = item or {}
        self.busy = False
        self.icon_path = ''
        self.setWindowTitle('App bearbeiten' if item else 'App hinzufügen')
        self.resize(690, 590)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        heading = label(self.windowTitle()); heading.setObjectName('heading')
        layout.addWidget(heading)
        form = QFormLayout()
        target, arguments = parents.app_launch_fields(self.item)
        self.title_input = QLineEdit(self.item.get('title', ''))
        self.title_input.setMaxLength(80)
        self.target_input = QLineEdit(target)
        self.target_input.setPlaceholderText('https://… oder /usr/bin/vlc')
        self.arguments_input = QLineEdit(arguments)
        self.arguments_input.setPlaceholderText('Zum Beispiel: --fullscreen "/home/kids/Mein Video.mp4"')
        self.category_input = QComboBox()
        for text, value in [('Automatisch', 'auto'), ('Webapps', 'webapps'), ('Spiele', 'games'), ('Produktiv', 'productive')]:
            self.category_input.addItem(text, value)
        self.category_input.setCurrentIndex(max(0, self.category_input.findData(self.item.get('category', 'auto'))))
        form.addRow('Kategorie', self.category_input)
        form.addRow('Name', self.title_input)
        form.addRow('Webadresse / Programm', self.target_input)
        form.addRow('Programmparameter', self.arguments_input)
        self.icon_input = QLineEdit(self.item.get('icon_url', ''))
        self.icon_input.setPlaceholderText('Optional: https://…/logo.png')
        form.addRow('Bildadresse', self.icon_input)
        layout.addLayout(form)
        file_row = QHBoxLayout()
        self.file_label = label('Keine neue Bilddatei gewählt', True)
        self.choose_button = button('Bilddatei wählen …', self.choose_icon, secondary=True)
        self.clear_button = button('Auswahl entfernen', self.clear_icon, secondary=True)
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(self.choose_button); file_row.addWidget(self.clear_button)
        layout.addLayout(file_row)
        self.reset_input = QCheckBox('Eigenes Bild entfernen / Standardsymbol verwenden')
        self.reset_input.toggled.connect(self.reset_changed)
        layout.addWidget(self.reset_input)
        layout.addWidget(label('HTTP/HTTPS öffnet eine Webapp. Ein Programmpfad oder Programmname startet eine bereits installierte Anwendung als kids. Parameter mit Leerzeichen in Anführungszeichen setzen. Ohne neue Bildauswahl bleibt das vorhandene Bild erhalten. PNG, JPEG, GIF oder WebP bis 4 MB.', True))
        if self.item.get('type') == 'camera' or self.item.get('emulator'):
            self.target_input.setEnabled(False)
            self.arguments_input.setEnabled(False)
            layout.addWidget(label('Bei Kamera und Emulator-Spielen lassen sich Name und Bild ändern; der Start bleibt festgelegt.', True))
        self.message = label(''); layout.addWidget(self.message)
        row = QHBoxLayout()
        self.save_button = button('App speichern', self.save)
        self.cancel_button = button('Abbrechen', self.reject, secondary=True)
        row.addWidget(self.save_button); row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self.signals = TaskSignals(self)
        self.signals.completed.connect(self.completed)

    def choose_icon(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Kachelbild auswählen', os.path.expanduser('~'),
                                             'Bilder (*.png *.jpg *.jpeg *.gif *.webp)')
        if path:
            try:
                if os.path.getsize(path) > parents.MAX_ICON_BYTES:
                    raise ValueError('Das Bild ist größer als 4 MB.')
            except (OSError, ValueError) as exc:
                self.message.setText(str(exc)); return
            self.icon_path = path
            self.icon_input.clear()
            self.file_label.setText(os.path.basename(path))

    def clear_icon(self):
        self.icon_path = ''
        self.file_label.setText('Keine neue Bilddatei gewählt')

    def reset_changed(self, reset):
        if reset:
            self.clear_icon()
            self.icon_input.clear()
        for widget in (self.icon_input, self.choose_button, self.clear_button):
            widget.setEnabled(not reset)

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.save_button, self.cancel_button, self.title_input, self.target_input,
                       self.arguments_input, self.icon_input, self.choose_button, self.clear_button, self.reset_input, self.category_input):
            widget.setEnabled(not busy)
        if not busy:
            self.reset_changed(self.reset_input.isChecked())
            if self.item.get('type') == 'camera' or self.item.get('emulator'):
                self.target_input.setEnabled(False)
                self.arguments_input.setEnabled(False)

    def save(self):
        values = dict(title=self.title_input.text(), target=self.target_input.text(),
                      arguments=self.arguments_input.text(), icon_url=self.icon_input.text(),
                      app_id=self.item.get('id'), reset_icon=self.reset_input.isChecked(), category=self.category_input.currentData())
        path = self.icon_path
        def operation():
            if path:
                with open(path, 'rb') as handle:
                    values['icon_data'] = handle.read(parents.MAX_ICON_BYTES + 1)
            return parents.save_app(**values)
        self.set_busy(True)
        self.message.setText('App wird gespeichert …')
        submit_task(operation, 'app', self.signals)

    def completed(self, token, value, error):
        self.set_busy(False)
        if not error:
            self.accept()
            return
        self.message.setText(error)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)


class ParentDiagnostics(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Geräte-Diagnose')
        self.resize(760, 540)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        row = QHBoxLayout()
        self.refresh_button = button('Aktualisieren', self.refresh, secondary=True)
        self.export_button = button('Bericht speichern', self.export)
        row.addWidget(self.refresh_button); row.addWidget(self.export_button)
        row.addWidget(button('Zurück', self.reject, secondary=True))
        layout.addLayout(row)
        self.signals = TaskSignals(self)
        self.signals.completed.connect(self.completed)
        self.refresh()

    def refresh(self):
        self.refresh_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.text.setPlainText('Diagnose wird gesammelt …')
        submit_task(collect_diagnostics, 'diagnostics', self.signals)

    def completed(self, token, value, error):
        self.refresh_button.setEnabled(True)
        self.export_button.setEnabled(not bool(error))
        self.text.setPlainText(error if error else diagnostics_text(value))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Bericht speichern', os.path.expanduser('~/LaurinOS-Diagnose.txt'), 'Textdateien (*.txt)')
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as handle:
                    handle.write(self.text.toPlainText())
            except OSError as exc:
                QMessageBox.warning(self, 'Speichern', str(exc))


class ParentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('LaurinOS · Elternbereich')
        self.setStyleSheet(STYLE)
        self.resize(860, 650)
        if self.screen():
            available = self.screen().availableGeometry()
            self.resize(min(860, available.width()-32), min(650, available.height()-32))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(12)
        heading = label('LaurinOS Eltern'); heading.setObjectName('heading')
        layout.addWidget(heading)
        layout.addWidget(label('Apps freigeben, Zeit verwalten und das Gerät einrichten.', True))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.status = label('Änderungen werden direkt auf diesem Gerät gespeichert.', True)
        row = QHBoxLayout(); row.addWidget(self.status, 1)
        row.addWidget(button('Schließen', self.accept, secondary=True))
        layout.addLayout(row)
        self.st = read_settings()
        self.limit_dirty = False
        self.color_dirty = False
        self.app_signature = None
        self.app_rows = {}
        self.build_overview()
        self.build_apps()
        self.build_time()
        self.build_settings()
        self.refresh()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(3000)

    def perform(self, operation, message):
        try:
            operation()
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            QMessageBox.warning(self, 'Änderung nicht gespeichert', str(exc))
            self.refresh()
            return False
        self.status.setText(message)
        self.refresh()
        return True

    def bonus_buttons(self, layout):
        row = QHBoxLayout()
        for minutes in (5, 15, 30):
            row.addWidget(button(f'+{minutes} Min.', lambda checked=False, m=minutes: self.give_bonus(m), secondary=True))
        layout.addLayout(row)

    def give_bonus(self, minutes):
        try:
            added = parents.add_bonus(minutes)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Bonuszeit', str(exc)); return
        self.status.setText(f'{added} Minuten Bonus hinzugefügt.' if added else 'Die maximale Bonuszeit ist erreicht.')
        self.refresh()

    def build_overview(self):
        page, layout = scroll_page()
        self.tabs.addTab(page, 'Übersicht')
        time_card = card(layout, 'Bildschirmzeit heute')
        self.summary = label(''); self.summary.setObjectName('metric')
        self.summary_detail = label('', True)
        time_card.addWidget(self.summary); time_card.addWidget(self.summary_detail)
        self.progress = QProgressBar(); self.progress.setTextVisible(False)
        time_card.addWidget(self.progress)
        self.bonus_buttons(time_card)
        time_card.addWidget(label('Bonuszeit wirkt nur bei einem gesetzten Tageslimit.', True))
        apps_card = card(layout, 'Apps für den Kinderbereich')
        self.apps_summary = label(''); apps_card.addWidget(self.apps_summary)
        apps_card.addWidget(button('Apps verwalten', lambda: self.tabs.setCurrentIndex(1), secondary=True))
        tools = card(layout, 'Gerät & Hilfe')
        row = QHBoxLayout()
        row.addWidget(button('WLAN / Netzwerke', self.open_wifi, secondary=True))
        row.addWidget(button('Geräte-Diagnose', self.open_diagnostics, secondary=True))
        tools.addLayout(row)
        self.web_address = label('Web-Elternbereich: Adresse wird ermittelt …', True)
        self.web_address.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tools.addWidget(self.web_address)
        self.address_signals = TaskSignals(self)
        self.address_signals.completed.connect(self.address_completed)
        submit_task(self.find_addresses, 'address', self.address_signals)
        layout.addStretch()

    @staticmethod
    def find_addresses():
        try:
            import ipaddress
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=3)
            addresses = []
            for raw in result.stdout.split():
                try:
                    address = ipaddress.ip_address(raw)
                except ValueError:
                    continue
                if address.version == 4 and not address.is_loopback and not address.is_link_local:
                    addresses.append('http://' + str(address))
            return addresses
        except (OSError, subprocess.TimeoutExpired):
            return []

    def address_completed(self, token, value, error):
        self.web_address.setText('Web-Elternbereich im selben Netzwerk: ' + ' · '.join(value) if value and not error else 'Web-Elternbereich: http://localhost (auf diesem Gerät)')

    def build_apps(self):
        page = QWidget(); layout = QVBoxLayout(page)
        self.tabs.addTab(page, 'Apps')
        row = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText('Name oder Startbefehl suchen …')
        self.search.setAccessibleName('Apps durchsuchen'); self.search.textChanged.connect(self.filter_apps)
        self.type_filter = QComboBox()
        for title, value in [('Alle Typen','all'),('Programme & Spiele','native'),('Webapps','webapp'),('Kamera, Bilder & Videos','camera')]:
            self.type_filter.addItem(title, value)
        self.type_filter.currentIndexChanged.connect(self.filter_apps)
        row.addWidget(self.search, 1); row.addWidget(self.type_filter)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(button('+ App', self.new_app))
        row.addWidget(button('Alle freigeben', lambda: self.bulk(True), secondary=True))
        row.addWidget(button('Alle sperren', lambda: self.bulk(False), danger=True))
        layout.addLayout(row)
        self.app_count = label('', True); layout.addWidget(self.app_count)
        self.apps_scroll = QScrollArea(); self.apps_scroll.setWidgetResizable(True)
        layout.addWidget(self.apps_scroll, 1)
        layout.addWidget(label('Freigegebene Webapps erscheinen bei Internetverbindung; die Kamera bei angeschlossenem Medium.', True))

    def render_apps(self, items, st):
        scroll_position = self.apps_scroll.verticalScrollBar().value()
        content = QWidget(); layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(10)
        self.app_rows = {}
        for item in items:
            widget = QWidget(); widget.setObjectName('card')
            inner = QVBoxLayout(widget)
            row = QHBoxLayout()
            checkbox = QCheckBox(item.get('title', item['id']))
            checkbox.setChecked(parents.app_active(item, st))
            checkbox.setToolTip('Freigabe im Kinderbereich')
            checkbox.toggled.connect(lambda active, i=item['id']: self.set_active(i, active))
            row.addWidget(checkbox, 1)
            if parents.editable_app(item):
                row.addWidget(button('Bearbeiten', lambda checked=False, i=dict(item): self.edit_app(i), secondary=True))
            if parents.deletable_app(item):
                row.addWidget(button('Löschen', lambda checked=False, i=dict(item): self.delete_app(i), danger=True))
            inner.addLayout(row)
            inner.addWidget(label(item.get('url', '') if item.get('type') == 'webapp' else 'Kamera, Bilder & Videos' if item.get('type') == 'camera' else item.get('command', 'Programm / Spiel'), True))
            if parents.app_source_label(item):
                inner.addWidget(label(parents.app_source_label(item), True))
            layout.addWidget(widget)
            self.app_rows[item['id']] = (widget, item)
        layout.addStretch()
        old = self.apps_scroll.takeWidget()
        if old:
            old.deleteLater()
        self.apps_scroll.setWidget(content)
        self.filter_apps()
        QTimer.singleShot(0, lambda: self.apps_scroll.verticalScrollBar().setValue(scroll_position))

    def filter_apps(self, *args):
        query, kind, count = self.search.text().casefold(), self.type_filter.currentData(), 0
        for widget, item in self.app_rows.values():
            visible = query in (item.get('title','') + ' ' + item.get('url','') + ' ' + item.get('command','')).casefold() and (kind=='all' or item.get('type','native')==kind)
            widget.setVisible(visible)
            count += visible
        self.app_count.setText(f'{count} Apps' if count else 'Keine passenden Apps gefunden.')

    def set_active(self, app_id, active):
        self.perform(lambda: parents.set_apps_active([app_id], active), 'App-Freigabe gespeichert.')

    def bulk(self, active):
        if not active and QMessageBox.question(self, 'Alle Apps sperren?', 'Alle Apps für den Kinderbereich sperren?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.perform(lambda: parents.set_apps_active([a['id'] for a in parents.managed_apps()], active), 'App-Freigaben gespeichert.')

    def new_app(self):
        self.edit_app(None)

    def edit_app(self, item):
        editor = AppEditor(item, self)
        if editor.exec_() == QDialog.Accepted:
            self.status.setText('App gespeichert.')
            self.refresh()
        editor.deleteLater()

    def delete_app(self, item):
        if QMessageBox.question(self, 'App löschen?', f'„{item["title"]}“ aus dem Kinder-Menü entfernen? Bei Emulator-Spielen werden auch die hochgeladenen ROM-Dateien entfernt; Spielstände bleiben erhalten. Installierte Programme und Browserprofile bleiben erhalten.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.perform(lambda: parents.delete_app(item['id']), 'App aus dem Menü entfernt.')

    def build_time(self):
        page, layout = scroll_page(); self.tabs.addTab(page, 'Bildschirmzeit')
        settings = card(layout, 'Tageslimit')
        settings.addWidget(label('Das Limit gilt jeden Tag. Verbrauch und Bonus werden um Mitternacht zurückgesetzt.', True))
        self.limit_spin = QSpinBox(); self.limit_spin.setRange(0, 600)
        self.limit_spin.setSuffix(' Min.'); self.limit_spin.setSpecialValueText('Unbegrenzt')
        self.limit_spin.setValue(min(600, self.st['daily_limit_minutes']))
        self.limit_spin.valueChanged.connect(lambda: setattr(self, 'limit_dirty', True))
        form = QFormLayout(); form.addRow('Minuten pro Tag', self.limit_spin); settings.addLayout(form)
        presets = QHBoxLayout()
        for minutes in (30, 60, 90, 120):
            presets.addWidget(button(str(minutes) + ' Min.', lambda checked=False, m=minutes: self.limit_spin.setValue(m), secondary=True))
        settings.addLayout(presets)
        settings.addWidget(button('Tageslimit speichern', self.save_time))
        bonus_card = card(layout, 'Bonuszeit heute')
        self.bonus_label = label(''); bonus_card.addWidget(self.bonus_label)
        self.bonus_buttons(bonus_card)
        row = QHBoxLayout()
        self.bonus_spin = QSpinBox(); self.bonus_spin.setRange(1, 600); self.bonus_spin.setValue(10); self.bonus_spin.setSuffix(' Min.')
        row.addWidget(self.bonus_spin)
        row.addWidget(button('Bonus hinzufügen', lambda: self.give_bonus(self.bonus_spin.value()), secondary=True))
        row.addWidget(button('Bonus entfernen', self.remove_bonus, danger=True))
        bonus_card.addLayout(row)
        reset = card(layout, 'Heutigen Verbrauch zurücksetzen')
        reset.addWidget(label('Setzt Verbrauch und Bonus auf 0. Das Tageslimit bleibt erhalten.', True))
        reset.addWidget(button('Heute zurücksetzen', self.reset_usage, danger=True))
        layout.addStretch()

    def save_time(self):
        if self.perform(lambda: parents.set_time(self.limit_spin.value()), 'Tageslimit gespeichert.'):
            self.limit_dirty = False

    def remove_bonus(self):
        if QMessageBox.question(self, 'Bonus entfernen?', 'Die Bonuszeit entfernen? Das Gerät kann dadurch gesperrt werden.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.perform(parents.clear_bonus, 'Bonuszeit entfernt.')

    def reset_usage(self):
        if QMessageBox.question(self, 'Heute zurücksetzen?', 'Heutigen Verbrauch und Bonus wirklich zurücksetzen?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.perform(parents.reset_today, 'Heutiger Verbrauch und Bonus zurückgesetzt.')

    def build_settings(self):
        page, layout = scroll_page(); self.tabs.addTab(page, 'Einstellungen')
        pin_card = card(layout, 'Eltern-PIN ändern')
        pin_card.addWidget(label('Die PIN gilt am Gerät und im Web. Beide Felder leer lassen, um sie beizubehalten.', True))
        self.pin_input, self.pin_confirm = QLineEdit(), QLineEdit()
        for field in (self.pin_input, self.pin_confirm):
            field.setEchoMode(QLineEdit.Password); field.setMaxLength(12)
            field.setPlaceholderText('4 bis 12 Ziffern')
        form = QFormLayout(); form.addRow('Neue PIN', self.pin_input); form.addRow('PIN wiederholen', self.pin_confirm)
        pin_card.addLayout(form)
        color_card = card(layout, 'Farbe im Kinder-Menü')
        self.color = self.st['bg_color']
        self.color_button = button('Farbe auswählen', self.choose_color, secondary=True)
        color_card.addWidget(self.color_button)
        self.update_color_button()
        self.category_tabs_input = QCheckBox('Kategorien im Kinder-Menü anzeigen (Symbole)')
        self.category_tabs_input.setChecked(bool(self.st.get('category_tabs', False)))
        color_card.addWidget(self.category_tabs_input)
        color_card.addWidget(label('Alles, Webapps, Spiele und Produktiv. Leere Kategorien verschwinden; Schultertasten wechseln die Ansicht.', True))
        layout.addWidget(button('Einstellungen speichern', self.save_settings))
        wifi_card = card(layout, 'WLAN & Internet')
        wifi_card.addWidget(label('Netzwerke suchen, verbinden und gespeicherte WLANs verwalten.', True))
        wifi_card.addWidget(button('WLAN verwalten', self.open_wifi, secondary=True))
        bluetooth_card = card(layout, 'Bluetooth-Geräte')
        bluetooth_card.addWidget(label('Controller, Kopfhörer und Tastaturen suchen, koppeln und verbinden.', True))
        bluetooth_card.addWidget(label('Nach dem Verbinden: Steuerkreuz oder linker Stick zum Wählen, Bestätigungstaste zum Öffnen. Start öffnet Farbe / Eltern, die rechte Taste geht zurück. Der Elternbereich bleibt PIN-geschützt.', True))
        bluetooth_card.addWidget(button('Bluetooth verwalten', self.open_bluetooth, secondary=True))
        layout.addStretch()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, 'Hintergrundfarbe')
        if color.isValid():
            self.color = color.name().upper(); self.color_dirty = True
            self.update_color_button()

    def update_color_button(self):
        self.color_button.setText('Farbe auswählen · ' + self.color)
        self.color_button.setStyleSheet(f'border:3px solid {self.color};')

    def save_settings(self):
        if self.perform(lambda: parents.save_preferences(self.pin_input.text().strip(), self.pin_confirm.text().strip(), self.color, self.category_tabs_input.isChecked()), 'Einstellungen gespeichert.'):
            self.pin_input.clear(); self.pin_confirm.clear(); self.color_dirty = False

    def refresh(self):
        try:
            st, items = read_settings(), parents.managed_apps()
            info = parents.usage(st)
            self.summary.setText('Heute genutzt: ' + parents.duration(info['used']))
            self.summary_detail.setText('Noch verfügbar: ' + parents.duration(info['remaining']) + f' · Bonus: {info["bonus"]} Min.')
            self.progress.setVisible(info['limit'] > 0)
            self.progress.setValue(info['percent'])
            self.apps_summary.setText(f'{sum(parents.app_active(a, st) for a in items)} von {len(items)} Apps sind freigegeben.')
            self.bonus_label.setText(f'Heute zusätzlich: {info["bonus"]} Minuten')
            if not self.limit_dirty:
                self.limit_spin.blockSignals(True); self.limit_spin.setValue(min(600, info['limit'])); self.limit_spin.blockSignals(False)
            if not self.color_dirty:
                self.color = st['bg_color']; self.update_color_button()
            signature = repr(items)
            if signature != self.app_signature:
                self.render_apps(items, st)
                self.app_signature = signature
            else:
                # Checkbox-Änderungen sollen weder Scrollposition noch Fokus verlieren.
                for widget, item in self.app_rows.values():
                    checkbox = widget.findChild(QCheckBox)
                    checkbox.blockSignals(True)
                    checkbox.setChecked(parents.app_active(item, st))
                    checkbox.blockSignals(False)
        except (ValueError, OSError) as exc:
            self.status.setText('Daten konnten nicht geladen werden: ' + str(exc))

    def open_diagnostics(self):
        dialog = ParentDiagnostics(self); dialog.exec_(); dialog.deleteLater()

    def open_bluetooth(self):
        from laurinos.bluetooth_ui import ParentBluetooth
        dialog = ParentBluetooth(self); dialog.exec_(); dialog.deleteLater()

    def open_wifi(self):
        from laurinos.wifi_ui import ParentWifi
        dialog = ParentWifi(self)
        dialog.exec_()
        command = dialog.advanced_command
        dialog.deleteLater()
        if command and self.parent() and hasattr(self.parent(), 'launch'):
            menu = self.parent()
            self.accept()
            # Beide modalen Schleifen erst verlassen, dann das Vollbildmenü ausblenden.
            QTimer.singleShot(0, lambda: menu.launch({'command': shlex.join(command)}))

    def done(self, result):
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        super().done(result)
