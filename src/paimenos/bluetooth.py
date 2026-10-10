"""Bluetooth für beide Elternbereiche; BlueZ-Zugriff nur im lokalen Dienst."""
from paimenos.i18n import t
import concurrent.futures
import json
import os
import re
import secrets
import socket
import socketserver
import threading
import time

SOCKET_PATH = '/run/paimenos-bluetooth/api.sock'
ADAPTER = 'org.bluez.Adapter1'
DEVICE = 'org.bluez.Device1'
AGENT = 'org.bluez.Agent1'
MAX_MESSAGE = 256 * 1024


class BluetoothError(Exception):
    def __init__(self, message, unavailable=False):
        super().__init__(message)
        self.unavailable = unavailable


def friendly_error(error):
    name = getattr(error, 'get_dbus_name', lambda: '')()
    messages = {
        'NotReady': t('Bluetooth ist ausgeschaltet oder blockiert. Bitte auch den Flugmodus bzw. Hardware-Schalter prüfen.'),
        'AuthenticationFailed': t('Kopplung fehlgeschlagen. Gerät erneut in den Kopplungsmodus versetzen und nochmals versuchen.'),
        'AuthenticationRejected': t('Die Kopplung wurde abgelehnt.'),
        'AuthenticationCanceled': t('Die Kopplung wurde abgebrochen.'),
        'AuthenticationTimeout': t('Zeit für die Kopplung abgelaufen. Gerät erneut in den Kopplungsmodus versetzen.'),
        'ConnectionAttemptFailed': t('Keine Verbindung. Gerät einschalten, näher an den Laptop legen und erneut versuchen.'),
        'InProgress': t('Für dieses Gerät läuft bereits ein Vorgang.'),
        'NotSupported': t('Dieses Gerät oder Bluetooth-Profil wird nicht unterstützt.'),
        'AccessDenied': t('Bluetooth-Berechtigung fehlt. Bitte PaimenOS-Setup aktualisieren.'),
        'ServiceUnknown': t('Der Bluetooth-Dienst ist nicht verfügbar.'),
        'NameHasNoOwner': t('Der Bluetooth-Dienst ist nicht verfügbar.'),
        'NoReply': t('Der Bluetooth-Dienst antwortet nicht. Bitte erneut versuchen.'),
    }
    if name.rsplit('.', 1)[-1] in messages:
        return messages[name.rsplit('.', 1)[-1]]
    text = str(error)[:240]
    if 'br-connection-profile-unavailable' in text:
        return t('Bluetooth-Profil nicht verfügbar. Gerät erneut koppeln; bei Kopfhörern Bluetooth-Audio-Pakete prüfen.')
    return text or t('Bluetooth-Vorgang fehlgeschlagen.')


def bluetooth_request(action='status', **values):
    payload = json.dumps(dict(values, action=action), ensure_ascii=False).encode() + b'\n'
    if len(payload) > 4096:
        raise BluetoothError(t('Bluetooth-Anfrage ist zu groß.'))
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(4)
            connection.connect(SOCKET_PATH)
            connection.sendall(payload)
            with connection.makefile('rb') as stream:
                raw = stream.readline(MAX_MESSAGE + 1)
        if not raw.endswith(b'\n') or len(raw) > MAX_MESSAGE:
            raise ValueError(t('Ungültige Antwort'))
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError(t('Ungültige Antwort'))
    except (OSError, ValueError) as exc:
        raise BluetoothError(t('Bluetooth-Verwaltung nicht erreichbar. Bitte das aktualisierte Setup installieren.'), True) from exc
    if not result.get('ok'):
        raise BluetoothError(result.get('error', t('Bluetooth-Vorgang fehlgeschlagen.')))
    if not isinstance(result.get('state'), dict):
        raise BluetoothError(t('Ungültige Antwort der Bluetooth-Verwaltung.'), True)
    return result['state']


