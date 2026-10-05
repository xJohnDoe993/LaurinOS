"""Bounded HTTPS access to the fixed GitHub release source and safe ZIP extraction."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import zipfile

from laurinos.updates import REPOSITORY, REPOSITORY_URL, UpdateError, version_key

API = 'https://api.github.com/repos/' + REPOSITORY + '/releases/'
MAX_ARCHIVE = 50 * 1024 * 1024
MAX_UNPACKED = 100 * 1024 * 1024
HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


def trusted_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in HOSTS or parts.username or parts.password or parts.port not in (None, 443):
        raise UpdateError('Release-Datei verweist auf eine nicht erlaubte Download-Adresse.')
    return url


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        trusted_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def open_url(url):
    trusted_url(url)
    request = Request(url, headers={'User-Agent': 'LaurinOS-Release-Updater', 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10'})
    return build_opener(SafeRedirect()).open(request, timeout=15)


def download(url, target=None, limit=MAX_ARCHIVE, progress=None):
    started = time.monotonic()
    data = bytearray() if target is None else None
    handle = target.open('wb') if target is not None else None
    try:
        with open_url(url) as response:
            announced = int(response.headers.get('Content-Length', '0'))
            if announced > limit:
                raise UpdateError('Release-Datei überschreitet die erlaubte Größe.')
            count = 0
            while True:
                if time.monotonic() - started > 600:
                    raise UpdateError('Download dauert zu lange. Bitte später erneut versuchen.')
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > limit:
                    raise UpdateError('Release-Datei überschreitet die erlaubte Größe.')
                if handle:
                    handle.write(chunk)
                else:
                    data.extend(chunk)
                if progress:
                    progress(count, announced)
            if announced and count != announced:
                raise UpdateError('Release-Datei wurde unvollständig heruntergeladen.')
        return bytes(data) if data is not None else count
    finally:
        if handle:
            handle.close()


def release_metadata(tag=None):
    endpoint = API + ('tags/' + quote(tag, safe='') if tag else 'latest')
    try:
        payload = json.loads(download(endpoint, limit=1024 * 1024))
    except HTTPError as exc:
        if exc.code == 404 and tag is None:
            return None
        if exc.code in (403, 429):
            raise UpdateError('GitHub begrenzt momentan die Anfragen. Bitte später erneut prüfen.') from exc
        raise UpdateError('GitHub-Release ist derzeit nicht erreichbar.') from exc
    except (URLError, OSError, ValueError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError('Versionsprüfung nicht möglich. Internetverbindung prüfen und später erneut versuchen.') from exc
    return parse_release(payload, expected_tag=tag)


def parse_release(payload, expected_tag=None):
    if not isinstance(payload, dict) or payload.get('draft') or payload.get('prerelease') or not payload.get('published_at'):
        raise UpdateError('Es werden nur veröffentlichte stabile Releases angeboten.')
    tag = payload.get('tag_name', '')
    version_key(tag)
    if expected_tag is not None and tag != expected_tag:
        raise UpdateError('Das ausgewählte Release hat sich geändert. Bitte erneut prüfen.')
    version = tag.removeprefix('v')
    names = ['LaurinOS-' + version + '.zip', 'LaurinOS-v60-modular-' + version + '.zip']
    assets = payload.get('assets', [])
    if not isinstance(assets, list):
        raise UpdateError('Ungültige Release-Dateiliste.')
    by_name = {asset.get('name'): asset for asset in assets if isinstance(asset, dict) and asset.get('state') == 'uploaded'}
    archive_name = next((name for name in names if name in by_name and name + '.sha256' in by_name), None)
    if not archive_name:
        raise UpdateError('Im Release fehlen das LaurinOS-Update-ZIP oder seine SHA-256-Datei.')
    selected = []
    for name in (archive_name, archive_name + '.sha256'):
        asset = by_name[name]
        expected_url = REPOSITORY_URL + '/releases/download/' + quote(tag, safe='') + '/' + name
        if asset.get('browser_download_url') != expected_url:
            raise UpdateError('Release-Datei stammt nicht aus dem festgelegten LaurinOS-Repo.')
        size = asset.get('size')
        bound = MAX_ARCHIVE if name == archive_name else 4096
        if not isinstance(size, int) or not 0 < size <= bound:
            raise UpdateError('Release-Dateigröße ist ungültig.')
        selected.append({'name': name, 'url': expected_url, 'size': size, 'digest': asset.get('digest', '')})
    return {'tag': tag, 'version': version, 'title': str(payload.get('name') or tag)[:200],
            'notes': str(payload.get('body') or '')[:24000], 'published_at': str(payload['published_at'])[:40],
            'url': REPOSITORY_URL + '/releases/tag/' + quote(tag, safe=''),
            'archive': selected[0], 'checksum': selected[1]}


def verify_archive(archive, checksum_text, asset):
    lines = checksum_text.strip().splitlines()
    if len(lines) != 1:
        raise UpdateError('Ungültige SHA-256-Datei.')
    match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?([^/\\\s]+)', lines[0])
    if not match or match[2] != asset['name']:
        raise UpdateError('SHA-256-Datei passt nicht zum Update-Archiv.')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != match[1].lower():
        raise UpdateError('Prüfsumme stimmt nicht überein. Update wurde nicht installiert.')
    github_digest = asset.get('digest')
    if github_digest and github_digest != 'sha256:' + digest:
        raise UpdateError('GitHub-Dateiprüfsumme stimmt nicht überein.')


def extract_archive(archive, target):
    """Accept only the release layout, normal files and bounded extraction."""
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if not members or len(members) > 5000 or sum(item.file_size for item in members) > MAX_UNPACKED:
            raise UpdateError('Update-Archiv ist zu groß oder ungültig.')
        seen = set()
        for item in members:
            name = item.filename
            path = PurePosixPath(name)
            mode = item.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if ('\\' in name or '\x00' in name or path.is_absolute() or '..' in path.parts or
                    not path.parts or path.parts[0] != 'LaurinOS' or path.as_posix() in seen or
                    kind not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1 or
                    item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                raise UpdateError('Update-Archiv enthält einen unerlaubten Dateipfad oder Dateityp.')
            seen.add(path.as_posix())
        target.mkdir(parents=True, exist_ok=True)
        # Validate everything before writing any archive file.
        for item in members:
            path = target.joinpath(*PurePosixPath(item.filename).parts)
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with package.open(item) as source, path.open('xb') as out:
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                path.chmod(0o600)
    root = target / 'LaurinOS'
    for relative in ('VERSION', 'manifest.json', 'tools/deploy.py', 'src/laurinos/__init__.py'):
        if not (root / relative).is_file():
            raise UpdateError('Das Archiv enthält kein vollständiges modulares LaurinOS-Release.')
    return root
