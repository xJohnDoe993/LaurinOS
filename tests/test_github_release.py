"""Release publication safeguards with a fake GitHub CLI; no external writes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('github_release', ROOT / '.github/scripts/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class FakeGitHub:
    def __init__(self, root):
        self.root, self.calls = root, []
        self.reference = None
        self.release = None
        self.auth_error = False
        self.incomplete = False
    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[0] == 'git':
            return subprocess.CompletedProcess(command, 0, stdout='a' * 40 + '\n')
        if command[:2] == ['gh', 'api']:
            if self.auth_error:
                return subprocess.CompletedProcess(command, 1, stdout='', stderr='gh: Forbidden (HTTP 403)')
            endpoint = command[2]
            if '/git/ref/' in endpoint: payload = self.reference
            elif '/git/tags/' in endpoint: payload = {'object': {'type': 'commit', 'sha': 'a' * 40}}
            elif '/releases?' in endpoint:
                payload = [dict(self.release, tag_name='v0.63.0')] if self.release else []
            else: raise AssertionError(endpoint)
            if payload is None:
                return subprocess.CompletedProcess(command, 1, stdout='', stderr='gh: Not Found (HTTP 404)')
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr='')
        if command[:2] != ['gh', 'release']:
            raise AssertionError(command)
        if command[2] == 'create':
            self.release = {'draft': '--draft' in command, 'assets': [], 'html_url': 'https://github.com/test/repo/releases/tag/v0.63.0'}
        if command[2] == 'edit':
            return subprocess.CompletedProcess(command, 0)
        for path in (self.root / 'dist').iterdir():
            if not self.incomplete or path.suffix == '.zip':
                self.release['assets'].append({'name': path.name, 'state': 'uploaded', 'size': path.stat().st_size})
        return subprocess.CompletedProcess(command, 0)


class GitHubReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        (self.root / 'src/laurinos').mkdir(parents=True)
        (self.root / 'VERSION').write_text('0.63.0\n')
        (self.root / 'src/laurinos/__init__.py').write_text('__version__ = "0.63.0"\n')
        (self.root / 'manifest.json').write_text('{"version":"0.63.0"}')
        (self.root / 'pyproject.toml').write_text('[tool.laurinos]\nversion="0.63.0"\n')
        (self.root / 'dist').mkdir()
        self.archive = self.root / 'dist/LaurinOS-0.63.0.zip'
        with zipfile.ZipFile(self.archive, 'w') as package:
            package.writestr('LaurinOS/VERSION', '0.63.0\n')
        self.checksum = self.archive.with_suffix('.zip.sha256')
        self.checksum.write_text(hashlib.sha256(self.archive.read_bytes()).hexdigest() + '  ' + self.archive.name + '\n')
        self.github = FakeGitHub(self.root)
    def tearDown(self): self.temp.cleanup()
    def prepare(self): return release.prepare(self.root, 'v0.63.0', 'test/repo', self.github)
    def writes(self): return [call for call in self.github.calls if call[:2] == ['gh', 'release']]
    def test_new_release_attaches_both_assets_as_draft_at_built_commit(self):
        self.assertIn('/v0.63.0', self.prepare())
        command = self.writes()[0]
        self.assertEqual(command[:4], ['gh', 'release', 'create', 'v0.63.0'])
        self.assertIn('--draft', command)
        self.assertEqual(command[command.index('--target') + 1], 'a' * 40)
        self.assertIn(str(self.archive), command)
        self.assertIn(str(self.checksum), command)
        self.assertTrue(self.github.release['draft'])
    def test_empty_existing_draft_is_uploaded_without_replacing_notes(self):
        self.github.release = {'draft': True, 'assets': [], 'html_url': 'https://github.com/test/draft'}
        self.github.reference = {'object': {'type': 'commit', 'sha': 'a' * 40}}
        self.prepare()
        self.assertEqual(self.writes()[0][:3], ['gh', 'release', 'upload'])
        self.assertNotIn('--clobber', self.writes()[0])
    def test_ui_draft_without_a_tag_is_pinned_before_upload(self):
        self.github.release = {'draft': True, 'assets': [], 'html_url': 'https://github.com/test/draft'}
        self.prepare()
        command = self.writes()[0]
        self.assertEqual(command[:3], ['gh', 'release', 'edit'])
        self.assertEqual(command[command.index('--target') + 1], 'a' * 40)
        self.assertEqual(self.writes()[1][:3], ['gh', 'release', 'upload'])
    def test_published_release_and_colliding_draft_assets_are_never_modified(self):
        for draft, assets in [(False, []), (True, [{'name': self.archive.name}])]:
            with self.subTest(draft=draft):
                self.github.release = {'draft': draft, 'assets': assets}
                with self.assertRaises(ValueError): self.prepare()
                self.assertEqual(self.writes(), [])
    def test_tag_cannot_move_to_another_commit_and_annotated_tags_are_resolved(self):
        self.github.reference = {'object': {'type': 'commit', 'sha': 'b' * 40}}
        with self.assertRaisesRegex(ValueError, 'gebauten Commit'): self.prepare()
        self.assertEqual(self.writes(), [])
        self.github.reference = {'object': {'type': 'tag', 'sha': 'c' * 40}}
        self.prepare()
        self.assertTrue(any('/git/tags/' in command[-1] for command in self.github.calls))
    def test_bad_checksum_refuses_upload_before_any_git_or_github_command(self):
        self.checksum.write_text('0' * 64 + '  ' + self.archive.name + '\n')
        with self.assertRaisesRegex(ValueError, 'SHA-256'): self.prepare()
        self.assertEqual(self.github.calls, [])
    def test_tag_and_all_project_version_files_must_match(self):
        for tag in ('v0.62.0', '0.63.0', 'v0.63.0-beta', 'v0.63.0;echo bad'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.checked_version(self.root, tag)
        for path in ['manifest.json', 'pyproject.toml', 'src/laurinos/__init__.py']:
            file = self.root / path; original = file.read_text()
            file.write_text(original.replace('0.63.0', '0.64.0'))
            with self.subTest(path=path), self.assertRaises(ValueError): self.prepare()
            file.write_text(original)
        self.assertEqual(self.github.calls, [])
    def test_permission_errors_are_not_mistaken_for_a_missing_release(self):
        self.github.auth_error = True
        with self.assertRaisesRegex(ValueError, '403'): self.prepare()
        self.assertEqual(self.writes(), [])
    def test_incomplete_upload_never_reports_success(self):
        self.github.incomplete = True
        with self.assertRaisesRegex(ValueError, 'nicht vollständig'): self.prepare()
        self.assertTrue(self.github.release['draft'])


class WorkflowSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        workflow = (ROOT / '.github/workflows/release.yml').read_text()
        step = workflow.split('      - name: Versionsdateien prüfen\n', 1)[1].split('      - name:', 1)[0]
        self.code = textwrap.dedent(step.split("python3 - <<'PY'\n", 1)[1].rsplit('          PY', 1)[0])
    def tearDown(self): self.temp.cleanup()
    def check(self, tag):
        return subprocess.run([sys.executable, '-c', self.code], cwd=self.root,
                              env=dict(os.environ, RELEASE_TAG=tag), capture_output=True, text=True)
    def test_actual_failed_tag_reports_its_old_version_before_missing_helper(self):
        (self.root / 'VERSION').write_text('0.62.0\n')
        result = self.check('v0.63.0')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('v0.63.0', result.stderr)
        self.assertIn('Projektversion 0.62.0', result.stderr)
        self.assertIn('vorhandener Tag', result.stderr)
        self.assertNotIn("can't open file", result.stderr)
    def test_matching_tag_without_helper_has_an_actionable_error(self):
        (self.root / 'VERSION').write_text('0.63.1\n')
        result = self.check('v0.63.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fehlt der Release-Helfer', result.stderr)
    def test_correct_checkout_runs_real_release_version_validation(self):
        (self.root / '.github/scripts').mkdir(parents=True)
        (self.root / 'src/laurinos').mkdir(parents=True)
        for path in ['VERSION', 'manifest.json', 'pyproject.toml', 'src/laurinos/__init__.py', '.github/scripts/release.py']:
            (self.root / path).write_bytes((ROOT / path).read_bytes())
        version = (ROOT / 'VERSION').read_text().strip()
        result = self.check('v' + version)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OK: Version ' + version, result.stdout)


if __name__ == '__main__': unittest.main()
