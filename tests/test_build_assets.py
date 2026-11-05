"""A package must not silently ship an obsolete frontend bundle."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_frontend import check_assets


class AssetParity(unittest.TestCase):
    def test_matching_changed_and_extra_asset(self):
        with tempfile.TemporaryDirectory(prefix="aek-assets-") as directory:
            root = Path(directory).resolve()
            self.assertEqual(root.parent, Path(tempfile.gettempdir()).resolve())
            dist, packaged = root / "dist", root / "package"
            dist.mkdir()
            packaged.mkdir()
            for path in (dist, packaged):
                (path / "index.html").write_bytes(b"<script src='/current.js'></script>")
                (path / "current.js").write_bytes(b"current")
            self.assertTrue(check_assets(dist, packaged))
            (packaged / "current.js").write_bytes(b"old bytes, same filename")
            self.assertFalse(check_assets(dist, packaged))
            (packaged / "current.js").write_bytes(b"current")
            (packaged / "obsolete.js").write_bytes(b"old hashed asset")
            self.assertFalse(check_assets(dist, packaged))

    def test_missing_build_cannot_pass_as_two_empty_directories(self):
        with tempfile.TemporaryDirectory(prefix="aek-assets-") as directory:
            root = Path(directory).resolve()
            self.assertEqual(root.parent, Path(tempfile.gettempdir()).resolve())
            self.assertFalse(check_assets(root / "missing", root / "also-missing"))
