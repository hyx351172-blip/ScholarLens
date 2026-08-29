import sys
import unittest
from pathlib import Path


UNIFIED_DIR = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "Information-Extraction"
    / "unified"
)
sys.path.insert(0, str(UNIFIED_DIR))

from chunkers.structure_aware_chunker import (  # noqa: E402
    ChunkingConfig,
    StructureAwareChunker,
)
from parsers.evidence_context_postprocessor import (  # noqa: E402
    LogicalFigure,
    LogicalFormula,
)
from parsers.models import (  # noqa: E402
    ContentBlock,
    PaperDocument,
    PaperMetadata,
    ParseQualityReport,
    ParserInfo,
)
from parsers.table_postprocessor import LogicalTable  # noqa: E402


def block(order, block_type, text, *, page=1, section=None, relations=None):
    return ContentBlock(
        block_id=f"block_{order:06d}",
        order=order,
        type=block_type,
        text=text,
        page=page,
        bbox=[0.0, 0.0, 100.0, 100.0],
        section_path=section or [],
        relations=relations or {},
    )


def document(blocks):
    return PaperDocument(
        schema_version="1.0",
        paper_id="paper-sha256",
        file_id="file-1",
        filename="paper.pdf",
        parser=ParserInfo(),
        metadata=PaperMetadata(
            title="A Structured Paper",
            authors=["Ada Author", "Ben Builder"],
            abstract="Fallback abstract",
        ),
        sections=[],
        blocks=blocks,
        quality=ParseQualityReport(),
    )


