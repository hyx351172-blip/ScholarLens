import tempfile
import unittest
from pathlib import Path

from scripts.replay_docling_table_export import replay


class ReplayTableExportTests(unittest.TestCase):
    def test_replay_cannot_overwrite_or_write_inside_source(self):
        """AC-TABLE-705: experiment evidence is never overwritten in place."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            existing = Path(tmp) / "existing"
            existing.mkdir()
            sentinel = existing / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            for output in (source, source / "nested", existing):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    replay(source, output)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_preflight_rejects_incomplete_artifacts_before_creating_output(self):
        """AC-TABLE-704/705: missing native source must not fabricate a replay."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            artifact = source / "artifacts" / "page"
            artifact.mkdir(parents=True)
            (artifact / "document.json").write_text("{}", encoding="utf-8")
            output = Path(tmp) / "output"
            with self.assertRaisesRegex(ValueError, "Missing native JSON or PDF"):
                replay(source, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