class BluetoothController:
    """Alle Methoden laufen im GLib-Thread; Pair/Connect bleiben asynchron."""
    def __init__(self, driver, clock=time.monotonic):
        self.driver, self.clock = driver, clock
        self.operation = None
        self.prompt = None
        self.prompt_callbacks = None
        self.scan = None
        self.message, self.error = '', ''

    def objects(self):
        return self.driver.objects()

    def checked(self, path, interface):
        pattern = r'/org/bluez/hci[0-9]+' + (r'/dev_(?:[0-9A-Fa-f]{2}_){5}[0-9A-Fa-f]{2}' if interface == DEVICE else '')
        if not isinstance(path, str) or not re.fullmatch(pattern, path):
            raise ValueError(t('Ungültiges Bluetooth-Gerät.'))
        properties = self.objects().get(path, {}).get(interface)
        if properties is None:
            raise ValueError(t('Gerät ist nicht mehr verfügbar. Bitte erneut suchen.'))
        return properties

    def snapshot(self):
        try:
            objects = self.objects()
        except Exception as exc:
            return dict(available=False, adapters=[], devices=[], scan=None, operation=self.operation,
                        prompt=self.prompt, message=self.message, error=friendly_error(exc),
                        events=list(getattr(self.driver, 'events', [])))
        adapters, devices = [], []
        for path, interfaces in objects.items():
            if ADAPTER in interfaces:
                props = interfaces[ADAPTER]
                adapters.append(dict(path=str(path), name=str(props.get('Alias', props.get('Name', 'Bluetooth'))),
                                     powered=bool(props.get('Powered')), discovering=bool(props.get('Discovering'))))
            if DEVICE in interfaces:
                props = interfaces[DEVICE]
                devices.append(dict(path=str(path), adapter=str(props.get('Adapter', '')),
                    name=str(props.get('Alias', props.get('Name', props.get('Address', t('Unbekanntes Gerät')))))[:160],
                    # BlueZ only sets Name when the device reports one; the Alias then falls back to the address.
                    named=bool(str(props.get('Name', '')).strip()),
                    address=str(props.get('Address', '')), icon=str(props.get('Icon', '')),
                    paired=bool(props.get('Paired')), connected=bool(props.get('Connected')),
                    trusted=bool(props.get('Trusted'))))
        devices.sort(key=lambda device: (not device['connected'], not device['paired'], device['name'].casefold(), device['path']))
        return dict(available=True, adapters=sorted(adapters, key=lambda a:a['path']), devices=devices[:128],
                    scan=self.scan, operation=self.operation, prompt=self.prompt,
                    message=self.message, error=self.error or getattr(self.driver, 'load_error', ''),
                    events=list(getattr(self.driver, 'events', [])))

    def stop_scan(self, success=None, error=None):
        success = success or (lambda: None)
        error = error or (lambda exc: setattr(self, 'error', friendly_error(exc)))
        scan = self.scan
        if scan:
            self.scan = None
            def failed(exc):
                if getattr(exc, 'get_dbus_name', lambda: '')().endswith(('.NotReady', '.NotInProgress')):
                    success()
                else:
                    error(exc)
            self.driver.async_method(scan['adapter'], ADAPTER, 'StopDiscovery', success, failed)
        else:
            success()

    def finish(self, token, message='', error=''):
        if not self.operation or self.operation['id'] != token:
            return
        self.clear_prompt(reject=True)
        self.operation = None
        self.message, self.error = message, error

    def start_operation(self, action, path, timeout=40):
        props = self.checked(path, DEVICE)
        adapter = str(props['Adapter'])
        if action in ('pair', 'connect') and not self.checked(adapter, ADAPTER).get('Powered'):
            raise BluetoothError(t('Bluetooth einschalten, bevor ein Gerät verbunden wird.'))
        token = secrets.token_hex(12)
        self.operation = dict(id=token, action=action, device=path,
                              name=str(props.get('Alias', props.get('Address', t('Gerät'))))[:160],
                              deadline=self.clock() + timeout)
        self.message, self.error = t('Gerät wird gekoppelt …') if action == 'pair' else t('Verbindung wird hergestellt …'), ''
        return token

    def connect(self, token, paired=False):
        if not self.operation or self.operation['id'] != token:
            return
        path = self.operation['device']
        self.operation['action'] = 'connect'
        self.operation['deadline'] = self.clock() + 40
        try:
            # Nur nach erfolgreichem Pair() oder für ein bereits gekoppeltes Gerät.
            if not self.checked(path, DEVICE).get('Paired'):
                raise BluetoothError(t('Gerät zuerst koppeln.'))
            def trusted():
                if not self.operation or self.operation['id'] != token:
                    return
                self.driver.async_method(path, DEVICE, 'Connect',
                    lambda: self.finish(token, t('Gerät gekoppelt und verbunden.') if paired else t('Gerät verbunden.')),
                    lambda error: self.connection_failed(token, error, paired))
            self.driver.set_property(path, DEVICE, 'Trusted', True, trusted,
                lambda error: self.connection_failed(token, error, paired))
        except Exception as exc:
            self.connection_failed(token, exc, paired)

    def connection_failed(self, token, error, paired):
        if getattr(error, 'get_dbus_name', lambda:'')().endswith('.AlreadyConnected'):
            self.finish(token, t('Gerät verbunden.'))
        else:
            prefix = t('Gerät ist gekoppelt. Verbindung noch nicht hergestellt: ') if paired else ''
            self.finish(token, error=prefix + friendly_error(error))

    def clear_prompt(self, reject=False):
        callbacks, self.prompt_callbacks = self.prompt_callbacks, None
        self.prompt = None
        if callbacks and reject:
            callbacks[1](self.driver.rejected(t('Kopplung abgebrochen.')))

    def require_target(self, path):
        if not self.operation or self.operation['action'] != 'pair' or self.operation['device'] != str(path):
            raise self.driver.rejected(t('Nur die im Elternbereich gestartete Kopplung ist erlaubt.'))

    def request_prompt(self, kind, path, success, error, code='', entered=0):
        try:
            self.require_target(path)
            self.clear_prompt(reject=True)
            self.prompt = dict(id=secrets.token_hex(12), kind=kind, device=str(path),
                               name=self.operation['name'], code=str(code), entered=int(entered),
                               deadline=min(self.operation['deadline'], self.clock() + 60))
            self.prompt_callbacks = (success, error)
        except Exception as exc:
            error(exc)

    def display_prompt(self, kind, path, code, entered=0):
        self.require_target(path)
        self.clear_prompt(reject=True)
        self.prompt = dict(id=secrets.token_hex(12), kind=kind, device=str(path),
                           name=self.operation['name'], code=str(code), entered=int(entered),
                           deadline=self.operation['deadline'])

    def answer(self, data):
        if not self.prompt or data.get('prompt_id') != self.prompt['id'] or not self.prompt_callbacks:
            raise ValueError(t('Kopplungsanfrage ist abgelaufen. Bitte aktualisieren.'))
        if data.get('accept') not in ('0', '1'):
            raise ValueError(t('Bitte Kopplung bestätigen oder ablehnen.'))
        if data['accept'] == '0':
            self.cancel()
            return
        kind = self.prompt['kind']
        value = data.get('value', '')
        if not isinstance(value, str):
            raise ValueError(t('Ungültiger Kopplungscode.'))
        if kind == 'pin' and (not 1 <= len(value) <= 16 or not value.isascii() or not value.isalnum()):
            raise ValueError(t('PIN muss 1–16 Buchstaben/Ziffern enthalten.'))
        if kind == 'passkey' and not re.fullmatch(r'[0-9]{1,6}', value):
            raise ValueError(t('Code muss 1–6 Ziffern enthalten.'))
        success, _ = self.prompt_callbacks
        self.prompt, self.prompt_callbacks = None, None
        if kind == 'pin':
            success(value)
        elif kind == 'passkey':
            success(self.driver.passkey(int(value)))
        else:
            success()

    def cancel(self):
        operation, self.operation = self.operation, None
        self.clear_prompt(reject=True)
        if operation:
            if operation['action'] in ('pair', 'connect'):
                method = 'CancelPairing' if operation['action'] == 'pair' else 'Disconnect'
                self.driver.async_method(operation['device'], DEVICE, method, lambda:None, lambda error:None)
            elif operation['action'] == 'scan':
                self.driver.async_method(operation['device'], ADAPTER, 'StopDiscovery', lambda:None, lambda error:None)
        self.message, self.error = t('Vorgang abgebrochen.'), ''

    def tick(self):
        if self.operation and (self.clock() >= self.operation['deadline'] or
                               (self.prompt and self.clock() >= self.prompt['deadline'])):
            self.cancel()
            self.error = t('Zeit für den Bluetooth-Vorgang abgelaufen. Bitte erneut versuchen.')
        if self.scan and self.clock() >= self.scan['deadline']:
            try:
                self.stop_scan()
            except Exception:
                pass
        return True

    def handle(self, data):
        if not isinstance(data, dict):
            raise ValueError(t('Ungültige Bluetooth-Anfrage.'))
        self.tick()
        action = data.get('action')
        if action == 'status':
            return self.snapshot()
        if action == 'answer':
            self.answer(data)
            return self.snapshot()
        if action == 'cancel':
            self.cancel()
            return self.snapshot()
        if action == 'stop_scan':
            self.stop_scan()
            return self.snapshot()
        if self.operation:
            raise BluetoothError(t('Bitte den laufenden Vorgang abschließen oder abbrechen.'))
        self.error = ''
        if action in ('power_on', 'power_off', 'scan'):
            adapter = data.get('adapter')
            props = self.checked(adapter, ADAPTER)
            token = secrets.token_hex(12)
            self.operation = dict(id=token, action=action, device=adapter,
                                  name=str(props.get('Alias', 'Bluetooth')), deadline=self.clock()+15)
            self.message = t('Bluetooth wird eingerichtet …')
            def fail(exc):
                self.finish(token, error=friendly_error(exc))
            def powered():
                if not self.operation or self.operation['id'] != token:
                    return
                if action != 'scan':
                    self.finish(token, t('Bluetooth eingeschaltet.') if action == 'power_on' else t('Bluetooth ausgeschaltet.'))
                    return
                def scanned():
                    if self.operation and self.operation['id'] == token:
                        self.scan = dict(adapter=adapter, deadline=self.clock() + 30)
                        self.finish(token, t('Suche läuft 30 Sekunden. Gerät jetzt in den Kopplungsmodus versetzen.'))
                    else:
                        self.driver.async_method(adapter, ADAPTER, 'StopDiscovery', lambda:None, lambda error:None)
                self.driver.async_method(adapter, ADAPTER, 'StartDiscovery', scanned, fail)
            def set_power():
                if self.operation and self.operation['id'] == token:
                    self.driver.set_property(adapter, ADAPTER, 'Powered', action != 'power_off', powered, fail)
            if self.scan:
                self.stop_scan(set_power, fail)
            else:
                set_power()
        elif action in ('pair', 'connect'):
            props = self.checked(data.get('device'), DEVICE)
            if action == 'connect' and not props.get('Paired'):
                raise BluetoothError(t('Gerät zuerst koppeln.'))
            token = self.start_operation(action, data['device'], 120 if action == 'pair' else 40)
            try:
                def fail(exc):
                    self.finish(token, error=friendly_error(exc))
                def begin():
                    if not self.operation or self.operation['id'] != token:
                        return
                    if action == 'connect' or props.get('Paired'):
                        self.connect(token)
                    else:
                        def registered():
                            if self.operation and self.operation['id'] == token:
                                self.driver.async_method(data['device'], DEVICE, 'Pair',
                                    lambda:self.connect(token, paired=True), fail)
                        self.driver.ensure_agent(self, registered, fail)
                # Keine laufende Gerätesuche parallel zur Controller-Kopplung.
                self.stop_scan(begin, fail)
            except Exception as exc:
                self.finish(token, error=friendly_error(exc))
        elif action in ('disconnect', 'remove'):
            props = self.checked(data.get('device'), DEVICE)
            token = self.start_operation(action, data['device'])
            fail = lambda error: self.finish(token, error=friendly_error(error))
            if action == 'remove':
                self.driver.async_method(str(props['Adapter']), ADAPTER, 'RemoveDevice',
                    lambda:self.finish(token, t('Gerät entfernt. Für eine neue Verbindung muss es erneut gekoppelt werden.')),
                    fail, data['device'])
            else:
                if props.get('Connected'):
                    self.driver.async_method(data['device'], DEVICE, 'Disconnect',
                        lambda:self.finish(token, t('Gerät getrennt. Die Kopplung bleibt gespeichert.')), fail)
                else:
                    self.finish(token, t('Gerät ist bereits getrennt. Die Kopplung bleibt gespeichert.'))
        else:
            raise ValueError(t('Unbekannte Bluetooth-Aktion.'))
        return self.snapshot()



