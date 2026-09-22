import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"
sys.path.insert(0, str(UNIFIED_DIR))

from parsers.evidence_context_postprocessor import LogicalFormula  # noqa: E402
from parsers.models import (  # noqa: E402
    ContentBlock,
    PaperDocument,
    PaperMetadata,
    ParseQualityReport,
    ParserInfo,
)
from parsers.table_postprocessor import LogicalTable  # noqa: E402
from parsers.vlm_page_repairer import VLMPageRepairer  # noqa: E402


def block(order, block_type, text, *, section=None, relations=None):
    return ContentBlock(
        block_id=f"block_{order:06d}",
        order=order,
        type=block_type,
        text=text,
        page=1,
        bbox=[0.0, 0.0, 100.0, 100.0],
        section_path=section or [],
        relations=relations or {},
    )


class _FakeParser:
    def __init__(self, result):
        self.result = result

    def parse(self, *args, **kwargs):
        return self.result


class _FakeVLMClient:
    def analyze_page(self, *, page, image_data_url, context):
        return {
            "title_block_ids": ["block_000001"],
            "abstract_block_ids": ["block_000002"],
            "bindings": [
                {
                    "kind": "table",
                    "object_block_ids": ["block_000004"],
                    "caption_block_ids": ["block_000003"],
                    "confidence": 0.95,
                    "reason": "Caption is directly above the table.",
                }
            ],
        }


class _FakeReclassifyingVLMClient:
    def analyze_page(self, *, page, image_data_url, context):
        return {
            "reclassifications": [
                {
                    "from_kind": "table",
                    "to_kind": "figure",
                    "object_block_ids": ["block_000004"],
                    "caption_block_ids": ["block_000003"],
                    "confidence": 0.97,
                    "reason": "The author labels the table-shaped object Figure G.1.",
                }
            ],
            "bindings": [],
        }


