import asyncio
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/Information-Extraction/unified"))
from parsers.models import ContentBlock
from parsers.markdown_renderer import render_document_markdown
from parsers.docling_parser import DoclingParser, save_parse_result
from tests.test_docling_parser import _Item, _Document, _Converter


def table_data():
    def cell(text, r, c, rs=1, cs=1, header=False):
        return {"text": text, "start_row_offset_idx": r, "end_row_offset_idx": r + rs,
                "start_col_offset_idx": c, "end_col_offset_idx": c + cs,
                "row_span": rs, "col_span": cs, "column_header": header,
                "row_header": False, "row_section": False,
                "bbox": {"l": 10, "t": 20, "r": 100, "b": 30, "coord_origin": "TOPLEFT"}}
    return {"num_rows": 3, "num_cols": 3, "table_cells": [
        cell("Model", 0, 0, rs=2, header=True),
        cell("<Score> & quality", 0, 1, cs=2, header=True),
        cell("A", 1, 1, header=True), cell("B", 1, 2, header=True),
        cell("Ours", 2, 0), cell("0.91", 2, 1), cell("0.92", 2, 2),
    ]}


class TableStructureTests(unittest.TestCase):
    def parse(self, data):
        item = _Item("table", table_markdown="Table 1. Scores\n\n| Model | A | B |\n|---|---|---|\n| Ours | 0.91 | 0.92 |")
        item.data = SimpleNamespace(**data)
        item.self_ref = "#/tables/0"
        parser = DoclingParser(converter=_Converter(_Document([item])))
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "table.pdf"
            pdf.write_bytes(b"%PDF fixture")
            return parser.parse(pdf)

    def test_structure_survives_parse_export_and_json_roundtrip(self):
        """AC-TABLE-702/703: native spans/provenance are not flattened."""
        data = table_data()
        result = self.parse(data)
        block = result.document.blocks[0]
        self.assertIn("| Model | A | B |", block.text)  # Existing consumer contract.
        self.assertEqual(block.table_structure["table_cells"], data["table_cells"])
        self.assertEqual(block.table_structure["source_ref"], "#/tables/0")
        self.assertTrue(block.table_structure["valid"])
        self.assertIn('<th rowspan="2">Model</th>', result.markdown)
        self.assertIn('<th colspan="2">&lt;Score&gt; &amp; quality</th>', result.markdown)
        self.assertEqual(result.markdown.count("Table 1. Scores"), 1)
        self.assertNotIn("|---|", result.markdown)
        with tempfile.TemporaryDirectory() as tmp:
            paths = save_parse_result(tmp, result)
            stored = json.loads(Path(paths["document"]).read_text(encoding="utf-8"))
        restored = ContentBlock(**stored["blocks"][0])
        self.assertEqual(restored.table_structure, block.table_structure)
        self.assertEqual(render_document_markdown([restored]), result.markdown)

    def test_invalid_grids_fall_back_without_losing_legacy_text(self):
        """AC-TABLE-703: no silent overlap, clipping or invented merged cells."""
        for failure in ("overlap", "outside", "span_mismatch", "huge", "fractional", "nonfinite_bbox"):
            with self.subTest(failure=failure):
                data = table_data()
                if failure == "overlap":
                    data["table_cells"].append(copy.deepcopy(data["table_cells"][0]))
                elif failure == "outside":
                    data["table_cells"][0]["end_row_offset_idx"] = 10
                    data["table_cells"][0]["row_span"] = 10
                elif failure == "span_mismatch":
                    data["table_cells"][0]["row_span"] = 1
                elif failure == "huge":
                    data["num_rows"] = 10000000
                elif failure == "fractional":
                    data["table_cells"][0]["start_row_offset_idx"] = 0.5
                else:
                    data["table_cells"][0]["bbox"]["l"] = float("nan")
                result = self.parse(data)
                block = result.document.blocks[0]
                self.assertFalse(block.table_structure["valid"])
                self.assertNotIn("<table>", result.markdown)
                self.assertIn(block.text, result.markdown)
                self.assertTrue(any("table structure" in warning for warning in result.document.quality.warnings))

    def test_legacy_missing_data_and_reclassified_figure_keep_text(self):
        """AC-TABLE-704: optional payload does not require migrating old JSON."""
        legacy = ContentBlock(**{"block_id": "old", "order": 0, "type": "table", "text": "| old |\n|---|"})
        self.assertIsNone(legacy.table_structure)
        self.assertEqual(render_document_markdown([legacy]), legacy.text + "\n")
        block = self.parse(table_data()).document.blocks[0]
        block.type = "figure"
        self.assertEqual(render_document_markdown([block]), block.text + "\n")

    def test_new_structure_does_not_change_logical_table_or_chunks(self):
        """AC-TABLE-704: structured export cannot silently alter retrieval text."""
        from chunkers.structure_aware_chunker import StructureAwareChunker
        parsed = self.parse(table_data())
        before = copy.deepcopy(parsed)
        for block in before.document.blocks:
            block.table_structure = None
        chunker = StructureAwareChunker()
        actual = chunker.chunk(parsed.document, logical_tables=parsed.logical_tables)
        expected = chunker.chunk(before.document, logical_tables=before.logical_tables)
        self.assertEqual(actual.to_dict(), expected.to_dict())
        self.assertIn("0.91", json.dumps(actual.to_dict()))

    def test_service_keeps_legacy_view_and_saves_structured_export(self):
        """AC-TABLE-704: do not send raw HTML to the legacy Markdown-only UI."""
        import unified_pdf_extraction_service as extraction_service
        parsed = self.parse(table_data())
        service = extraction_service.PDFExtractionService()
        service._docling_parser = SimpleNamespace(parse=lambda *a, **k: parsed)
        with tempfile.TemporaryDirectory() as tmp, patch.object(extraction_service, "EXTRACTION_RESULTS_DIR", Path(tmp)):
            result = asyncio.run(service.extract_docling("unused.pdf", perform_chunking=True))
            paths = extraction_service.save_extraction_results("fixture", "paper.pdf", result)
            self.assertIn("| Model |", result["markdown"])
            self.assertNotIn("<table>", result["markdown"])
            self.assertIn('<th rowspan="2">', result["structured_markdown"])
            self.assertEqual(Path(paths["structured_markdown"]).read_text(encoding="utf-8"), result["structured_markdown"])
            stored = json.loads(Path(paths["document"]).read_text(encoding="utf-8"))
            self.assertEqual(stored["blocks"][0]["table_structure"], parsed.document.blocks[0].table_structure)
            self.assertTrue(any("0.91" in chunk["text"] for chunk in result["chunks"]))

    def test_missing_grid_slots_are_explicit_and_loaded_structure_is_revalidated(self):
        """AC-TABLE-703: missing cells stay empty, hostile text stays escaped."""
        data = table_data()
        data["table_cells"].pop()
        result = self.parse(data)
        structure = result.document.blocks[0].table_structure
        self.assertEqual(structure["uncovered_slots"], 1)
        self.assertIn("<td></td>", result.markdown)
        self.assertTrue(structure["warnings"])
        structure["table_cells"][0]["end_row_offset_idx"] = 100
        self.assertNotIn("<table>", render_document_markdown(result.document.blocks))


if __name__ == "__main__":
    unittest.main()
