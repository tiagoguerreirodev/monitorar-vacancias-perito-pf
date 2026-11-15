"""Executable publication boundaries for the prospective UF archive (offline)."""
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from perito_dashboard import refresh_and_build
from tests.sources import ControlledArchive
from tests.test_uf import ExportSource, NOW
from tests.test_uf_history import counterfactual
from tests import test_workflows as workflow_harness
from tests.uf_runtime import install_offline_runtime

ROOT = Path(__file__).resolve().parents[1]


class UFHistoryDeliveryTests(unittest.TestCase):
    def test_persist_commits_exact_five_accepted_files_not_unrelated_work(self):
        harness = workflow_harness.GitPersistenceTests('test_unvalidated_local_commit_cannot_be_pushed')
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        for name in ('history.json', 'status.json'):
            (harness.repo / 'data' / name).unlink()  # harness placeholders are not application state
        refresh_and_build(harness.repo / 'data', harness.repo / 'site',
                          source=ControlledArchive(), uf_source=ExportSource(), clock=lambda: NOW)
        (harness.repo / 'README.md').write_text('not accepted\n')
        (harness.repo / 'data/not-accepted.json').write_text('{}\n')
        result = harness.persist()  # local bare Git remote; no network or real token
        self.assertEqual(result.returncode, 0, result.stderr)
        names = harness.git(harness.repo, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').stdout.splitlines()
        self.assertEqual(names, ['data/history.json', 'data/status.json', 'data/uf-history.json',
                                'data/uf-status.json', 'data/uf.json'])
        self.assertEqual(harness.git(harness.repo, 'show', 'HEAD:README.md').stdout, 'unrelated source\n')
        self.assertIn('README.md', harness.git(harness.repo, 'status', '--porcelain').stdout)
        self.assertEqual(harness.git(harness.repo, 'show', 'HEAD:data/uf-history.json').stdout,
                         (harness.repo / 'site/data/uf-history.json').read_text())

    def test_actual_pair_collector_rejects_later_bad_export_without_partial_UF_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, site = root / 'data', root / 'site'
            refresh_and_build(data, site, source=ControlledArchive(), uf_source=ExportSource(), clock=lambda: NOW)
            before = {n: ((data / n).read_bytes(), (data / n).stat().st_mode)
                      for n in ('uf.json', 'uf-status.json', 'uf-history.json')}
            good = counterfactual('2026-10')
            (root / 'good.xlsx').write_bytes(good.content)
            (root / 'good.json').write_text(json.dumps(good.evidence))
            (root / 'bad.xlsx').write_bytes(b'not an XLSX')
            env = install_offline_runtime(root, [
                {'workbook': str(root / 'good.xlsx'), 'evidence': str(root / 'good.json')},
                {'workbook': str(root / 'bad.xlsx'), 'evidence': str(root / 'good.json')}])
            with patch.dict(os.environ, env):
                result = refresh_and_build(data, site, source=ControlledArchive(), clock=lambda: NOW + timedelta(days=1))
            self.assertEqual(result['uf'], 'failed')
            self.assertEqual(result['publication'], 'partial')
            for name, (content, mode) in before.items():
                self.assertEqual((data / name).read_bytes(), content)
                self.assertEqual((data / name).stat().st_mode, mode)
                self.assertEqual((site / 'data' / name).read_bytes(), content)

    def test_cli_builds_archive_using_real_pair_collector_and_controlled_HTTP(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = ROOT / 'tests/fixtures/uf'
            env = install_offline_runtime(root, [
                {'workbook': str(fixture / 'run-6.xlsx'), 'evidence': str(fixture / 'run-6.json')},
                {'workbook': str(fixture / 'run-7.xlsx'), 'evidence': str(fixture / 'run-7.json')}])
            program = '''
import io, runpy, sys
from urllib.request import urlopen as real_open
from unittest.mock import patch
from tests.sources import ControlledArchive, ARCHIVE_URL
source = ControlledArchive()
def response(url, **kwargs):
    if not isinstance(url, str) and url.full_url.startswith('http://127.0.0.1:'):
        return real_open(url, **kwargs)  # owned offline runtime control, never Gov
    if url == ARCHIVE_URL:
        return io.BytesIO(source.archive_index().encode())
    if url == ARCHIVE_URL + '2026/':
        return io.BytesIO(source.year_index('2026').encode())
    return io.BytesIO(source.spreadsheet(url))
sys.argv = ['perito_dashboard', '--data-dir', sys.argv[1], '--site-dir', sys.argv[2]]
with patch('urllib.request.urlopen', side_effect=response):
    runpy.run_module('perito_dashboard', run_name='__main__')
'''
            result = subprocess.run([sys.executable, '-c', program, str(root / 'data'), str(root / 'site')],
                cwd=ROOT, env={**os.environ, **env}, capture_output=True, text=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('publication=complete', result.stdout)
            data = root / 'data/uf-history.json'
            self.assertEqual(data.read_bytes(), (root / 'site/data/uf-history.json').read_bytes())
            archive = json.loads(data.read_text())
            self.assertEqual(archive['coverage']['available_months'], ['2026-09'])
            self.assertEqual(archive['observations'][0]['counts_by_uf']['DF'], 324)
            self.assertEqual(archive['observations'][0]['total'], 1108)
