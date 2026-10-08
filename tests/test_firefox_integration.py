"""Real Firefox/X11/cache checks, enabled in the Debian CI containers."""
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from paimenos import browser


@unittest.skipUnless(os.environ.get('PAIMENOS_FIREFOX_INTEGRATION') == '1', 'requires Firefox, Openbox and X11')
class FirefoxIntegrationTests(unittest.TestCase):
    def test_cache_clean_close_crash_and_orphan_restart(self):
        from Xlib import Xatom, display
        requests = Counter()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests[self.path] += 1
                if self.path == '/asset.js':
                    body = b'document.title="PaimenOS cache ready";'
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/javascript')
                    self.send_header('Cache-Control', 'public, max-age=86400')
                else:
                    body = b'<html><head><title>loading</title></head><body><script src="/asset.js"></script></body></html>'
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        x = display.Display()
        process = None

        def visible_ready():
            prop = x.screen().root.get_full_property(x.intern_atom('_NET_CLIENT_LIST'), Xatom.WINDOW)
            if prop is None:
                return False
            for wid in prop.value:
                try:
                    window = x.create_resource_object('window', int(wid))
                    title = window.get_full_property(x.intern_atom('_NET_WM_NAME'), x.intern_atom('UTF8_STRING'))
                    if title is not None and b'PaimenOS cache ready' in bytes(title.value):
                        return True
                except Exception:
                    continue
            return False

        try:
            with tempfile.TemporaryDirectory() as folder:
                profile = Path(folder) / 'profile'
                command = [sys.executable, '-I', str(ROOT / 'run.py'), 'close_overlay', '--browser',
                           str(profile), str(Path(folder) / 'missing-template.js'),
                           f'http://127.0.0.1:{server.server_port}/']
                for attempt, mode in enumerate(('normal', 'normal', 'crash', 'orphan', 'normal')):
                    previous_pages = requests['/']
                    environment = dict(os.environ, MOZ_LOG='cache2:5,nsHttp:5',
                                       MOZ_LOG_FILE=str(Path(folder) / f'cache-{attempt}.log'))
                    process = subprocess.Popen(command, env=environment)
                    deadline = time.monotonic() + 45
                    while time.monotonic() < deadline:
                        self.assertIsNone(process.poll(), 'Firefox supervisor exited during startup')
                        if requests['/'] > previous_pages and visible_ready():
                            break
                        time.sleep(.1)
                    else:
                        self.fail('Requested page was not shown; possible restore/lock dialog')
                    # Allow async cache writes before shutdown.
                    time.sleep(1)
                    if mode == 'crash':
                        pids = [int(p.name) for p in Path('/proc').iterdir()
                                if p.name.isdigit() and browser.owns_profile(int(p.name), str(profile))]
                        self.assertEqual(len(pids), 1)
                        os.killpg(pids[0], signal.SIGKILL)
                        self.assertNotEqual(process.wait(timeout=15), 0)
                    elif mode == 'orphan':
                        process.kill()
                        process.wait(timeout=5)
                        # The next supervisor must recover this exact profile.
                    else:
                        process.terminate()
                        self.assertEqual(process.wait(timeout=15), 0)
                        self.assertTrue(browser.profile_available(str(profile)))
                    process = None
                    if mode == 'normal':
                        if requests['/asset.js'] != 1:
                            print('CACHE DIAGNOSTICS', flush=True)
                            for path in Path(folder).rglob(f'cache-{attempt}.log*'):
                                lines = path.read_text(errors='replace').splitlines()
                                print('\n'.join(line for line in lines if any(word in line for word in
                                      ('Validating', 'validating', 'expiration time', 'CheckCache', 'no-cache', 'load flags')))[-20000:], flush=True)
                                for index, line in enumerate(lines):
                                    if '/asset.js' in line:
                                        print('\n'.join(lines[max(0,index-3):index+12]), flush=True)
                            print('cache files:', [str(p.relative_to(profile)) for p in profile.rglob('*') if 'cache' in str(p)], flush=True)
                            print('cache prefs:', [line for line in (profile / 'prefs.js').read_text().splitlines()
                                                   if 'cache' in line or 'sanitize' in line or 'privatebrowsing' in line], flush=True)
                        self.assertEqual(requests['/asset.js'], 1, 'Cacheable asset downloaded again')
                self.assertGreaterEqual(requests['/'], 5)
        finally:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            x.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
