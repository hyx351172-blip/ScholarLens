import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from experiment_table_grid_binding import fresh_output, verify_hashes, png_size, verify_run
from audit_table_decoder import sha, write


class GridReplayContracts(unittest.TestCase):
    def test_overlap_and_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'input'; source.mkdir()
            for output in (root, source, source / 'child'):
                with self.subTest(output=output), self.assertRaises(ValueError): fresh_output(output, [source])
            fresh_output(root / 'new', [source])

    def test_changed_input_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'source'; p.write_text('frozen')
            hashes = {str(p): sha(p)}; verify_hashes(hashes)
            p.write_text('changed')
            with self.assertRaises(ValueError): verify_hashes(hashes)

    def test_png_header_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'crop.png'; p.write_bytes(b'not a PNG' * 4)
            with self.assertRaises(ValueError): png_size(p)

    def test_result_tampering_detected_before_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); p = root / 'trace.json'; write(p, {'gate': False})
            summary = {'protected_inputs_unchanged': True, 'protected_hashes': {},
                       'artifact_sha256': {'trace.json': sha(p)}}
            verify_run(root, summary)
            write(p, {'gate': True})
            with self.assertRaises(ValueError): verify_run(root, summary)

    def test_output_artifact_path_escape_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = {'protected_inputs_unchanged': True, 'protected_hashes': {},
                       'artifact_sha256': {'../outside': 'fake'}}
            with self.assertRaises(ValueError): verify_run(Path(tmp), summary)


if __name__ == '__main__': unittest.main()