class StructureAwareChunkerTests(unittest.TestCase):
    def test_abstract_is_independent_and_paragraphs_never_cross_sections(self):
        """AC-PDF-002/003: provenance and an independent abstract chunk."""
        blocks = [
            block(1, "title", "A Structured Paper"),
            block(2, "heading", "Abstract", section=["Abstract"]),
            block(
                3,
                "paragraph",
                "This paper introduces a structure-aware retriever.",
                section=["Abstract"],
                relations={"section_kind": "abstract"},
            ),
            block(4, "heading", "1 Introduction", section=["1 Introduction"]),
            block(5, "paragraph", "Introduction evidence.", section=["1 Introduction"]),
            block(6, "heading", "2 Method", section=["2 Method"]),
            block(7, "paragraph", "Method evidence.", section=["2 Method"]),
        ]

        result = StructureAwareChunker().chunk(document(blocks))

        abstracts = [chunk for chunk in result.chunks if chunk.content_type == "abstract"]
        paragraphs = [chunk for chunk in result.chunks if chunk.content_type == "paragraph"]
        self.assertEqual(len(abstracts), 1)
        self.assertIn("This paper introduces", abstracts[0].text)
        self.assertNotIn("Introduction evidence", abstracts[0].text)
        self.assertEqual(
            [chunk.section_path for chunk in paragraphs],
            [["1 Introduction"], ["2 Method"]],
        )
        self.assertTrue(all(chunk.source_block_ids for chunk in result.chunks))

    def test_long_paragraph_splits_on_sentence_boundaries(self):
        text = " ".join(
            f"Sentence {index} contains several retrieval words."
            for index in range(1, 13)
        )
        doc = document(
            [block(10, "paragraph", text, section=["3 Method"])]
        )
        chunker = StructureAwareChunker(
            ChunkingConfig(target_tokens=20, max_tokens=28)
        )

        result = chunker.chunk(doc)

        self.assertGreater(len(result.chunks), 1)
        self.assertTrue(all(chunk.token_count <= 28 for chunk in result.chunks))
        self.assertTrue(all(chunk.section_path == ["3 Method"] for chunk in result.chunks))

    def test_large_table_splits_by_rows_and_repeats_caption_and_header(self):
        """AC-PDF-004/005: preserve table evidence without character bridges."""
        table_block = block(
            20,
            "table",
            "| Model | Accuracy |\n|---|---|\n"
            + "\n".join(f"| Model {i} | {80 + i}% |" for i in range(1, 13)),
            page=4,
            section=["4 Experiments"],
            relations={"logical_table_id": "logical_table_0001"},
        )
        caption_block = block(
            21,
            "caption",
            "Table 1: Accuracy by model.",
            page=4,
            section=["4 Experiments"],
        )
        table = LogicalTable(
            table_id="logical_table_0001",
            label="Table 1",
            number=1,
            caption="Table 1: Accuracy by model.",
            page_start=4,
            page_end=4,
            section_path=["4 Experiments"],
            source_block_ids=[table_block.block_id],
            caption_block_ids=[caption_block.block_id],
            text=table_block.text,
            status="correct",
        )
        chunker = StructureAwareChunker(
            ChunkingConfig(target_tokens=24, max_tokens=34)
        )

        result = chunker.chunk(
            document([table_block, caption_block]), logical_tables=[table]
        )
        chunks = [chunk for chunk in result.chunks if chunk.content_type == "table"]

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.table_id == table.table_id for chunk in chunks))
        self.assertTrue(all("Table 1: Accuracy by model." in chunk.text for chunk in chunks))
        self.assertTrue(all("| Model | Accuracy |" in chunk.text for chunk in chunks))
        self.assertEqual(
            sorted(
                line
                for chunk in chunks
                for line in chunk.text.splitlines()
                if line.startswith("| Model ") and "Accuracy" not in line
            ),
            sorted(f"| Model {i} | {80 + i}% |" for i in range(1, 13)),
        )
        self.assertEqual([chunk.part_index for chunk in chunks], list(range(1, len(chunks) + 1)))
        self.assertTrue(all(chunk.part_count == len(chunks) for chunk in chunks))

    def test_figure_chunk_uses_bound_caption_and_explanation(self):
        figure_block = block(30, "figure", "", page=6, section=["4 Results"])
        caption_block = block(
            31,
            "figure_caption",
            "Figure 2: Retrieval architecture.",
            page=6,
            section=["4 Results"],
        )
        explanation = block(
            32,
            "paragraph",
            "Figure 2 shows the dense and sparse retrieval branches.",
            page=6,
            section=["4 Results"],
        )
        figure = LogicalFigure(
            figure_id="figure_0002_000030",
            label="Figure 2",
            number=2,
            caption=caption_block.text,
            page=6,
            section_path=["4 Results"],
            source_block_ids=[figure_block.block_id],
            caption_block_ids=[caption_block.block_id],
            explanation_block_ids=[explanation.block_id],
            status="context_bound",
        )

        result = StructureAwareChunker().chunk(
            document([figure_block, caption_block, explanation]),
            logical_figures=[figure],
        )
        figure_chunks = [chunk for chunk in result.chunks if chunk.content_type == "figure"]

        self.assertEqual(len(figure_chunks), 1)
        self.assertIn(caption_block.text, figure_chunks[0].text)
        self.assertIn(explanation.text, figure_chunks[0].text)
        self.assertEqual(figure_chunks[0].figure_id, figure.figure_id)
        self.assertEqual(figure_chunks[0].context_block_ids, [explanation.block_id])

    def test_formula_requires_context_and_repeats_formula_when_context_splits(self):
        before = block(
            40,
            "paragraph",
            "We define the score used by the retriever.",
            page=7,
            section=["3 Method"],
        )
        formula_block = block(
            41,
            "formula",
            "Score(q,d) = alpha dense(q,d) + beta sparse(q,d). (3)",
            page=7,
            section=["3 Method"],
        )
        after = block(
            42,
            "paragraph",
            "In Equation (3), alpha and beta control the contribution of each branch. "
            "The coefficients are selected on the validation set.",
            page=7,
            section=["3 Method"],
        )
        orphan = block(50, "formula", "x = y. (9)", page=9, section=["5 Appendix"])
        formula = LogicalFormula(
            formula_id="formula_000041",
            equation_number="3",
            text=formula_block.text,
            page=7,
            section_path=["3 Method"],
            source_block_id=formula_block.block_id,
            context_block_ids=[before.block_id, after.block_id],
            status="context_bound",
        )
        orphan_formula = LogicalFormula(
            formula_id="formula_000050",
            equation_number="9",
            text=orphan.text,
            page=9,
            section_path=["5 Appendix"],
            source_block_id=orphan.block_id,
            context_block_ids=[],
            status="context_missing",
        )
        chunker = StructureAwareChunker(
            ChunkingConfig(target_tokens=22, max_tokens=40)
        )

        result = chunker.chunk(
            document([before, formula_block, after, orphan]),
            logical_formulas=[formula, orphan_formula],
        )
        formula_chunks = [chunk for chunk in result.chunks if chunk.content_type == "formula"]

        self.assertGreaterEqual(len(formula_chunks), 1)
        self.assertTrue(all(formula_block.text in chunk.text for chunk in formula_chunks))
        self.assertTrue(all(chunk.formula_id == formula.formula_id for chunk in formula_chunks))
        self.assertNotIn(orphan_formula.formula_id, {chunk.formula_id for chunk in formula_chunks})
        self.assertTrue(any("context missing" in warning for warning in result.warnings))

    def test_output_is_deterministic_and_contains_legacy_compatibility_fields(self):
        """AC-PDF-002/008: stable IDs plus complete provenance fields."""
        doc = document(
            [block(60, "paragraph", "Stable deterministic content.", section=["1 Intro"])]
        )
        chunker = StructureAwareChunker()

        first = chunker.chunk(doc).to_dict()
        second = chunker.chunk(doc).to_dict()

        self.assertEqual(first, second)
        chunk = first["chunks"][0]
        self.assertEqual(chunk["chunk_id"], "paper-sha256:chunk_0001")
        self.assertEqual(chunk["pages"], [1])
        self.assertFalse(chunk["cross_page_bridge"])
        self.assertIn("text_length", chunk)


if __name__ == "__main__":
    unittest.main()
