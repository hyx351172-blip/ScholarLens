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


class DoclingChunkingIntegrationTests(unittest.TestCase):
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
            self.assertEqual(result["chunk_schema_version"], "1.0")
            self.assertTrue(all(chunk["source_block_ids"] for chunk in result["chunks"]))
            self.assertTrue(all("retrieval_text" in chunk for chunk in result["chunks"]))

            extraction_service.EXTRACTION_RESULTS_DIR = Path(temp_dir) / "results"
            paths = extraction_service.save_extraction_results(
                "file-integration", "integration.pdf", result
            )
            chunks_path = Path(paths["chunks"])
            payload = json.loads(chunks_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "1.0")
            self.assertEqual(len(payload["chunks"]), result["chunk_stats"]["total_chunks"])
            self.assertEqual(payload["chunk_stats"]["bridge_chunks"], 0)


if __name__ == "__main__":
    unittest.main()
