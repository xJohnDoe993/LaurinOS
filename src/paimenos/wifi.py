"""WLAN für beide Elternbereiche; NetworkManager-Zugriff im lokalen Dienst."""
from paimenos.i18n import t
import concurrent.futures
import grp
import json
import os
import re
import socket
import socketserver
import struct
import threading
import time
import uuid

SOCKET_PATH = '/run/paimenos-wifi/api.sock'
NM = 'org.freedesktop.NetworkManager'
ROOT = '/org/freedesktop/NetworkManager'
DEV = NM + '.Device'
WIFI = DEV + '.Wireless'
AP = NM + '.AccessPoint'
ACTIVE = NM + '.Connection.Active'
SETTINGS = NM + '.Settings'
PROFILE = SETTINGS + '.Connection'
SEC = '802-11-wireless-security'
WIRELESS = '802-11-wireless'
MAX_MESSAGE = 512 * 1024


class WifiError(Exception):
    def __init__(self, message, unavailable=False):
        super().__init__(message)
        self.unavailable = unavailable


def friendly_error(error):
    # D-Bus-Fehlertexte können Eingaben enthalten: niemals Passwörter zurückgeben.
    if isinstance(error, (WifiError, ValueError)):
        return str(error)
    name = getattr(error, 'get_dbus_name', lambda: '')().rsplit('.', 1)[-1]
    return {
        'ServiceUnknown': t('Der Netzwerkdienst ist nicht verfügbar.'),
        'NameHasNoOwner': t('Der Netzwerkdienst ist nicht verfügbar.'),
        'NoReply': t('Der Netzwerkdienst antwortet nicht. Bitte erneut versuchen.'),
        'NotAllowed': 'NetworkManager hat diesen WLAN-Vorgang abgelehnt.',
        'PermissionDenied': t('WLAN-Berechtigung fehlt. Bitte PaimenOS-Setup aktualisieren.'),
        'UnknownConnection': t('Das gespeicherte Netzwerk ist nicht mehr vorhanden.'),
        'InvalidConnection': t('Diese Verbindung benötigt erweiterte Einstellungen am Laptop.'),
        'ConnectionNotAvailable': t('Netzwerk momentan nicht erreichbar. Bitte erneut suchen.'),
        'UnknownObject': t('Gerät oder Netzwerk nicht mehr vorhanden. Bitte erneut suchen.'),
    }.get(name, t('WLAN-Vorgang fehlgeschlagen. Netzwerk, Passwort und Hardware-Schalter prüfen.'))


def adapter_problem(adapter):
    if not adapter['managed']:
        message = t('Dieser Adapter wird nicht vom Netzwerkdienst verwaltet.')
    elif adapter['firmware_missing']:
        message = t('Die WLAN-Firmware fehlt.')
    elif adapter['plugin_missing']:
        message = t('Das WLAN-Modul von NetworkManager fehlt.')
    elif 40 <= adapter['state'] <= 90:
        message = t('NetworkManager baut eine Verbindung auf. Die Suche ist währenddessen gesperrt.')
    elif adapter['state'] == 110:
        message = t('Die WLAN-Verbindung wird gerade getrennt.')
    elif adapter['state'] not in (30, 100):
        message = {
            2: t('NetworkManager hat den Adapter übernommen; WLAN ist noch nicht betriebsbereit.'),
            7: t('Für die WLAN-Anmeldung fehlen Zugangsdaten.'),
            8: t('Der WLAN-Anmeldedienst (Supplicant) wurde getrennt.'),
            9: t('Die WLAN-Anmeldung konnte nicht konfiguriert werden.'),
            10: t('Der WLAN-Anmeldedienst (Supplicant) ist fehlgeschlagen.'),
            11: t('Die WLAN-Anmeldung hat zu lange gedauert.'),
            35: t('Die WLAN-Firmware fehlt.'),
            42: t('Der WLAN-Anmeldedienst wird bereitgestellt.'),
        }.get(adapter['reason'], t('Der WLAN-Adapter ist noch nicht betriebsbereit. Netzwerkdienst und WLAN-Anmeldedienst prüfen.'))
    else:
        return ''
    return message + t(' (Zustand {value0}, Grund {value1})', value0=adapter['state'], value1=adapter['reason'])


