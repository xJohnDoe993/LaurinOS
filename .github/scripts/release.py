"""Build a verified draft; publish only when explicitly requested."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def checked_version(root, tag):
    version = (root / 'VERSION').read_text().strip()
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag) or tag != 'v' + version:
        raise ValueError('Release-Tag und VERSION müssen übereinstimmen: v' + version)
    tree = ast.parse((root / 'src/paimenos/__init__.py').read_text())
    python_version = next((ast.literal_eval(node.value) for node in tree.body
                           if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == '__version__'
                                   for target in node.targets)), None)
    versions = [python_version, json.loads((root / 'manifest.json').read_text())['version'],
                tomllib.loads((root / 'pyproject.toml').read_text())['tool']['paimenos']['version']]
    if any(value != version for value in versions):
        raise ValueError('VERSION, Python-Paket, pyproject.toml und Manifest müssen dieselbe Version haben.')
    return version


def api(endpoint, run, missing=False):
    result = run(['gh', 'api', endpoint], capture_output=True, text=True, check=False)
    if result.returncode:
        if missing and '(HTTP 404)' in result.stderr:
            return None
        raise ValueError('GitHub-Abfrage fehlgeschlagen: ' + result.stderr.strip())
    return json.loads(result.stdout)


def find_release(endpoint, tag, run):
    # The tag endpoint promises published releases. List releases to include drafts
    # visible to the workflow's write token, including drafts without a Git tag yet.
    found = []
    for page in range(1, 101):
        entries = api(endpoint + '/releases?per_page=100&page=' + str(page), run)
        found.extend(item for item in entries if item['tag_name'] == tag)
        if len(entries) < 100:
            if len(found) > 1:
                raise ValueError('Mehrere Releases für denselben Tag; Entwürfe auf GitHub prüfen.')
            return found[0] if found else None
    raise ValueError('Zu viele Releases für die automatische Entwurfsprüfung.')


def checked_reference(endpoint, tag, head, run):
    reference = api(endpoint + '/git/ref/tags/' + tag, run, missing=True)
    if reference:
        target = reference['object']
        for _ in range(8):
            if target['type'] != 'tag':
                break
            target = api(endpoint + '/git/tags/' + target['sha'], run)['object']
        if target['type'] != 'commit' or target['sha'] != head:
            raise ValueError('GitHub-Tag zeigt nicht auf den gebauten Commit. Tag nicht verschieben; neuen Tag verwenden.')
    return reference


def complete_upload(release, assets):
    uploaded = {item['name']: item for item in release['assets']}
    return all(path.name in uploaded and uploaded[path.name]['state'] == 'uploaded'
               and uploaded[path.name]['size'] == path.stat().st_size for path in assets)


def prepare(root, tag, repository, run=subprocess.run, *, publish=False):
    version = checked_version(root, tag)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('GH_REPO muss owner/repo enthalten.')
    notes = root / 'docs/releases' / (version + '.md')
    if publish and (not notes.is_file() or not notes.read_text().strip()):
        raise ValueError('Veröffentlichung benötigt Release-Notizen: ' + str(notes))
    archive = root / 'dist' / ('PaimenOS-' + version + '.zip')
    checksum = archive.with_suffix('.zip.sha256')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if checksum.read_text() != digest + '  ' + archive.name + '\n':
        raise ValueError('ZIP und SHA-256-Datei stimmen nicht überein.')
    with zipfile.ZipFile(archive) as package:
        if package.testzip() or package.read('PaimenOS/VERSION').decode().strip() != version:
            raise ValueError('Release-Archiv beschädigt oder falsche Version.')
    assets = [archive, checksum]
    endpoint = 'repos/' + repository
    head = run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    reference = checked_reference(endpoint, tag, head, run)
    release = find_release(endpoint, tag, run)
    if release:
        if not release['draft']:
            raise ValueError('Release ist bereits veröffentlicht. Für Änderungen eine neue Version verwenden.')
        names = {item['name'] for item in release['assets']}
        if names.intersection(path.name for path in assets):
            raise ValueError('Update-Dateien existieren bereits im Entwurf. Vor einem erneuten Upload '
                             'nur dessen ZIP/SHA-Dateien löschen; veröffentlichte Releases nicht ändern.')
        if reference is None:
            run(['gh', 'release', 'edit', tag, '--repo', repository, '--target', head, '--draft'], check=True)
        run(['gh', 'release', 'upload', tag, *map(str, assets), '--repo', repository], check=True)
    else:
        run(['gh', 'release', 'create', tag, *map(str, assets), '--repo', repository,
             '--target', head, '--draft', '--title', 'PaimenOS ' + version, '--generate-notes'], check=True)
    release = find_release(endpoint, tag, run)
    if release is None:
        raise ValueError('Release-Entwurf nach dem Upload nicht gefunden.')
    if not release['draft'] or not complete_upload(release, assets):
        raise ValueError('Upload nicht vollständig als Entwurf bestätigt. Release noch nicht veröffentlichen.')
    if publish:
        # Set the built commit explicitly, including drafts that do not have a tag yet.
        run(['gh', 'release', 'edit', tag, '--repo', repository, '--target', head,
             '--notes-file', str(notes), '--draft=false', '--prerelease=false', '--latest'], check=True)
        release = find_release(endpoint, tag, run)
        if (release is None or release['draft'] or release.get('prerelease', True)
                or not complete_upload(release, assets)):
            raise ValueError('Stabile Veröffentlichung mit beiden Dateien nicht bestätigt.')
        if checked_reference(endpoint, tag, head, run) is None:
            raise ValueError('GitHub-Tag nach Veröffentlichung nicht gefunden.')
    return release['html_url']


def main():
    parser = argparse.ArgumentParser(description='PaimenOS-Release prüfen und vorbereiten.')
    parser.add_argument('tag')
    parser.add_argument('--check-version', action='store_true')
    parser.add_argument('--publish', action='store_true',
                        help='Nach vollständigem Upload mit docs/releases/VERSION.md stabil veröffentlichen.')
    args = parser.parse_args()
    if args.check_version:
        print('OK: Version ' + checked_version(ROOT, args.tag))
        return
    url = prepare(ROOT, args.tag, os.environ.get('GH_REPO', ''), publish=args.publish)
    if args.publish:
        message = 'Stabiles Release mit ZIP und SHA-256 veröffentlicht: ' + url + '\n'
    else:
        message = ('Release-Entwurf mit ZIP und SHA-256 erstellt: ' + url
                   + '\nNach Geräteprüfung Release-Notizen ergänzen und auf GitHub veröffentlichen.\n')
    print(message)
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(summary).open('a') as output:
            output.write(message)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as exc:
        raise SystemExit('FEHLER: ' + str(exc))
