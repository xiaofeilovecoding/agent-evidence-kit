"""Reject unsafe or incomplete release payloads before installation."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_distribution import inspect_archives, validate_member


class DistributionBoundary(unittest.TestCase):
    def test_parent_traversal_rejected(self):
        with self.assertRaises(ValueError):
            validate_member("package/../secret")

    def test_absolute_path_rejected(self):
        for name in ("/etc/passwd", "C:/Users/secret", "package\\secret"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_member(name)

    def test_environment_files_rejected(self):
        for name in (".env", "package/.env.production", "frontend/.env.showcase"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_member(name)

    def test_only_source_showcase_configuration_allowed(self):
        validate_member("agent-evidence-kit/frontend/.env.showcase", source=True)
        with self.assertRaises(ValueError):
            validate_member("package/.env.showcase", source=True)

    def test_internal_files_rejected(self):
        for name in ("package/reports/review.md", "package/node_modules/a.js",
                     "package/.git/config", "package/artifacts/key.txt"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_member(name, source=True)

    def test_generated_files_rejected(self):
        for name in ("package/a.pyc", "package/run.log"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_member(name)

    def test_normal_package_files_allowed(self):
        validate_member("agent_evidence_kit/_web_static/assets/index.js")
        validate_member("agent_evidence_kit-0.2.0.dist-info/licenses/LICENSE")

    def test_incomplete_wheel_rejected_before_install(self):
        with tempfile.TemporaryDirectory(prefix="aek-test-archive-") as directory:
            root = Path(directory).resolve()
            self.assertEqual(root.parent, Path(tempfile.gettempdir()).resolve())
            wheel = root / "incomplete.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("a.dist-info/METADATA", "Name: agent-evidence-kit\nVersion: 0.2.0\n")
            with self.assertRaisesRegex(ValueError, "web assets"):
                inspect_archives(wheel, root / "unused.tar.gz")