def wifi_request(action='status', **values):
    payload = json.dumps(dict(values, action=action), ensure_ascii=False).encode() + b'\n'
    if len(payload) > 4096:
        raise WifiError(t('WLAN-Anfrage ist zu groß.'))
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(20)
            connection.connect(SOCKET_PATH)
            connection.sendall(payload)
            with connection.makefile('rb') as stream:
                raw = stream.readline(MAX_MESSAGE + 1)
        if not raw.endswith(b'\n') or len(raw) > MAX_MESSAGE:
            raise ValueError(t('Antwort'))
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError(t('Antwort'))
    except (OSError, ValueError) as exc:
        raise WifiError(t('WLAN-Verwaltung nicht erreichbar. Bitte das aktualisierte Setup installieren.'), True) from exc
    if not result.get('ok'):
        raise WifiError(result.get('error', t('WLAN-Vorgang fehlgeschlagen.')))
    if not isinstance(result.get('state'), dict):
        raise WifiError(t('Ungültige Antwort der WLAN-Verwaltung.'), True)
    return result['state']


def ssid_name(raw):
    return bytes(raw).decode('utf-8', 'replace')


def security(props):
    flags = int(props.get('RsnFlags', 0)) | int(props.get('WpaFlags', 0))
    if flags & 0x100:
        return 'wpa-psk', 'WPA / WPA2' if not flags & 0x400 else 'WPA2 / WPA3'
    if flags & 0x400:
        return 'sae', 'WPA3'
    if flags & (0x200 | 0x2000):
        return 'enterprise', t('Schul- / Firmennetz')
    if flags & (0x800 | 0x1000):
        return 'owe', t('Verschlüsselt ohne Passwort')
    if int(props.get('Flags', 0)) & 1:
        return 'wep', t('WEP · erweiterte Einstellungen')
    return 'open', t('Offen · ohne Verschlüsselung')


def profile_security(settings):
    return str(settings.get(SEC, {}).get('key-mgmt', 'open'))


def compatible(key, other):
    if key == 'enterprise':
        return other in ('wpa-eap', 'wpa-eap-suite-b-192', 'ieee8021x')
    if key == 'wep':
        return other == 'none'
    return key == other or key in ('wpa-psk', 'sae') and other in ('wpa-psk', 'sae')


def validate_password(password, key):
    if not isinstance(password, str) or '\x00' in password:
        raise ValueError(t('Ungültiges WLAN-Passwort.'))
    if key == 'wpa-psk':
        if not (8 <= len(password) <= 63 or re.fullmatch(r'[0-9a-fA-F]{64}', password)):
            raise ValueError(t('WPA2-Passwort: 8 bis 63 Zeichen oder 64 Hexadezimalzeichen eingeben.'))
    elif key == 'sae':
        if not 1 <= len(password.encode('utf-8')) <= 63:
            raise ValueError(t('WPA3-Passwort: 1 bis 63 Bytes eingeben.'))
    elif key not in ('open', 'owe'):
        raise ValueError(t('Dieses Netzwerk benötigt die erweiterten Einstellungen am Laptop.'))


