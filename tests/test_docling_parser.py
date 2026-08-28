import json
import sys
import tempfile
import unittest
from pathlib import Path


UNIFIED_DIR = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "Information-Extraction"
    / "unified"
)
sys.path.insert(0, str(UNIFIED_DIR))

from parsers.docling_parser import DoclingParser, save_parse_result  # noqa: E402


class _Label:
    def __init__(self, value):
        self.value = value


class _BBox:
    def __init__(self, left, top, right, bottom):
        self.l = left
        self.t = top
        self.r = right
        self.b = bottom


class _Prov:
    def __init__(self, page_no, bbox):
        self.page_no = page_no
        self.bbox = bbox


class _Item:
    def __init__(
        self,
        label,
        text="",
        page=1,
        level=1,
        table_markdown=None,
        orig="",
        bbox=None,
    ):
        self.label = _Label(label)
        self.text = text
        self.level = level
        self.prov = [_Prov(page, _BBox(*(bbox or (10, 20, 100, 120))))]
        self._table_markdown = table_markdown
        self.orig = orig

    def export_to_markdown(self, _document):
        return self._table_markdown or self.text


class _Document:
    def __init__(self, items):
        self._items = items
        self.pages = {1: object(), 2: object()}

    def iterate_items(self):
        for item in self._items:
            yield item, item.level

    def export_to_markdown(self):
        return "# A Reliable Paper\n\n## Abstract\n\nThis study evaluates parsing."

    def export_to_dict(self):
        return {"name": "fixture", "pages": {"1": {}, "2": {}}}


class _ConversionResult:
    def __init__(self, document):
        self.document = document


class _Converter:
    def __init__(self, document):
        self.document = document
        self.received_path = None

    def convert(self, path):
        self.received_path = path
        return _ConversionResult(self.document)


