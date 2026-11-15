"""Accepted download bytes and permissions through the complete refresh seam."""
from datetime import timedelta
import json
from pathlib import Path
import stat
import tempfile
import unittest

from perito_dashboard import refresh_and_build
from tests.sources import ControlledArchive, UnavailableUF
from tests.test_uf import ExportSource, NOW, UnavailableNational


UF_FILES = ('uf.json', 'uf-status.json', 'uf-history.json')
NATIONAL_FILES = ('history.json', 'status.json')


class AcceptedPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data, self.site = self.root / 'data', self.root / 'site'

    def refresh(self, *, national=None, uf=None, day=0):
        return refresh_and_build(
            self.data, self.site,
            source=national if national is not None else ControlledArchive(),
            uf_source=uf if uf is not None else ExportSource(),
            clock=lambda: NOW + timedelta(days=day),
        )

    def make_noncanonical(self, names):
        """Change only external saved-file encoding and location-specific modes."""
        snapshots = {}
        for name in names:
            saved = self.data / name
            public = self.site / 'data' / name
            original = saved.read_bytes()
            raw = (json.dumps(json.loads(original), ensure_ascii=False,
                              indent='\t', sort_keys=True) + '\n\n').encode('utf-8')
            self.assertNotEqual(raw, original)
            for path, mode in ((saved, 0o640), (public, 0o600)):
                path.write_bytes(raw)
                path.chmod(mode)
            snapshots[name] = raw
        return snapshots

    def output_state(self):
        return {
            str(path.relative_to(self.root)): (
                path.read_bytes() if path.is_file() else None,
                stat.S_IMODE(path.stat().st_mode),
            )
            for root in (self.data, self.site)
            for path in (root, *root.rglob('*'))
            if path.exists()
        }

    def test_failed_uf_retains_noncanonical_bytes_and_separate_public_modes(self):
        self.refresh()
        snapshots = self.make_noncanonical(UF_FILES)

        result = self.refresh(uf=UnavailableUF(), day=1)

        self.assertEqual(result, {
            'national': 'unchanged', 'uf': 'failed', 'publication': 'partial',
        })
        for name, raw in snapshots.items():
            for path, mode in ((self.data / name, 0o640),
                               (self.site / 'data' / name, 0o600)):
                self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)

    def test_failed_national_retains_noncanonical_bytes_and_saved_mode_policy(self):
        self.refresh()
        snapshots = self.make_noncanonical(NATIONAL_FILES)

        result = self.refresh(national=UnavailableNational(), day=1)

        self.assertEqual(result, {
            'national': 'failed', 'uf': 'unchanged', 'publication': 'partial',
        })
        for name, raw in snapshots.items():
            for path in (self.data / name, self.site / 'data' / name):
                self.assertEqual(path.read_bytes(), raw)
                # National public copies inherit saved-file modes; unlike failed UF.
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_failed_uf_missing_or_mismatched_public_copy_preserves_existing_policy(self):
        for missing in (True, False):
            with self.subTest(missing=missing):
                # Each case starts with a genuine, independently accepted document set.
                with tempfile.TemporaryDirectory(dir=self.root) as directory:
                    self.data = Path(directory) / 'data'
                    self.site = Path(directory) / 'site'
                    self.refresh()
                    snapshots = self.make_noncanonical(UF_FILES)
                    if missing:
                        for name in UF_FILES:
                            (self.site / 'data' / name).unlink()
                        result = self.refresh(uf=UnavailableUF(), day=1)
                        self.assertEqual(result['publication'], 'partial')
                        self.assertEqual(result['uf'], 'failed')
                        for name, raw in snapshots.items():
                            public = self.site / 'data' / name
                            self.assertEqual(public.read_bytes(), raw)
                            self.assertEqual(stat.S_IMODE(public.stat().st_mode), 0o640)
                    else:
                        public = self.site / 'data' / 'uf-history.json'
                        public.write_bytes(public.read_bytes() + b' ')
                        before = self.output_state()
                        with self.assertRaisesRegex(
                            ValueError, 'Saved public UF copy differs from accepted data',
                        ):
                            self.refresh(uf=UnavailableUF(), day=1)
                        self.assertEqual(self.output_state(), before)


if __name__ == '__main__':
    unittest.main()