class WifiController:
    """Alle Methoden im GLib-Thread; Verbindungsaufbau wird separat überwacht."""
    def __init__(self, driver, clock=time.monotonic):
        self.driver, self.clock = driver, clock
        self.operation, self.scan = None, None
        self.message, self.error = '', ''

    def read(self):
        manager = self.driver.properties(ROOT, NM)
        adapters, networks, saved = [], [], []
        profiles = self.driver.profiles()
        # GetSettings enthält keine Secrets. Der Status liefert nur ausgewählte Metadaten.
        for path, settings in profiles.items():
            connection = settings.get('connection', {})
            wifi = settings.get(WIRELESS, {})
            if connection.get('type') != WIRELESS or wifi.get('mode', 'infrastructure') != 'infrastructure':
                continue
            raw = bytes(wifi.get('ssid', []))
            saved.append(dict(path=str(path), name=ssid_name(raw), title=str(connection.get('id', ssid_name(raw))),
                              ssid=raw.hex(), key=profile_security(settings), autoconnect=bool(connection.get('autoconnect', True)),
                              connected=False, adapters=[], available=[]))
        for device in self.driver.devices():
            props = self.driver.properties(device, DEV)
            if int(props.get('DeviceType', 0)) != 2:
                continue
            wireless = self.driver.properties(device, WIFI)
            active = str(props.get('ActiveConnection', '/'))
            active_profile = '/'
            if active != '/':
                try:
                    active_profile = str(self.driver.properties(active, ACTIVE).get('Connection', '/'))
                except Exception:
                    pass  # Hotplug / Verbindungswechsel zwischen den beiden Abfragen.
            connected = int(props.get('State', 0)) == 100
            adapter = dict(path=str(device), name=str(props.get('Interface', t('WLAN'))),
                           managed=bool(props.get('Managed', True)), state=int(props.get('State', 0)),
                           reason=int(props.get('StateReason', (0, 0))[1]), active=active,
                           profile=active_profile, connected=connected, last_scan=int(wireless.get('LastScan', -1)),
                           network='', addresses=[])
            adapter['firmware_missing'] = bool(props.get('FirmwareMissing', False))
            adapter['plugin_missing'] = bool(props.get('NmPluginMissing', False))
            adapter['ready'] = adapter['managed'] and adapter['state'] in (30, 100)
            adapter['problem'] = adapter_problem(adapter)
            ipconfig = str(props.get('Ip4Config', '/'))
            if connected and ipconfig != '/':
                try:
                    adapter['addresses'] = [str(a['address']) for a in self.driver.properties(ipconfig, NM + '.IP4Config').get('AddressData', []) if 'address' in a]
                except Exception:
                    pass
            available = set(map(str, props.get('AvailableConnections', [])))
            for profile in saved:
                if profile['path'] in available or profile['path'] == active_profile:
                    profile['available'].append(str(device))
                if connected and profile['path'] == active_profile:
                    profile['connected'] = True
                    profile['adapters'].append(str(device))
                    adapter['network'] = profile['name']
            grouped = {}
            for path in wireless.get('AccessPoints', []):
                try:
                    ap = self.driver.properties(str(path), AP)
                except Exception:
                    continue
                raw = bytes(ap.get('Ssid', []))
                if not raw or int(ap.get('Mode', 2)) != 2:
                    continue
                key, description = security(ap)
                is_active = connected and str(path) == str(wireless.get('ActiveAccessPoint', '/'))
                matches = [p for p in saved if p['ssid'] == raw.hex() and compatible(key, p['key']) and p['path'] in available]
                chosen = next((p for p in matches if p['path'] == active_profile), matches[0] if matches else None)
                item = dict(path=str(path), adapter=str(device), name=ssid_name(raw), ssid=raw.hex(), key=key,
                            security=description, strength=int(ap.get('Strength', 0)), connected=is_active,
                            profile=chosen['path'] if chosen else '', supported=key in ('open', 'wpa-psk', 'sae', 'owe'))
                group = (raw.hex(), key)
                previous = grouped.get(group)
                if previous is None or (is_active, item['strength']) > (previous['connected'], previous['strength']):
                    grouped[group] = item
                if is_active:
                    adapter['network'] = item['name']
            networks.extend(grouped.values())
            adapters.append(adapter)
        networks.sort(key=lambda n:(not n['connected'], -n['strength'], n['name'].casefold()))
        saved.sort(key=lambda p:(not p['connected'], p['name'].casefold(), p['path']))
        return dict(available=True, powered=bool(manager.get('WirelessEnabled', False)),
                    hardware=bool(manager.get('WirelessHardwareEnabled', False)),
                    connectivity=int(manager.get('Connectivity', 0)), adapters=adapters, networks=networks, saved=saved)

    def check_progress(self, state):
        now = self.clock()
        if self.scan:
            adapter = next((a for a in state['adapters'] if a['path'] == self.scan['adapter']), None)
            if adapter and adapter['last_scan'] > self.scan['last_scan']:
                self.scan = None
                self.message = t('Netzwerkliste aktualisiert.')
            elif not adapter or not adapter['ready'] or now >= self.scan['deadline']:
                self.scan = None
                self.message = ''
                self.error = adapter['problem'] if adapter and adapter['problem'] else t('Die WLAN-Suche wurde nicht abgeschlossen. Die angezeigte Liste kann veraltet sein.')
        if not self.operation:
            return
        op = self.operation
        adapter = next((a for a in state['adapters'] if a['path'] == op['adapter']), None)
        try:
            active_state = int(self.driver.properties(op['active'], ACTIVE)['State'])
        except Exception:
            active_state = 4
        if active_state == 2:
            if op['created']:
                try:
                    self.driver.save(op['created'])
                except Exception:
                    self.error = t('Verbunden, aber Netzwerk konnte nicht dauerhaft gespeichert werden.')
            self.message = t('Mit „') + op['name'] + t('“ verbunden.')
            self.operation = None
        elif active_state == 4 or not adapter or adapter['state'] == 120 or now >= op['deadline']:
            reason = adapter['reason'] if adapter else 36
            self.error = t('Keine Verbindung. Passwort prüfen; bei geändertem Passwort das gespeicherte Netzwerk vergessen und erneut verbinden.') if reason in (7, 8, 9, 10, 11) else t('Verbindung fehlgeschlagen. Netzwerk, Passwort und Signalstärke prüfen.')
            self.cleanup_operation()

    def cleanup_operation(self):
        op, self.operation = self.operation, None
        if not op:
            return
        try:
            self.driver.deactivate(op['active'])
        except Exception:
            pass
        if op['created']:
            try:
                self.driver.delete(op['created'])
            except Exception:
                self.error = t('Temporäres Netzwerk konnte nicht entfernt werden. Bitte unter gespeicherten Netzwerken vergessen.')

    def snapshot(self):
        try:
            state = self.read()
            self.check_progress(state)
        except Exception as exc:
            state = dict(available=False, powered=False, hardware=False, connectivity=0, adapters=[], networks=[], saved=[])
            self.error = friendly_error(exc)
        state.update(operation={k:v for k,v in self.operation.items() if k in ('adapter', 'name')} if self.operation else None,
                     scan={'adapter':self.scan['adapter']} if self.scan else None, message=self.message, error=self.error)
        return state

    def handle(self, data):
        if not isinstance(data, dict) or not isinstance(data.get('action'), str):
            raise ValueError(t('Ungültige WLAN-Anfrage.'))
        action = data['action']
        if action == 'status':
            return self.snapshot()
        allowed = {'power_on', 'power_off', 'scan', 'connect', 'hidden', 'disconnect', 'forget', 'autoconnect', 'cancel'}
        if action not in allowed:
            raise ValueError(t('Unbekannte WLAN-Aktion.'))
        state = self.snapshot()
        if not state['available']:
            raise WifiError(t('Der Netzwerkdienst ist nicht verfügbar.'), True)
        if action == 'cancel':
            self.cleanup_operation(); self.message = t('Verbindungsaufbau abgebrochen.'); self.error = ''
            return self.snapshot()
        if self.operation:
            raise ValueError(t('Es wird gerade eine Verbindung aufgebaut. Bitte warten oder abbrechen.'))
        self.message, self.error = '', ''
        if action in ('power_on', 'power_off'):
            self.driver.power(action == 'power_on')
            self.scan = None
            self.message = t('WLAN eingeschaltet.') if action == 'power_on' else t('WLAN ausgeschaltet.')
            return self.snapshot()
        if action in ('forget', 'autoconnect'):
            profile = next((p for p in state['saved'] if p['path'] == data.get('profile')), None)
            if not profile:
                raise ValueError(t('Gespeichertes WLAN nicht mehr vorhanden.'))
            if action == 'forget':
                if profile['connected']:
                    raise ValueError(t('Bitte dieses Netzwerk zuerst trennen, dann vergessen.'))
                self.driver.delete(profile['path']); self.message = t('Netzwerk vergessen.')
            else:
                enabled = data.get('enabled')
                if enabled not in ('0', '1'):
                    raise ValueError(t('Ungültige Einstellung.'))
                self.driver.autoconnect(profile['path'], enabled == '1')
                self.message = t('Automatische Verbindung gespeichert.')
            return self.snapshot()
        adapter = next((a for a in state['adapters'] if a['path'] == data.get('adapter')), None)
        if not adapter or not adapter['managed']:
            raise ValueError(t('Kein verwalteter WLAN-Adapter ausgewählt.'))
        device = adapter['path']
        if action == 'disconnect':
            # Device.Disconnect verhindert sofortiges automatisches Wiederverbinden.
            self.driver.disconnect(device); self.message = t('WLAN-Verbindung getrennt.')
            return self.snapshot()
        if not state['powered'] or not state['hardware']:
            raise ValueError(t('WLAN ist ausgeschaltet oder durch Flugmodus / Hardware-Schalter blockiert.'))
        if not adapter['ready']:
            raise ValueError(adapter['problem'])
        if action == 'scan':
            if self.scan:
                return self.snapshot()
            try:
                self.driver.scan(device)
            except Exception as exc:
                name = getattr(exc, 'get_dbus_name', lambda: '')()
                if not name.endswith('.NotAllowed'):
                    raise
                # Nur bekannte Gründe übersetzen, niemals beliebige D-Bus-Texte ausgeben.
                text = str(exc).lower()
                if 'already scanning' in text:
                    self.scan = dict(adapter=device, last_scan=adapter['last_scan'], deadline=self.clock()+20)
                    self.message = t('NetworkManager sucht bereits. Die laufende Suche wird übernommen.')
                    return self.snapshot()
                if 'immediately following previous scan' in text:
                    self.message = t('NetworkManager hat gerade gesucht. Die vorhandene Netzwerkliste wird angezeigt. Eine neue Suche ist nach einigen Sekunden möglich.')
                    return self.snapshot()
                current = next((a for a in self.read()['adapters'] if a['path'] == device), adapter)
                reason = current['problem'] or t('NetworkManager lehnt die Suche ab (Zustand {value0}, Grund {value1}). Bitte die WLAN-Diagnose prüfen.', value0=current['state'], value1=current['reason'])
                raise WifiError(reason) from exc
            self.scan = dict(adapter=device, last_scan=adapter['last_scan'], deadline=self.clock()+20)
            self.message = t('Netzwerke werden gesucht …')
            return self.snapshot()
        profile = None
        network = None
        if action == 'connect':
            if data.get('profile'):
                profile = next((p for p in state['saved'] if p['path'] == data['profile'] and device in p['available']), None)
                if not profile:
                    raise ValueError(t('Gespeichertes Netzwerk hier nicht erreichbar. Bitte erneut suchen.'))
            else:
                network = next((n for n in state['networks'] if n['path'] == data.get('network') and n['adapter'] == device), None)
                if not network:
                    raise ValueError(t('Netzwerk nicht mehr gefunden. Bitte erneut suchen.'))
                if network['profile']:
                    profile = next(p for p in state['saved'] if p['path'] == network['profile'])
        if profile:
            active = self.driver.activate(profile['path'], device, '/')
            name, created = profile['name'], ''
        else:
            if action == 'hidden':
                name = data.get('ssid', '')
                if not isinstance(name, str) or not 1 <= len(name.encode('utf-8')) <= 32 or '\x00' in name:
                    raise ValueError(t('Netzwerkname muss 1 bis 32 Bytes lang sein.'))
                raw, key, access_point = name.encode('utf-8'), data.get('security'), '/'
                if key not in ('open', 'wpa-psk', 'sae'):
                    raise ValueError(t('Ungültige WLAN-Sicherheit.'))
                if any(p['ssid'] == raw.hex() and compatible(key, p['key']) for p in state['saved']):
                    raise ValueError(t('Dieses WLAN ist bereits gespeichert. Dort verbinden oder zuerst vergessen.'))
            else:
                raw, key, access_point = bytes.fromhex(network['ssid']), network['key'], network['path']
                name = network['name']
            password = data.get('password', '')
            validate_password(password, key)
            settings = {'connection': {'id':name, 'uuid':str(uuid.uuid4()), 'type':WIRELESS, 'autoconnect':True},
                        WIRELESS: {'ssid':raw, 'mode':'infrastructure', 'hidden':action == 'hidden'},
                        'ipv4': {'method':'auto'}, 'ipv6': {'method':'auto'}}
            if key != 'open':
                settings[SEC] = {'key-mgmt':key}
                if key in ('wpa-psk', 'sae'):
                    settings[SEC].update(psk=password, **{'psk-flags':0})
            created, active = self.driver.add_activate(settings, device, access_point)
        self.operation = dict(adapter=device, name=name, active=str(active), created=str(created), deadline=self.clock()+65)
        self.scan = None
        self.message = t('Verbindung zu „') + name + t('“ wird aufgebaut …')
        return self.snapshot()


