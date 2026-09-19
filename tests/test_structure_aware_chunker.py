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
    estimate_tokens,
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
        self.assertEqual(
            chunk["chunk_id"],
            "paper-sha256:paragraph:block_000060:part_0001",
        )
        self.assertEqual(chunk["legacy_chunk_id"], "paper-sha256:chunk_0001")
        self.assertEqual(chunk["pages"], [1])
        self.assertFalse(chunk["cross_page_bridge"])
        self.assertIn("text_length", chunk)

    def test_unstructured_large_table_is_bounded_without_losing_caption(self):
        """AC-CHUNK-V2-001: fallback table chunks respect the hard budget."""
        table_block = block(
            70,
            "table",
            "\n".join(
                f"Model {index} reports accuracy {80 + index} with detailed evidence"
                for index in range(1, 15)
            ),
            page=8,
            section=["5 Results"],
        )
        caption_block = block(
            71,
            "caption",
            "Table A.1: Detailed results.",
            page=8,
            section=["5 Results"],
        )
        table = LogicalTable(
            table_id="logical_table_a_1",
            label="Table A.1",
            number=None,
            caption=caption_block.text,
            page_start=8,
            page_end=8,
            section_path=["5 Results"],
            source_block_ids=[table_block.block_id],
            caption_block_ids=[caption_block.block_id],
            text=table_block.text,
            status="correct",
            identifier="A.1",
        )
        chunker = StructureAwareChunker(ChunkingConfig(target_tokens=24, max_tokens=32))

        result = chunker.chunk(
            document([table_block, caption_block]), logical_tables=[table]
        )
        chunks = [item for item in result.chunks if item.content_type == "table"]

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(item.token_count <= 32 for item in chunks))
        self.assertTrue(all(table.caption in item.text for item in chunks))
        self.assertTrue(all(item.table_identifier == "A.1" for item in chunks))
        self.assertFalse(
            any("oversized_atomic_unit" in item.warnings for item in chunks)
        )

    def test_multiblock_table_chunks_have_precise_page_and_source_provenance(self):
        """AC-CHUNK-V2-002: each table part cites only blocks it actually uses."""
        first = block(
            80,
            "table",
            "| Model | Score |\n|---|---|\n| A | 1 |\n| B | 2 |",
            page=10,
            section=["6 Evaluation"],
        )
        second = block(
            81,
            "table",
            "| Model | Score |\n|---|---|\n| C | 3 |\n| D | 4 |",
            page=11,
            section=["6 Evaluation"],
        )
        caption = block(
            82,
            "caption",
            "Table 6.1: Results continued across pages.",
            page=10,
            section=["6 Evaluation"],
        )
        table = LogicalTable(
            table_id="logical_table_6_1",
            label="Table 6.1",
            number=None,
            caption=caption.text,
            page_start=10,
            page_end=11,
            section_path=["6 Evaluation"],
            source_block_ids=[first.block_id, second.block_id],
            caption_block_ids=[caption.block_id],
            text=f"{first.text}\n\n{second.text}",
            status="merged_fragments",
            identifier="6.1",
        )
        chunker = StructureAwareChunker(ChunkingConfig(target_tokens=12, max_tokens=22))

        result = chunker.chunk(
            document([first, second, caption]), logical_tables=[table]
        )
        chunks = [item for item in result.chunks if item.content_type == "table"]

        self.assertGreaterEqual(len(chunks), 2)
        for item in chunks:
            self.assertEqual(item.page_start, item.page_end)
            expected_source = first.block_id if item.page_start == 10 else second.block_id
            self.assertEqual(item.source_block_ids, [expected_source])
            self.assertEqual(item.table_identifier, "6.1")

    def test_long_figure_description_splits_and_repeats_caption(self):
        """AC-CHUNK-V2-003: a long Figure core no longer creates an oversized chunk."""
        figure_block = block(
            90,
            "figure",
            " ".join(f"visual-token-{index}" for index in range(80)),
            page=12,
            section=["7 Analysis"],
        )
        caption_block = block(
            91,
            "caption",
            "Figure 7: Error categories.",
            page=12,
            section=["7 Analysis"],
        )
        figure = LogicalFigure(
            figure_id="logical_figure_7",
            label="Figure 7",
            number=7,
            caption=caption_block.text,
            page=12,
            section_path=["7 Analysis"],
            source_block_ids=[figure_block.block_id],
            caption_block_ids=[caption_block.block_id],
            explanation_block_ids=[],
            status="context_bound",
        )
        chunker = StructureAwareChunker(ChunkingConfig(target_tokens=24, max_tokens=32))

        result = chunker.chunk(
            document([figure_block, caption_block]), logical_figures=[figure]
        )
        chunks = [item for item in result.chunks if item.content_type == "figure"]

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(item.token_count <= 32 for item in chunks))
        self.assertTrue(all(caption_block.text in item.text for item in chunks))

    def test_paragraphs_do_not_merge_across_structural_evidence(self):
        """AC-CHUNK-V2-004: Figure/Table/Formula blocks are paragraph barriers."""
        before = block(100, "paragraph", "Evidence before the figure.", section=["8 Results"])
        figure = block(101, "figure", "figure.png", section=["8 Results"])
        after = block(102, "paragraph", "Evidence after the figure.", section=["8 Results"])

        result = StructureAwareChunker().chunk(document([before, figure, after]))
        chunks = [item for item in result.chunks if item.content_type == "paragraph"]

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].source_block_ids, [before.block_id])
        self.assertEqual(chunks[1].source_block_ids, [after.block_id])

    def test_chunk_identity_is_stable_when_an_earlier_chunk_is_inserted(self):
        """AC-CHUNK-V2-005: stable IDs derive from evidence, not global position."""
        target = block(111, "paragraph", "Stable target evidence.", section=["2 Method"])
        original = StructureAwareChunker().chunk(document([target]))
        inserted = block(110, "paragraph", "Earlier evidence.", section=["1 Intro"])
        changed = StructureAwareChunker().chunk(document([inserted, target]))

        original_target = next(
            item for item in original.chunks if target.block_id in item.source_block_ids
        )
        changed_target = next(
            item for item in changed.chunks if target.block_id in item.source_block_ids
        )
        self.assertEqual(original_target.chunk_id, changed_target.chunk_id)
        self.assertNotEqual(original_target.chunk_index, changed_target.chunk_index)

    def test_custom_token_counter_controls_chunk_budget(self):
        """AC-CHUNK-V2-006: production tokenizers can replace the local estimator."""
        counter = lambda value: len(value.split())  # noqa: E731
        text = "one two three four five six seven eight nine ten"
        chunker = StructureAwareChunker(
            ChunkingConfig(target_tokens=3, max_tokens=4), token_counter=counter
        )

        result = chunker.chunk(
            document([block(120, "paragraph", text, section=["9 Appendix"])])
        )

        self.assertTrue(all(item.token_count <= 4 for item in result.chunks))
        self.assertEqual(
            [item.token_count for item in result.chunks],
            [counter(item.text) for item in result.chunks],
        )
        self.assertGreater(estimate_tokens("visual-token-1"), counter("visual-token-1"))

    def test_empty_table_is_skipped_with_an_explicit_quality_warning(self):
        """AC-CHUNK-V2-007: empty parser artifacts never become empty chunks."""
        table_block = block(130, "table", "", page=14, section=["Appendix"])
        table = LogicalTable(
            table_id="logical_table_empty",
            label=None,
            number=None,
            caption=None,
            page_start=14,
            page_end=14,
            section_path=["Appendix"],
            source_block_ids=[table_block.block_id],
            caption_block_ids=[],
            text="",
            status="caption_missing",
        )

        result = StructureAwareChunker().chunk(
            document([table_block]), logical_tables=[table]
        )

        self.assertEqual(result.chunks, [])
        self.assertTrue(
            any("no textual table evidence" in warning for warning in result.warnings)
        )


if __name__ == "__main__":
    unittest.main()
