import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install_release import install_support


class ReleaseInstallationTests(unittest.TestCase):
    def test_update_backs_up_owned_files_and_preserves_companion_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            services = root / 'Services'
            support = services / 'Service Tools'
            old_app = support / 'Service Tools.app'
            old_app.mkdir(parents=True)
            (old_app / 'old').write_text('old app')
            workers = support / 'Workers'
            workers.mkdir()
            (workers / 'worker.py').write_text('old worker')
            (workers / 'custom.py').write_text('user worker')
            extra = support / 'PDF Image Tools'
            extra.mkdir()
            (extra / 'helper').write_text('user helper')
            source_app = root / 'release' / 'Service Tools.app'
            source_app.mkdir(parents=True)
            (source_app / 'new').write_text('new app')
            source_workers = root / 'release' / 'Workers'
            source_workers.mkdir()
            (source_workers / 'worker.py').write_text('new worker')
            with patch('install_release.subprocess.run'):
                backup = install_support(source_app, source_workers, [], services)
            self.assertEqual((backup / 'Service Tools/Service Tools.app/old').read_text(), 'old app')
            self.assertEqual((backup / 'Service Tools/Workers/worker.py').read_text(), 'old worker')
            self.assertEqual((workers / 'worker.py').read_text(), 'new worker')
            self.assertEqual((workers / 'custom.py').read_text(), 'user worker')
            self.assertEqual((extra / 'helper').read_text(), 'user helper')
            self.assertFalse((old_app / 'old').exists())
            self.assertEqual((old_app / 'new').read_text(), 'new app')


if __name__ == '__main__':
    unittest.main()
