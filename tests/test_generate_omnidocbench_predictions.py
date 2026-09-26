import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate_omnidocbench_predictions.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("omnidoc_predictions", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OmniDocBenchPredictionTests(unittest.TestCase):
    def test_reuse_rejects_stale_formula_settings_and_retains_inference_time(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (32, 48), "white").save(root / "page.png")
            annotations = root / "annotations.json"
            annotations.write_text(json.dumps([{"page_info": {
                "image_path": "page.png", "page_attribute": {"subset": "equation_hard"}
            }}]), encoding="utf-8")
            output = root / "result"
            artifact = output / "artifacts" / "page"
            artifact.mkdir(parents=True)
            (output / "predictions").mkdir()
            (output / "predictions" / "page.md").write_text("cached", encoding="utf-8")
            document = {"blocks": [], "parser": {
                "table_mode": "accurate", "ocr_enabled": True,
                "formula_enrichment_enabled": False,
            }, "quality": {"warnings": [], "duration_seconds": 42.5}}
            (artifact / "document.json").write_text(json.dumps(document), encoding="utf-8")
            args = dict(annotations_path=annotations, image_dir=root, output_dir=output,
                        limit=None, table_mode="accurate", do_ocr=True, reuse=True)
            stale = module.generate_predictions(**args, do_formula_enrichment=True)
            self.assertEqual(stale["failed_pages"], 1)
            self.assertIn("settings differ", stale["failures"][0]["error"])
            cached = module.generate_predictions(**args, do_formula_enrichment=False)
            self.assertEqual(cached["failed_pages"], 0)
            self.assertTrue(cached["results"][0]["reused"])
            self.assertEqual(cached["duration_seconds"], 42.5)

    def test_stratified_selection_keeps_each_available_subset(self):
        module = _load_module()
        pages = []
        for subset, count in (
            ("equation_hard", 44),
            ("table_hard", 30),
            ("layout_hard", 3),
            ("v1.5", 23),
        ):
            for index in range(count):
                pages.append(
                    {
                        "page_info": {
                            "image_path": f"{subset}-{index:03d}.png",
                            "page_attribute": {"subset": subset},
                        }
                    }
                )

        selected = module.select_stratified_pages(pages, 10)

        self.assertEqual(len(selected), 10)
        selected_subsets = {
            page["page_info"]["page_attribute"]["subset"] for page in selected
        }
        self.assertEqual(
            selected_subsets,
            {"equation_hard", "table_hard", "layout_hard", "v1.5"},
        )
        self.assertEqual(
            [page["page_info"]["image_path"] for page in selected],
            sorted(page["page_info"]["image_path"] for page in selected),
        )

    def test_image_to_pdf_preserves_page_dimensions(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "page.png"
            pdf_path = root / "page.pdf"
            Image.new("RGB", (320, 480), color="white").save(image_path)

            module.image_to_pdf(image_path, pdf_path)

            with pymupdf.open(pdf_path) as document:
                self.assertEqual(document.page_count, 1)
                self.assertAlmostEqual(document[0].rect.width, 320.0)
                self.assertAlmostEqual(document[0].rect.height, 480.0)


if __name__ == "__main__":
    unittest.main()
