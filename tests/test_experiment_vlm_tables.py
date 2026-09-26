import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from scripts.experiment_vlm_tables import (
    PROMPT, crop_box, validate_candidate, prepare, run_experiment, fresh_output, TableVLMClient,
)


def candidate():
    return {"rows": 2, "cols": 2, "cells": [
        [0, 0, 1, 2, "<Header>", True, False],
        [1, 0, 1, 1, "0.18", False, False],
        [1, 1, 1, 1, None, False, True],
    ]}


class VLMTableExperimentTests(unittest.TestCase):
    def test_coordinates_origins_scaling_and_clipping(self):
        """AC-VTABLE-801: native origins are explicit, never guessed."""
        b = {"l": 10, "t": 90, "r": 190, "b": 10, "coord_origin": "BOTTOMLEFT"}
        self.assertEqual(crop_box(b, (200, 100), (400, 200), 0), (20, 20, 380, 180))
        b.update(t=10, b=90, coord_origin="TOPLEFT")
        self.assertEqual(crop_box(b, (200, 100), (400, 200), 30), (0, 0, 400, 200))
        for changes in ({"l": float("nan")}, {"r": 0}, {"coord_origin": "unknown"}):
            with self.assertRaises(ValueError):
                crop_box({**b, **changes}, (200, 100), (400, 200))

    def test_strict_cells_uncertainty_and_safe_html(self):
        """AC-VTABLE-802/806: null is uncertainty, not a guessed number."""
        structure, rendered = validate_candidate(json.dumps(candidate()))
        self.assertEqual(structure["uncertain_cells"], [[1, 1]])
        self.assertIn('&lt;Header&gt;', rendered)
        self.assertIn('colspan="2"', rendered)
        self.assertIn('[UNCERTAIN]', rendered)
        self.assertEqual(structure["source"], "vlm_experiment")

    def test_invalid_candidate_is_not_silently_fixed(self):
        """AC-VTABLE-802: overlap, holes, invalid text and budget reject."""
        cases = []
        for index, value in ((0, -1), (2, 0), (3, 3), (4, 0.18), (5, 1), (6, "no")):
            data = candidate()
            data["cells"][1][index] = value
            cases.append(data)
        data = candidate(); data["cells"].pop(); cases.append(data)
        data = candidate(); data["cells"].append(data["cells"][1]); cases.append(data)
        data = candidate(); data["cells"][2][6] = False; cases.append(data)
        data = candidate(); data["rows"] = True; cases.append(data)
        data = candidate(); data["rows"] = 100001; cases.append(data)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_candidate(json.dumps(data))
        with self.assertRaises(ValueError):
            validate_candidate('{"rows":2')

    def fixture(self, root):
        source, images = root / "source", root / "images"
        art = source / "artifacts/page-fixture"
        art.mkdir(parents=True); images.mkdir()
        Image.new("RGB", (200, 100), "white").save(images / "page-fixture.png")
        structure, _ = validate_candidate(json.dumps(candidate()))
        (art / "document.json").write_text(json.dumps({"filename": "page-fixture.png", "blocks": [
            {"type": "table", "block_id": "b1", "table_structure": {
                **structure, "source_ref": "#/tables/0"}}]}), encoding="utf-8")
        (art / "docling-document.json").write_text(json.dumps({
            "pages": {"1": {"size": {"width": 200, "height": 100}}},
            "tables": [{"self_ref": "#/tables/0", "prov": [{"page_no": 1,
                "bbox": {"l": 10, "t": 90, "r": 190, "b": 10, "coord_origin": "BOTTOMLEFT"}}]}],
        }), encoding="utf-8")
        return source, images

    def test_prepare_run_preserves_inputs_and_records_usage(self):
        """AC-VTABLE-803/804: real image seam with fake network; no gold input."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, images = self.fixture(root)
            before = {p: p.read_bytes() for p in source.rglob('*.json')}
            prep = prepare(source, images, root / "prepared", ["page-fixture.png"])
            calls = []
            def client(crop):
                calls.append(crop)
                return {"content": json.dumps(candidate()), "finish_reason": "stop", "model": "fake",
                        "usage": {"prompt_tokens": 10, "completion_tokens": 20}}
            report = run_experiment(root / "prepared", root / "run", client)
            self.assertEqual(len(calls), 1)
            self.assertEqual(report["results"][0]["status"], "valid_candidate_review_required")
            self.assertEqual(report["results"][0]["usage"]["completion_tokens"], 20)
            self.assertEqual(prep["gold_access"], False)
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            self.assertTrue((root / "prepared/page-fixture/native-overlay.png").is_file())
            with self.assertRaises(ValueError):
                run_experiment(root / "prepared", root / "run", client)
            self.assertEqual(len(calls), 1)

    def test_failure_truncation_and_budget_keep_baseline_without_retry(self):
        """AC-VTABLE-803: secret-bearing errors never persisted; failed call counts."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, images = self.fixture(root)
            prepare(source, images, root / "prepared", ["page-fixture.png"])
            calls = []
            def broken(crop):
                calls.append(crop)
                raise TimeoutError("secret-key-must-not-be-written")
            report = run_experiment(root / "prepared", root / "failure", broken)
            self.assertEqual(report["calls_attempted"], 1)
            self.assertEqual(report["results"][0]["status"], "request_failed_baseline_retained")
            self.assertNotIn("secret-key", (root / "failure/summary.json").read_text())
            def truncated(crop):
                return {"content": json.dumps(candidate()), "finish_reason": "length"}
            report = run_experiment(root / "prepared", root / "truncated", truncated)
            self.assertEqual(report["results"][0]["status"], "invalid_candidate_baseline_retained")
            report = run_experiment(root / "prepared", root / "no-budget", broken, max_calls=0)
            self.assertEqual(report["calls_attempted"], 0)
            self.assertEqual(len(calls), 1)

    def test_isolation_tampering_and_path_traversal(self):
        """AC-VTABLE-804: protect originals, refuse tampered cropped inputs."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, images = self.fixture(root)
            for path in (source, source / "output", root):
                with self.assertRaises(ValueError):
                    fresh_output(path, [source])
            with self.assertRaises(ValueError):
                prepare(source, images, root / "bad", ["../page.png"])
            prepare(source, images, root / "prepared", ["page-fixture.png"])
            (root / "prepared/page-fixture/crop.png").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                run_experiment(root / "prepared", root / "run", lambda _: self.fail("No request allowed"))

    def test_real_client_contract_has_bounded_cost_and_image_only_input(self):
        """AC-VTABLE-803/804: inspect actual SDK seam without network/real key."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf = root / '.env'
            conf.write_text('VLM_REPAIR_API_KEY=test-not-a-real-key\nVLM_REPAIR_MODEL_NAME=fake-vlm\nVLM_REPAIR_BASE_URL=https://example.test/v1\n')
            crop = root / 'crop.png'; Image.new('RGB', (20, 20)).save(crop)
            with patch('openai.OpenAI') as sdk:
                sdk.return_value.chat.completions.create.return_value = SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(candidate())), finish_reason='stop')],
                    usage=SimpleNamespace(model_dump=lambda: {'total_tokens': 30}), model='fake-vlm', id='request-test')
                result = TableVLMClient(conf)(crop)
                self.assertEqual(sdk.call_args.kwargs['max_retries'], 0)
                self.assertEqual(sdk.call_args.kwargs['timeout'], 180)
                args = sdk.return_value.chat.completions.create.call_args.kwargs
                self.assertEqual(args['max_tokens'], 16384)
                self.assertEqual(args['messages'][0]['content'], PROMPT)
                self.assertEqual(len(args['messages'][1]['content']), 2)
                self.assertTrue(args['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
                self.assertNotIn('test-not-a-real-key', json.dumps(args))
                self.assertEqual(result['usage']['total_tokens'], 30)


if __name__ == "__main__":
    unittest.main()