"""BlueZ-Client mit lokalem Objektcache und ausschließlich asynchronen RPCs."""
class AsyncBluezDriver:
    def __init__(self, bus, dbus, agent_factory, clock=time.monotonic):
        self.bus, self.dbus, self.agent_factory, self.clock = bus, dbus, agent_factory, clock
        self.agent = None
        self.agent_registered = False
        self.cache, self.ready, self.fetching = {}, False, False
        self.load_error = ''
        self.pending_signals = []
        self.generation, self.last_refresh = 0, -100
        self.on_lost = lambda: None
        self.events = []
        bus.add_signal_receiver(self.added, signal_name='InterfacesAdded',
            dbus_interface='org.freedesktop.DBus.ObjectManager', bus_name='org.bluez')
        bus.add_signal_receiver(self.removed, signal_name='InterfacesRemoved',
            dbus_interface='org.freedesktop.DBus.ObjectManager', bus_name='org.bluez')
        bus.add_signal_receiver(self.changed, signal_name='PropertiesChanged',
            dbus_interface='org.freedesktop.DBus.Properties', bus_name='org.bluez', path_keyword='path')
        bus.add_signal_receiver(self.owner_changed, signal_name='NameOwnerChanged',
            dbus_interface='org.freedesktop.DBus', bus_name='org.freedesktop.DBus', arg0='org.bluez')
        self.refresh()

    def trace(self, message):
        text = str(message)[:400]
        self.events.append(text)
        self.events = self.events[-20:]
        print('Bluetooth: ' + text, flush=True)

    def interface(self, path, interface):
        # Keine synchrone Introspektion oder Namensauflösung während Agent-Callbacks.
        proxy = self.bus.get_object('org.bluez', path, introspect=False, follow_name_owner_changes=True)
        return self.dbus.Interface(proxy, interface)

    def objects(self):
        if not self.ready:
            raise BluetoothError(self.load_error or t('Bluetooth-Geräteliste wird geladen. Bitte kurz warten.'))
        return self.cache

    def signal(self, kind, values):
        if self.fetching:
            self.pending_signals.append((kind, values))
            # Gerätelisten sind begrenzt; eine Scan-Flut darf nicht beliebig RAM belegen.
            if len(self.pending_signals) > 2048:
                self.pending_signals = self.pending_signals[-2048:]
        self.apply(kind, values)

    def apply(self, kind, values):
        path = str(values[0])
        if not path.startswith('/org/bluez/'):
            return
        if kind == 'added':
            target = self.cache.setdefault(path, {})
            for interface, properties in values[1].items():
                target.setdefault(str(interface), {}).update(dict(properties))
        elif kind == 'removed':
            for interface in values[1]:
                self.cache.get(path, {}).pop(str(interface), None)
            if not self.cache.get(path):
                self.cache.pop(path, None)
        else:
            _, interface, changed, invalidated = values
            props = self.cache.setdefault(path, {}).setdefault(str(interface), {})
            props.update(dict(changed))
            for key in invalidated:
                props.pop(str(key), None)

    def added(self, path, interfaces):
        self.signal('added', (path, interfaces))

    def removed(self, path, interfaces):
        self.signal('removed', (path, interfaces))

    def changed(self, interface, changed, invalidated, path=None):
        if path is not None:
            self.signal('changed', (path, interface, changed, invalidated))

    def owner_changed(self, name, previous, current):
        self.generation += 1
        self.ready, self.fetching, self.agent_registered = False, False, False
        self.cache, self.pending_signals = {}, []
        self.trace(t('Bluetooth-Dienst neu gestartet.') if current else t('Bluetooth-Dienst beendet.'))
        self.on_lost()
        if current:
            self.refresh()
        else:
            self.load_error = t('Der Bluetooth-Dienst wurde beendet. Warte auf Neustart.')

    def refresh(self):
        if self.fetching:
            return
        self.fetching = True
        self.last_refresh = self.clock()
        generation = self.generation
        def success(objects):
            if generation != self.generation:
                return
            self.cache = {str(path): {str(interface): dict(props) for interface, props in interfaces.items()}
                          for path, interfaces in objects.items()}
            for kind, values in self.pending_signals:
                self.apply(kind, values)
            self.pending_signals = []
            self.fetching, self.ready, self.load_error = False, True, ''
        def error(exc):
            if generation != self.generation:
                return
            self.fetching = False
            self.pending_signals = []
            self.load_error = friendly_error(exc)
            self.trace(t('Geräteliste: ') + self.load_error)
        try:
            self.interface('/', 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(
                reply_handler=success, error_handler=error, timeout=5, signature='')
        except Exception as exc:
            error(exc)

    def poll(self):
        interval = 30 if self.ready else 3
        if self.clock() - self.last_refresh >= interval:
            self.refresh()
        return True

    def async_method(self, path, interface, method, success, error, *args):
        started, generation = self.clock(), self.generation
        timeout = 125 if method == 'Pair' else 40 if method == 'Connect' else 5
        self.trace(method + t(' gestartet'))
        def reply(*values):
            if generation != self.generation:
                return
            props = self.cache.get(str(path), {}).get(interface, {})
            if method == 'Pair':
                props['Paired'] = True
            elif method in ('Connect', 'Disconnect'):
                props['Connected'] = method == 'Connect'
            elif method == 'RemoveDevice' and args:
                self.cache.pop(str(args[0]), None)
            elif method in ('StartDiscovery', 'StopDiscovery'):
                props['Discovering'] = method == 'StartDiscovery'
            self.trace(method + t(' abgeschlossen nach ') + f'{self.clock() - started:.1f}' + ' s')
            success(*values)
        def failed(exc):
            if generation != self.generation:
                return
            self.trace(method + ': ' + friendly_error(exc))
            error(exc)
        try:
            converted = [self.dbus.ObjectPath(arg) if method == 'RemoveDevice' else arg for arg in args]
            getattr(self.interface(path, interface), method)(*converted,
                reply_handler=reply, error_handler=failed, timeout=timeout,
                signature='o' if method == 'RemoveDevice' else '')
        except Exception as exc:
            failed(exc)

    def set_property(self, path, interface, name, value, success, error):
        generation = self.generation
        def reply():
            if generation != self.generation:
                return
            self.cache.setdefault(str(path), {}).setdefault(interface, {})[name] = bool(value)
            success()
        def failed(exc):
            if generation == self.generation:
                self.trace(t('Eigenschaft ') + name + ': ' + friendly_error(exc))
                error(exc)
        try:
            self.interface(path, 'org.freedesktop.DBus.Properties').Set(
                interface, name, self.dbus.Boolean(value, variant_level=1),
                reply_handler=reply, error_handler=failed, timeout=5, signature='ssv')
        except Exception as exc:
            failed(exc)

    def ensure_agent(self, engine, success, error):
        if self.agent_registered:
            success()
            return
        if self.agent is None:
            self.agent = self.agent_factory(self.bus, '/org/paimenos/BluetoothAgent')
        generation = self.generation
        def reply():
            if generation == self.generation:
                self.agent_registered = True
                success()
        def failed(exc):
            if generation != self.generation:
                return
            if getattr(exc, 'get_dbus_name', lambda: '')().endswith('.AlreadyExists'):
                reply()
            else:
                error(exc)
        try:
            self.interface('/org/bluez', 'org.bluez.AgentManager1').RegisterAgent(
                self.dbus.ObjectPath('/org/paimenos/BluetoothAgent'), 'KeyboardDisplay',
                reply_handler=reply, error_handler=failed, timeout=5, signature='os')
        except Exception as exc:
            failed(exc)

    def rejected(self, message):
        class Rejected(self.dbus.DBusException):
            _dbus_error_name = 'org.bluez.Error.Rejected'
        return Rejected(message)

    def passkey(self, value):
        return self.dbus.UInt32(value)

def run_daemon():
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    class Rejected(dbus.DBusException):
        _dbus_error_name = 'org.bluez.Error.Rejected'

    class Agent(dbus.service.Object):
        @dbus.service.method(AGENT, in_signature='', out_signature='')
        def Release(self):
            controller.cancel()

        @dbus.service.method(AGENT, in_signature='o', out_signature='s', async_callbacks=('reply', 'error'))
        def RequestPinCode(self, device, reply, error):
            controller.request_prompt('pin', device, reply, error)

        @dbus.service.method(AGENT, in_signature='o', out_signature='u', async_callbacks=('reply', 'error'))
        def RequestPasskey(self, device, reply, error):
            controller.request_prompt('passkey', device, reply, error)

        @dbus.service.method(AGENT, in_signature='ou', out_signature='', async_callbacks=('reply', 'error'))
        def RequestConfirmation(self, device, passkey, reply, error):
            controller.request_prompt('confirm', device, reply, error, f'{int(passkey):06d}')

        @dbus.service.method(AGENT, in_signature='o', out_signature='', async_callbacks=('reply', 'error'))
        def RequestAuthorization(self, device, reply, error):
            controller.request_prompt('authorize', device, reply, error)

        @dbus.service.method(AGENT, in_signature='os', out_signature='')
        def DisplayPinCode(self, device, pincode):
            controller.display_prompt('display', device, pincode)

        @dbus.service.method(AGENT, in_signature='ouq', out_signature='')
        def DisplayPasskey(self, device, passkey, entered):
            controller.display_prompt('display', device, f'{int(passkey):06d}', entered)

        @dbus.service.method(AGENT, in_signature='os', out_signature='')
        def AuthorizeService(self, device, uuid):
            props = controller.checked(str(device), DEVICE)
            if not (props.get('Paired') and props.get('Trusted')):
                controller.require_target(device)

        @dbus.service.method(AGENT, in_signature='', out_signature='')
        def Cancel(self):
            controller.clear_prompt(reject=True)

    driver = AsyncBluezDriver(bus, dbus, Agent)
    controller = BluetoothController(driver)
    driver.on_lost = controller.cancel
    GLib.timeout_add_seconds(3, driver.poll)
    GLib.timeout_add_seconds(1, controller.tick)

    def dispatch(data):
        future = concurrent.futures.Future()
        def execute():
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(dict(ok=True, state=controller.handle(data)))
                except Exception as exc:
                    controller.error = friendly_error(exc)
                    future.set_result(dict(ok=False, error=friendly_error(exc)))
            return False
        GLib.idle_add(execute)
        try:
            return future.result(timeout=2)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return dict(ok=False, error=t('Bluetooth-Dienst beschäftigt. Bitte erneut versuchen.'))

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(12)
            try:
                raw = self.rfile.readline(4097)
                if not raw.endswith(b'\n') or len(raw) > 4096:
                    raise ValueError(t('Ungültige Bluetooth-Anfrage.'))
                result = dispatch(json.loads(raw))
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode() + b'\n')
            except (OSError, ValueError):
                return

    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True
        request_queue_size = 8

    os.umask(0o077)
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    server = Server(SOCKET_PATH, Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        GLib.MainLoop().run()
    finally:
        server.server_close()


if __name__ == '__main__':
    run_daemon()