class DoclingParserTests(unittest.TestCase):
    def _build_parser(self):
        items = [
            # Real Docling output may label the paper title as section_header.
            _Item("section_header", "A Reliable Paper", page=1, level=1),
            _Item(
                "text",
                "Alice Example alice@example.edu University of Test, City "
                "Bob Researcher bob@example.edu University of Test",
                page=1,
                level=1,
            ),
            _Item(
                "text",
                "Department of Science Technology {alice,bob}@example.edu",
                page=1,
                level=1,
            ),
            _Item("section_header", "Abstract", page=1, level=1),
            _Item(
                "text",
                "This study evaluates parsing for arXiv:2608.10509.",
                page=1,
                level=1,
            ),
            _Item("section_header", "1 Introduction", page=2, level=1),
            _Item("text", "The introduction starts here.", page=2, level=1),
            _Item(
                "table",
                page=2,
                level=1,
                table_markdown="| Model | Score |\n|---|---:|\n| Ours | 0.91 |",
            ),
        ]
        document = _Document(items)
        converter = _Converter(document)
        return DoclingParser(converter=converter), converter

    def test_parse_preserves_metadata_reading_order_and_provenance(self):
        """AC-102/AC-103: metadata, stable identity and page provenance."""
        parser, converter = self._build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fixture")

            result = parser.parse(
                pdf_path,
                file_id="file_test",
                original_filename="论文.pdf",
            )

        self.assertEqual(converter.received_path, str(pdf_path))
        self.assertEqual(result.document.file_id, "file_test")
        self.assertEqual(result.document.filename, "论文.pdf")
        self.assertEqual(len(result.document.paper_id), 64)
        self.assertEqual(result.document.metadata.title, "A Reliable Paper")
        self.assertIn("Alice Example", result.document.metadata.authors)
        self.assertIn("Bob Researcher", result.document.metadata.authors)
        self.assertEqual(
            result.document.metadata.authors,
            ["Alice Example", "Bob Researcher"],
        )
        self.assertIn("evaluates parsing", result.document.metadata.abstract)
        self.assertEqual(result.document.metadata.arxiv_id, "2608.10509")
        self.assertEqual(
            [block.order for block in result.document.blocks],
            list(range(len(result.document.blocks))),
        )
        self.assertEqual(result.document.blocks[0].page, 1)
        self.assertEqual(result.document.blocks[0].bbox, [10.0, 20.0, 100.0, 120.0])
        self.assertGreater(result.document.quality.provenance_coverage, 0.99)

    def test_table_is_a_structured_block_and_keeps_its_section(self):
        """AC-105: tables remain explicit blocks instead of flattened prose."""
        parser, _ = self._build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fixture")
            result = parser.parse(pdf_path)

        table = next(block for block in result.document.blocks if block.type == "table")
        self.assertIn("| Model | Score |", table.text)
        self.assertEqual(table.page, 2)
        self.assertEqual(table.section_path, ["1 Introduction"])
        self.assertEqual(result.document.quality.block_counts["table"], 1)

    def test_formula_prefers_text_then_falls_back_to_orig_and_reports_missing(self):
        """Formula text is preserved without inventing LaTeX content."""
        items = [
            _Item("section_header", "Formula Paper", page=1),
            _Item("section_header", "Abstract", page=1),
            _Item("text", "This paper contains formulas.", page=1),
            _Item(
                "formula",
                text="E = mc² (1)",
                orig="E = m c 2 (1)",
                page=1,
            ),
            _Item(
                "formula",
                text="",
                orig="Score( m,q,a ) = s ( m,q ) ρ ( m,a ) . (3)",
                page=1,
            ),
            _Item("formula", text="", orig="", page=1),
        ]
        parser = DoclingParser(converter=_Converter(_Document(items)))

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "formulas.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fixture")
            result = parser.parse(pdf_path)

        formulas = [
            block for block in result.document.blocks if block.type == "formula"
        ]
        self.assertEqual(formulas[0].text, "E = mc² (1)")
        self.assertEqual(formulas[0].relations["formula_text_source"], "text")
        self.assertEqual(
            formulas[1].text,
            "Score( m,q,a ) = s ( m,q ) ρ ( m,a ) . (3)",
        )
        self.assertEqual(
            formulas[1].relations["formula_text_source"], "orig_fallback"
        )
        self.assertEqual(formulas[2].text, "")
        self.assertEqual(formulas[2].relations["formula_text_source"], "missing")
        self.assertIn("1 个公式没有可用文本", result.document.quality.warnings)

    def test_save_writes_parse_artifacts_but_never_chunks(self):
        """AC-101/AC-104: persist parser artifacts, never chunks.json."""
        parser, _ = self._build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fixture")
            result = parser.parse(pdf_path)

            paths = save_parse_result(tmp_path / "result", result)

            self.assertEqual(
                set(paths),
                {
                    "markdown",
                    "document",
                    "docling_document",
                    "quality_report",
                    "tables",
                    "figures",
                    "formulas",
                },
            )
            self.assertFalse((tmp_path / "result" / "chunks.json").exists())
            stored = json.loads(Path(paths["document"]).read_text(encoding="utf-8"))
            self.assertEqual(stored["schema_version"], "1.0")
            self.assertEqual(stored["parser"]["name"], "docling")
            tables = json.loads(Path(paths["tables"]).read_text(encoding="utf-8"))
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0]["source_block_ids"], ["block_000007"])

    def test_reading_order_runs_before_section_binding(self):
        items = [
            _Item("section_header", "Geometry Paper", page=1, bbox=(50, 780, 560, 740)),
            _Item("section_header", "Abstract", page=1, bbox=(50, 700, 120, 680)),
            _Item("text", "Abstract text.", page=1, bbox=(50, 660, 560, 600)),
            _Item("section_header", "2 Method", page=2, bbox=(320, 700, 430, 680)),
            _Item("text", "Method text.", page=2, bbox=(320, 660, 560, 600)),
            _Item("section_header", "1 Introduction", page=2, bbox=(50, 700, 190, 680)),
            _Item("text", "Introduction text.", page=2, bbox=(50, 660, 290, 600)),
        ]
        parser = DoclingParser(converter=_Converter(_Document(items)))

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "geometry.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fixture")
            result = parser.parse(pdf_path)

        page_two = [block for block in result.document.blocks if block.page == 2]
        self.assertEqual(
            [block.text for block in page_two],
            ["1 Introduction", "Introduction text.", "2 Method", "Method text."],
        )
        self.assertEqual(page_two[1].section_path, ["1 Introduction"])
        self.assertEqual(page_two[3].section_path, ["2 Method"])
        self.assertEqual(
            result.document.quality.reading_order_page_methods[2],
            "two_column_geometry",
        )


if __name__ == "__main__":
    unittest.main()