def run_daemon():
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    class Driver:
        def interface(self, path, interface):
            return dbus.Interface(bus.get_object(NM, path), interface)
        def properties(self, path, interface):
            return self.interface(path, 'org.freedesktop.DBus.Properties').GetAll(interface, timeout=4)
        def devices(self):
            return self.interface(ROOT, NM).GetDevices(timeout=4)
        def profiles(self):
            result = {}
            for path in self.interface(ROOT+'/Settings', SETTINGS).ListConnections(timeout=4):
                try:
                    result[str(path)] = self.interface(path, PROFILE).GetSettings(timeout=4)
                except dbus.DBusException as exc:
                    if not exc.get_dbus_name().endswith('.UnknownObject'):
                        raise
            return result
        def scan(self, device):
            self.interface(device, WIFI).RequestScan(dbus.Dictionary({}, signature='sv'), timeout=4)
        def power(self, enabled):
            self.interface(ROOT, 'org.freedesktop.DBus.Properties').Set(NM, 'WirelessEnabled', dbus.Boolean(enabled), timeout=4)
        def disconnect(self, device):
            self.interface(device, DEV).Disconnect(timeout=4)
        def deactivate(self, active):
            self.interface(ROOT, NM).DeactivateConnection(dbus.ObjectPath(active), timeout=4)
        def delete(self, profile):
            self.interface(profile, PROFILE).Delete(timeout=4)
        def save(self, profile):
            self.interface(profile, PROFILE).Save(timeout=4)
        def autoconnect(self, profile, enabled):
            # Beim vollständigen Update vorhandene Secrets ausschließlich im
            # privilegierten Treiber erhalten; niemals in den Status übernehmen.
            interface = self.interface(profile, PROFILE)
            settings = interface.GetSettings(timeout=4)
            for section in (SEC, '802-1x'):
                if section in settings:
                    secrets = interface.GetSecrets(section, timeout=4)
                    for key, values in secrets.items():
                        settings.setdefault(key, {}).update(values)
            settings['connection']['autoconnect'] = dbus.Boolean(enabled)
            interface.Update(settings, timeout=4)
        def activate(self, profile, device, ap):
            return self.interface(ROOT, NM).ActivateConnection(dbus.ObjectPath(profile), dbus.ObjectPath(device), dbus.ObjectPath(ap), timeout=4)
        def add_activate(self, settings, device, ap):
            typed = {}
            for section, values in settings.items():
                typed[section] = dbus.Dictionary({key: dbus.ByteArray(value) if isinstance(value, bytes) else dbus.Boolean(value) if isinstance(value, bool) else dbus.UInt32(value) if isinstance(value, int) else dbus.String(value) for key, value in values.items()}, signature='sv')
            result = self.interface(ROOT, NM).AddAndActivateConnection2(dbus.Dictionary(typed, signature='sa{sv}'), dbus.ObjectPath(device), dbus.ObjectPath(ap), dbus.Dictionary({'persist':'memory'}, signature='sv'), timeout=4)
            return str(result[0]), str(result[1])

    controller = WifiController(Driver())
    def tick():
        if controller.operation or controller.scan:
            controller.snapshot()
        return True
    GLib.timeout_add_seconds(1, tick)
    def dispatch(data):
        future = concurrent.futures.Future()
        def execute():
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(dict(ok=True, state=controller.handle(data)))
                except Exception as exc:
                    controller.error = friendly_error(exc)
                    future.set_result(dict(ok=False, error=controller.error))
            return False
        GLib.idle_add(execute)
        try:
            return future.result(timeout=18)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return dict(ok=False, error=t('WLAN-Dienst beschäftigt. Bitte erneut versuchen.'))

    kids_uid = __import__('pwd').getpwnam('kids').pw_uid
    slots = threading.BoundedSemaphore(8)
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                _, uid, _ = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid not in (0, kids_uid):
                    return
                self.request.settimeout(20)
                raw = self.rfile.readline(4097)
                if not raw.endswith(b'\n') or len(raw) > 4096:
                    return
                result = dispatch(json.loads(raw))
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode() + b'\n')
            except (OSError, ValueError):
                return
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True
        request_queue_size = 8
        def process_request(self, request, address):
            if not slots.acquire(blocking=False):
                self.shutdown_request(request); return
            try:
                super().process_request(request, address)
            except Exception:
                slots.release(); raise
        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request, address)
            finally:
                slots.release()
    os.umask(0o077)
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    server = Server(SOCKET_PATH, Handler)
    os.chown(SOCKET_PATH, 0, grp.getgrnam('kids').gr_gid)
    os.chmod(SOCKET_PATH, 0o660)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        GLib.MainLoop().run()
    finally:
        server.server_close()


if __name__ == '__main__':
    run_daemon()
