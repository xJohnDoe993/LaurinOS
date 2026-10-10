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
from unittest import mock
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
        self.ignore_publish = False
        self.publish_sha = 'a' * 40
        self.listing_delay = 0
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
            elif '/releases?' in endpoint and self.listing_delay:
                self.listing_delay -= 1
                payload = []
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
            if '--draft=false' in command and not self.ignore_publish:
                self.release['draft'] = False
                self.release['prerelease'] = False
                self.release['body'] = Path(command[command.index('--notes-file') + 1]).read_text()
                if self.reference is None:
                    self.reference = {'object': {'type': 'commit', 'sha': self.publish_sha}}
            return subprocess.CompletedProcess(command, 0)
        for path in (self.root / 'dist').iterdir():
            if not self.incomplete or path.suffix == '.zip':
                self.release['assets'].append({'name': path.name, 'state': 'uploaded', 'size': path.stat().st_size})
        return subprocess.CompletedProcess(command, 0)


class GitHubReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.root = Path(self.temp.name)
        (self.root / 'src/paimenos').mkdir(parents=True)
        (self.root / 'VERSION').write_text('0.63.0\n')
        (self.root / 'src/paimenos/__init__.py').write_text('__version__ = "0.63.0"\n')
        (self.root / 'manifest.json').write_text('{"version":"0.63.0"}')
        (self.root / 'pyproject.toml').write_text('[tool.paimenos]\nversion="0.63.0"\n')
        (self.root / 'docs/releases').mkdir(parents=True)
        self.notes = self.root / 'docs/releases/0.63.0.md'
        self.notes.write_text('## Release\n\nSecurity fix and update instructions.\n')
        (self.root / 'dist').mkdir()
        self.archive = self.root / 'dist/PaimenOS-0.63.0.zip'
        with zipfile.ZipFile(self.archive, 'w') as package:
            package.writestr('PaimenOS/VERSION', '0.63.0\n')
        self.checksum = self.archive.with_suffix('.zip.sha256')
        self.checksum.write_text(hashlib.sha256(self.archive.read_bytes()).hexdigest() + '  ' + self.archive.name + '\n')
        self.github = FakeGitHub(self.root)
    def tearDown(self): self.temp.cleanup()
    def prepare(self, *, publish=False):
        self.sleeps = []
        return release.prepare(self.root, 'v0.63.0', 'test/repo', self.github, publish=publish,
                               sleep=self.sleeps.append)
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
    def test_new_draft_listed_with_delay_is_awaited(self):
        # Erste Abfrage vor dem Anlegen, zwei weitere ohne den neuen Entwurf.
        self.github.listing_delay = 3
        self.assertIn('/v0.63.0', self.prepare())
        self.assertEqual(self.sleeps, [3, 3])
        self.github.listing_delay = 99
        self.github.release = None
        with self.assertRaisesRegex(ValueError, 'nicht gefunden'): self.prepare()
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
        for path in ['manifest.json', 'pyproject.toml', 'src/paimenos/__init__.py']:
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

    def test_explicit_publication_uses_notes_and_verified_assets_at_built_commit(self):
        self.assertIn('/v0.63.0', self.prepare(publish=True))
        self.assertEqual([call[2] for call in self.writes()], ['create', 'edit'])
        command = self.writes()[-1]
        self.assertIn('--draft=false', command)
        self.assertIn('--prerelease=false', command)
        self.assertIn('--latest', command)
        self.assertEqual(command[command.index('--target') + 1], 'a' * 40)
        self.assertEqual(self.github.release['body'], self.notes.read_text())
        self.assertFalse(self.github.release['draft'])
        self.assertEqual({asset['name'] for asset in self.github.release['assets']},
                         {self.archive.name, self.checksum.name})
        self.assertEqual(self.github.reference['object']['sha'], 'a' * 40)

    def test_publication_requires_nonempty_notes_before_any_github_operation(self):
        self.notes.write_text(' \n')
        with self.assertRaisesRegex(ValueError, 'Release-Notizen'): self.prepare(publish=True)
        self.notes.unlink()
        with self.assertRaisesRegex(ValueError, 'Release-Notizen'): self.prepare(publish=True)
        self.assertEqual(self.github.calls, [])

    def test_publication_does_not_follow_an_incomplete_upload(self):
        self.github.incomplete = True
        with self.assertRaisesRegex(ValueError, 'nicht vollständig'): self.prepare(publish=True)
        self.assertTrue(self.github.release['draft'])
        self.assertFalse(any('--draft=false' in call for call in self.writes()))

    def test_publication_must_be_confirmed_as_stable(self):
        self.github.ignore_publish = True
        with self.assertRaisesRegex(ValueError, 'nicht bestätigt'): self.prepare(publish=True)

    def test_published_tag_is_checked_again_against_built_commit(self):
        self.github.publish_sha = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'gebauten Commit'): self.prepare(publish=True)

    def test_explicit_publication_cannot_modify_an_existing_published_release(self):
        self.github.release = {'draft': False, 'assets': []}
        with self.assertRaisesRegex(ValueError, 'bereits veröffentlicht'): self.prepare(publish=True)
        self.assertEqual(self.writes(), [])


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
        (self.root / 'src/paimenos').mkdir(parents=True)
        for path in ['VERSION', 'manifest.json', 'pyproject.toml', 'src/paimenos/__init__.py', '.github/scripts/release.py']:
            (self.root / path).write_bytes((ROOT / path).read_bytes())
        version = (ROOT / 'VERSION').read_text().strip()
        result = self.check('v' + version)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OK: Version ' + version, result.stdout)


class WorkflowCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.output = Path(self.temp.name) / 'output'
        workflow = (ROOT / '.github/workflows/release.yml').read_text()
        step = workflow.split("python3 - <<'PY'\n", 1)[1].split('          PY', 1)[0]
        self.code = textwrap.dedent(step)

    def tearDown(self): self.temp.cleanup()

    def checkout(self, tag, event='workflow_dispatch', ref='refs/heads/main', exists=False):
        entries = [{'ref': 'refs/tags/v0.65.0'}] if exists else []
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps(entries))
        environment = dict(RELEASE_TAG=tag, SOURCE_SHA='a' * 40, GH_REPO='test/repo',
                           GITHUB_OUTPUT=str(self.output), GITHUB_EVENT_NAME=event, GITHUB_REF=ref)
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(subprocess, 'run', return_value=result):
            exec(compile(self.code, '<release workflow>', 'exec'), {})
        return dict(line.split('=', 1) for line in self.output.read_text().splitlines())

    def test_manual_run_defaults_to_draft_and_selected_commit(self):
        self.assertEqual(self.checkout('v0.65.0'),
                         {'tag': 'v0.65.0', 'ref': 'a' * 40, 'publish': 'false'})

    def test_tag_run_uses_original_tag_and_remains_a_draft(self):
        output = self.checkout('v0.65.0', 'push', 'refs/tags/v0.65.0', exists=True)
        self.assertEqual(output['ref'], 'refs/tags/v0.65.0')
        self.assertEqual(output['publish'], 'false')

    def test_only_release_branch_push_opts_into_publication(self):
        self.assertEqual(self.checkout('release/v0.65.0', 'push', 'refs/heads/release/v0.65.0'),
                         {'tag': 'v0.65.0', 'ref': 'a' * 40, 'publish': 'true'})
        self.output.unlink()
        output = self.checkout('v0.65.0', 'workflow_dispatch', 'refs/heads/release/v0.65.0')
        self.assertEqual(output['publish'], 'false')

    def test_release_branch_ref_and_version_must_match(self):
        with self.assertRaises(SystemExit):
            self.checkout('release/v0.65.1', 'push', 'refs/heads/release/v0.65.0')
        self.assertFalse(self.output.exists())

    def test_release_branch_cannot_republish_an_existing_tag(self):
        with self.assertRaisesRegex(SystemExit, 'neuen Tag'):
            self.checkout('release/v0.65.0', 'push', 'refs/heads/release/v0.65.0', exists=True)
        self.assertFalse(self.output.exists())

    def test_invalid_tags_are_rejected_before_checkout(self):
        for tag in ('v0.65', 'v0.65.0-beta', 'v0.65.0;echo bad'):
            with self.subTest(tag=tag), self.assertRaises(SystemExit): self.checkout(tag)
        self.assertFalse(self.output.exists())


if __name__ == '__main__': unittest.main()