class DoclingChunkingIntegrationTests(unittest.TestCase):
    def test_vlm_reclassification_updates_service_contract_and_figure_chunk(self):
        """AC-VLM-008: the service exposes reclassified evidence consistently."""
        with tempfile.TemporaryDirectory() as temp_dir:
            title = block(1, "title", "Semantic Classification Paper")
            body = block(2, "paragraph", "Existing abstract evidence.")
            caption = block(3, "caption", "Figure G.1: Formatted dataset example")
            table_block = block(
                4,
                "table",
                "| Context | Answer |\n|---|---|\n| Example | Yes |",
                relations={
                    "logical_table_id": "logical_table_unlabelled_0001",
                    "caption_block_ids": [],
                    "postprocess_status": "caption_missing",
                    "warnings": ["caption_missing"],
                },
            )
            document = PaperDocument(
                schema_version="1.0",
                paper_id="paper-reclassify",
                file_id="file-reclassify",
                filename="reclassify.pdf",
                parser=ParserInfo(),
                metadata=PaperMetadata(
                    title=title.text,
                    abstract=body.text,
                ),
                sections=[],
                blocks=[title, body, caption, table_block],
                quality=ParseQualityReport(
                    total_pages=1,
                    parsed_pages=1,
                    total_blocks=4,
                    block_counts={
                        "title": 1,
                        "paragraph": 1,
                        "caption": 1,
                        "table": 1,
                    },
                ),
            )
            table = LogicalTable(
                table_id="logical_table_unlabelled_0001",
                label=None,
                number=None,
                caption=None,
                page_start=1,
                page_end=1,
                section_path=["Appendix G"],
                source_block_ids=[table_block.block_id],
                caption_block_ids=[],
                text=table_block.text,
                status="caption_missing",
                warnings=["caption_missing"],
            )
            parse_result = SimpleNamespace(
                document=document,
                markdown="# Semantic Classification Paper",
                raw_document={},
                logical_tables=[table],
                logical_figures=[],
                logical_formulas=[],
            )

            import unified_pdf_extraction_service as extraction_service  # noqa: E402

            service = extraction_service.PDFExtractionService()
            service._docling_parser = _FakeParser(parse_result)
            service._vlm_page_repairer = VLMPageRepairer(
                client=_FakeReclassifyingVLMClient(),
                renderer=lambda _path, page, _dpi: f"data:image/png;base64,page-{page}",
            )
            pdf_path = Path(temp_dir) / "reclassify.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

            result = asyncio.run(
                service.extract_docling(
                    str(pdf_path),
                    perform_vlm_repair=True,
                    perform_chunking=True,
                )
            )

            self.assertEqual(result["metadata"]["logical_table_count"], 0)
            self.assertEqual(result["metadata"]["logical_figure_count"], 1)
            self.assertEqual(result["tables"], [])
            self.assertEqual(result["figures"][0]["label"], "Figure G.1")
            source = next(
                item
                for item in result["structured_document"]["blocks"]
                if item["block_id"] == table_block.block_id
            )
            self.assertEqual(source["type"], "table")
            self.assertEqual(source["relations"]["semantic_type"], "figure")
            evidence_chunks = [
                item
                for item in result["chunks"]
                if table_block.block_id in item["source_block_ids"]
            ]
            self.assertTrue(evidence_chunks)
            self.assertTrue(
                all(item["content_type"] == "figure" for item in evidence_chunks)
            )
            self.assertTrue(
                any(
                    item["type"] == "object_reclassification"
                    for item in result["vlm_repair"]["accepted_repairs"]
                )
            )

    def test_vlm_repair_runs_before_chunking_and_persists_audit(self):
        """AC-VLM-005: repaired structure reaches chunks and audit storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            title = block(1, "title", "Recovered Research Title")
            abstract = block(2, "paragraph", "Recovered abstract evidence.")
            caption = block(3, "caption", "Table 1: Evaluation results")
            table_block = block(4, "table", "| Model | Score |\n|---|---|\n| A | 9 |")
            document = PaperDocument(
                schema_version="1.0",
                paper_id="paper-vlm",
                file_id="file-vlm",
                filename="vlm.pdf",
                parser=ParserInfo(),
                metadata=PaperMetadata(
                    title="https://arxiv.org/abs/1234.5678",
                    abstract=None,
                ),
                sections=[],
                blocks=[title, abstract, caption, table_block],
                quality=ParseQualityReport(
                    total_pages=1,
                    parsed_pages=1,
                    total_blocks=4,
                    block_counts={"title": 1, "paragraph": 1, "caption": 1, "table": 1},
                ),
            )
            table = LogicalTable(
                table_id="table_1",
                label=None,
                number=None,
                caption=None,
                page_start=1,
                page_end=1,
                section_path=[],
                source_block_ids=[table_block.block_id],
                caption_block_ids=[],
                text=table_block.text,
                status="unlabelled",
            )
            parse_result = SimpleNamespace(
                document=document,
                markdown="# original",
                raw_document={},
                logical_tables=[table],
                logical_figures=[],
                logical_formulas=[],
            )

            import unified_pdf_extraction_service as extraction_service  # noqa: E402

            service = extraction_service.PDFExtractionService()
            service._docling_parser = _FakeParser(parse_result)
            service._vlm_page_repairer = VLMPageRepairer(
                client=_FakeVLMClient(),
                renderer=lambda _path, page, _dpi: f"data:image/png;base64,page-{page}",
            )
            pdf_path = Path(temp_dir) / "vlm.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

            result = asyncio.run(
                service.extract_docling(
                    str(pdf_path),
                    perform_vlm_repair=True,
                    perform_chunking=True,
                )
            )

            self.assertTrue(result["metadata"]["vlm_repair_performed"])
            self.assertEqual(
                result["metadata"]["paper_metadata"]["title"],
                "Recovered Research Title",
            )
            self.assertEqual(result["tables"][0]["caption_block_ids"], [caption.block_id])
            self.assertEqual(len(result["vlm_repair"]["accepted_repairs"]), 3)
            self.assertTrue(any(chunk["content_type"] == "table" for chunk in result["chunks"]))

            extraction_service.EXTRACTION_RESULTS_DIR = Path(temp_dir) / "results"
            paths = extraction_service.save_extraction_results(
                "file-vlm", "vlm.pdf", result
            )
            audit = json.loads(Path(paths["vlm_repair"]).read_text(encoding="utf-8"))
            self.assertEqual(len(audit["accepted_repairs"]), 3)

    def test_extract_docling_chunks_and_persists_scientific_contract(self):
        """AC-PDF-001/002: Docling output persists valid chunks.json."""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["UPLOAD_BASE_DIR"] = str(Path(temp_dir) / "uploads")
            os.environ["EXTRACTION_RESULTS_DIR"] = str(Path(temp_dir) / "results")
            os.environ["MILVUS_API_ENABLED"] = "false"

            import unified_pdf_extraction_service as extraction_service  # noqa: E402

            title = block(1, "title", "Chunking Integration Paper")
            abstract = block(
                2,
                "paragraph",
                "This abstract is independently retrievable.",
                section=["Abstract"],
                relations={"section_kind": "abstract"},
            )
            context = block(
                3,
                "paragraph",
                "We define the score as follows.",
                section=["2 Method"],
            )
            formula_block = block(
                4,
                "formula",
                "score(q,d) = dense(q,d) + sparse(q,d). (1)",
                section=["2 Method"],
            )
            formula = LogicalFormula(
                formula_id="formula_000004",
                equation_number="1",
                text=formula_block.text,
                page=1,
                section_path=["2 Method"],
                source_block_id=formula_block.block_id,
                context_block_ids=[context.block_id],
                status="context_bound",
            )
            document = PaperDocument(
                schema_version="1.0",
                paper_id="paper-integration",
                file_id="file-integration",
                filename="integration.pdf",
                parser=ParserInfo(),
                metadata=PaperMetadata(
                    title="Chunking Integration Paper",
                    authors=["Ada Author"],
                    abstract=abstract.text,
                ),
                sections=[],
                blocks=[title, abstract, context, formula_block],
                quality=ParseQualityReport(
                    total_pages=1,
                    parsed_pages=1,
                    total_blocks=4,
                    block_counts={"title": 1, "paragraph": 2, "formula": 1},
                ),
            )
            parse_result = SimpleNamespace(
                document=document,
                markdown="# Chunking Integration Paper",
                raw_document={"schema_name": "DoclingDocument"},
                logical_tables=[],
                logical_figures=[],
                logical_formulas=[formula],
            )
            service = extraction_service.PDFExtractionService()
            service._docling_parser = _FakeParser(parse_result)
            pdf_path = Path(temp_dir) / "integration.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

            result = asyncio.run(
                service.extract_docling(
                    str(pdf_path),
                    original_filename="integration.pdf",
                    file_id="file-integration",
                    perform_chunking=True,
                )
            )

            self.assertTrue(result["metadata"]["chunking_performed"])
            self.assertGreater(result["chunk_stats"]["total_chunks"], 0)
            self.assertEqual(result["chunk_schema_version"], "1.1")
            self.assertTrue(all(chunk["source_block_ids"] for chunk in result["chunks"]))
            self.assertTrue(all("retrieval_text" in chunk for chunk in result["chunks"]))
            self.assertTrue(
                all(chunk["schema_version"] == "1.1" for chunk in result["chunks"])
            )
            self.assertTrue(
                all(chunk["legacy_chunk_id"] for chunk in result["chunks"])
            )

            extraction_service.EXTRACTION_RESULTS_DIR = Path(temp_dir) / "results"
            paths = extraction_service.save_extraction_results(
                "file-integration", "integration.pdf", result
            )
            chunks_path = Path(paths["chunks"])
            payload = json.loads(chunks_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "1.1")
            self.assertEqual(len(payload["chunks"]), result["chunk_stats"]["total_chunks"])
            self.assertEqual(payload["chunk_stats"]["bridge_chunks"], 0)


if __name__ == "__main__":
    unittest.main()
