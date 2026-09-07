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

from parsers.models import ContentBlock  # noqa: E402
from parsers.table_postprocessor import TablePostProcessor  # noqa: E402


def block(order, block_type, text, *, page=1, bbox=None):
    return ContentBlock(
        block_id=f"block_{order:06d}",
        order=order,
        type=block_type,
        text=text,
        page=page,
        bbox=bbox or [50.0, 700.0 - order, 550.0, 600.0 - order],
        section_path=["Results"],
    )


class TablePostProcessorTests(unittest.TestCase):
    def setUp(self):
        self.processor = TablePostProcessor()

    def test_merges_unlabelled_fragment_after_trailing_caption(self):
        """AC-PDF-004: one captioned multi-panel table remains one table."""
        blocks = [
            block(10, "table", "Table 4: Results.\n\n| A | B |\n|---|---|\n| 1 | 2 |"),
            block(11, "caption", "Table 4: Results."),
            block(12, "table", "| C | D |\n|---|---|\n| 3 | 4 |"),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(len(result.tables), 1)
        table = result.tables[0]
        self.assertEqual(table.label, "Table 4")
        self.assertEqual(
            table.source_block_ids,
            ["block_000010", "block_000012"],
        )
        self.assertEqual(table.caption_block_ids, ["block_000011"])
        self.assertEqual(table.status, "merged_fragments")
        self.assertEqual(result.blocks[0].relations["fragment_count"], 2)
        self.assertEqual(result.blocks[2].relations["fragment_index"], 2)

    def test_binds_leading_caption_to_next_table_without_merging_previous(self):
        """A leading caption starts a new logical table, not a continuation."""
        blocks = [
            block(20, "table", "Table 8: Domain results.\n\n| A |\n|---|\n| 1 |"),
            block(21, "caption", "Table 8: Domain results."),
            block(22, "caption", "Table 9: Diagnostics."),
            block(23, "table", "| Metric | Value |\n|---|---:|\n| Recall | 0.9 |"),
        ]

        result = self.processor.process(blocks)

        self.assertEqual([table.label for table in result.tables], ["Table 8", "Table 9"])
        self.assertEqual(result.tables[1].source_block_ids, ["block_000023"])
        self.assertEqual(result.tables[1].caption_block_ids, ["block_000022"])
        self.assertEqual(result.tables[1].status, "caption_attached")

    def test_retypes_heatmap_table_when_caption_identifies_a_figure(self):
        """AC-105: a Figure heatmap must not remain a logical table."""
        blocks = [
            block(30, "table", "Figure 3: ASR matrix.\n\n| Defence | ASR |\n|---|---:|\n| Ours | 0 |"),
            block(31, "caption", "Figure 3: ASR matrix."),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(result.tables, [])
        self.assertEqual(result.blocks[0].type, "figure")
        self.assertEqual(result.blocks[0].relations["postprocess_status"], "retyped_as_figure")
        self.assertEqual(result.blocks[0].relations["caption_block_ids"], ["block_000031"])

    def test_resolves_caption_collision_between_adjacent_tables(self):
        """A duplicated next-table caption must not steal the current table."""
        blocks = [
            block(
                40,
                "table",
                "Table 5: Propagation outcome.\n\n"
                "| Scenario | Verdict |\n|---|---|\n"
                "| Table 4: Authority repair POC. | allow |",
            ),
            block(41, "caption", "Table 5: Propagation outcome."),
            block(42, "table", "| tau | 1 | 2 |\n|---|---:|---:|\n| 0.5 | 1 | 1 |"),
        ]

        result = self.processor.process(blocks)

        self.assertEqual([table.label for table in result.tables], ["Table 4", "Table 5"])
        self.assertEqual(result.tables[0].source_block_ids, ["block_000040"])
        self.assertEqual(result.tables[0].status, "caption_collision_recovered")
        self.assertEqual(result.tables[1].source_block_ids, ["block_000042"])
        self.assertEqual(result.tables[1].caption_block_ids, ["block_000041"])
        self.assertIn("caption_collision", result.blocks[0].relations["warnings"])

    def test_processing_is_idempotent(self):
        blocks = [
            block(50, "table", "Table 1: Scores.\n\n| Model | Score |\n|---|---:|\n| Ours | 1 |"),
            block(51, "caption", "Table 1: Scores."),
        ]

        first = self.processor.process(blocks)
        second = self.processor.process(first.blocks)

        self.assertEqual(first.tables, second.tables)
        self.assertEqual(first.blocks, second.blocks)

    def test_cross_reference_inside_caption_does_not_steal_another_table(self):
        blocks = [
            block(60, "table", "Table 5: Baseline.\n\n| A |\n|---|\n| 1 |"),
            block(61, "caption", "Table 5: Baseline."),
            block(
                62,
                "table",
                "Table 6: Ablation; cell semantics match Table 5.\n\n"
                "| B |\n|---|\n| 2 |",
            ),
            block(63, "caption", "Table 6: Ablation; cell semantics match Table 5."),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(result.tables[0].source_block_ids, ["block_000060"])
        self.assertEqual(result.tables[0].caption_block_ids, ["block_000061"])
        self.assertEqual(result.tables[1].source_block_ids, ["block_000062"])
        self.assertEqual(result.tables[1].caption_block_ids, ["block_000063"])

    def test_full_identifiers_keep_decimal_tables_in_distinct_caption_groups(self):
        """AC-TABLE-OWN-001: Table 3.1 and 3.2 are distinct logical tables."""
        blocks = [
            block(70, "caption", "Table 3.1: Zero-shot results."),
            block(71, "table", "| Model | Score |\n|---|---:|\n| A | 1 |"),
            block(72, "caption", "Table 3.2: Few-shot results."),
            block(73, "table", "| Model | Score |\n|---|---:|\n| B | 2 |"),
        ]

        result = self.processor.process(blocks)

        self.assertEqual([table.label for table in result.tables], ["Table 3.1", "Table 3.2"])
        self.assertEqual([table.identifier for table in result.tables], ["3.1", "3.2"])
        self.assertEqual(result.tables[0].source_block_ids, ["block_000071"])
        self.assertEqual(result.tables[0].caption_block_ids, ["block_000070"])
        self.assertEqual(result.tables[1].source_block_ids, ["block_000073"])
        self.assertEqual(result.tables[1].caption_block_ids, ["block_000072"])

        repeated = self.processor.process(result.blocks)
        self.assertEqual(result.tables, repeated.tables)
        self.assertEqual(result.blocks, repeated.blocks)

    def test_leading_caption_owns_contiguous_unlabelled_tables_until_boundary(self):
        """AC-TABLE-OWN-002: one caption owns its bounded following table region."""
        blocks = [
            block(80, "caption", "Table A.1: Results split into two physical grids."),
            block(81, "table", "| A | B |\n|---|---|\n| 1 | 2 |"),
            block(82, "table", "| C | D |\n|---|---|\n| 3 | 4 |"),
            block(83, "paragraph", "The next grid is unrelated."),
            block(84, "table", "| X | Y |\n|---|---|\n| 5 | 6 |"),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(len(result.tables), 2)
        self.assertEqual(result.tables[0].label, "Table A.1")
        self.assertEqual(
            result.tables[0].source_block_ids,
            ["block_000081", "block_000082"],
        )
        self.assertEqual(result.tables[0].caption_block_ids, ["block_000080"])
        self.assertEqual(result.tables[1].source_block_ids, ["block_000084"])
        self.assertEqual(result.blocks[1].relations["fragment_count"], 2)
        self.assertEqual(result.blocks[2].relations["fragment_index"], 2)

    def test_trailing_caption_owns_contiguous_unlabelled_tables_above(self):
        """AC-TABLE-OWN-003: a trailing caption can own a bounded preceding group."""
        blocks = [
            block(90, "table", "| A | B |\n|---|---|\n| 1 | 2 |"),
            block(91, "table", "| C | D |\n|---|---|\n| 3 | 4 |"),
            block(92, "caption", "Table S1: Supplementary results."),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(len(result.tables), 1)
        self.assertEqual(result.tables[0].label, "Table S1")
        self.assertEqual(result.tables[0].identifier, "S1")
        self.assertEqual(
            result.tables[0].source_block_ids,
            ["block_000090", "block_000091"],
        )
        self.assertEqual(result.tables[0].caption_block_ids, ["block_000092"])

    def test_caption_region_stops_at_a_different_explicit_table(self):
        """AC-TABLE-OWN-004: ownership never crosses another table identity."""
        blocks = [
            block(100, "caption", "Table 1: Primary results."),
            block(101, "table", "| A |\n|---|\n| 1 |"),
            block(102, "table", "Table 2: Ablation.\n| B |\n|---|\n| 2 |"),
            block(103, "caption", "Table 2: Ablation."),
        ]

        result = self.processor.process(blocks)

        self.assertEqual([table.label for table in result.tables], ["Table 1", "Table 2"])
        self.assertEqual(result.tables[0].source_block_ids, ["block_000101"])
        self.assertEqual(result.tables[1].source_block_ids, ["block_000102"])
        self.assertEqual(result.tables[0].caption_block_ids, ["block_000100"])
        self.assertEqual(result.tables[1].caption_block_ids, ["block_000103"])

    def test_leading_caption_does_not_absorb_an_unlabelled_table_above(self):
        """AC-TABLE-OWN-005: caption ownership follows its selected direction."""
        blocks = [
            block(110, "table", "| Previous |\n|---|\n| unrelated |"),
            block(111, "caption", "Table 7: Current results."),
            block(112, "table", "| Current |\n|---|\n| result |"),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(len(result.tables), 2)
        self.assertEqual(result.tables[0].source_block_ids, ["block_000110"])
        self.assertEqual(result.tables[0].caption_block_ids, [])
        self.assertEqual(result.tables[1].label, "Table 7")
        self.assertEqual(result.tables[1].source_block_ids, ["block_000112"])
        self.assertEqual(result.tables[1].caption_block_ids, ["block_000111"])

    def test_two_captions_cannot_both_own_the_same_physical_table(self):
        """AC-TABLE-OWN-006: one physical table has one primary caption."""
        blocks = [
            block(120, "caption", "Table 8: Caption before the table."),
            block(121, "table", "| Result |\n|---|\n| 8 |"),
            block(122, "caption", "Table 8: Duplicate caption after the table."),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(len(result.tables), 1)
        self.assertEqual(result.tables[0].label, "Table 8")
        self.assertEqual(result.tables[0].source_block_ids, ["block_000121"])
        self.assertEqual(len(result.tables[0].caption_block_ids), 1)
        self.assertTrue(
            any("caption target already owned" in warning for warning in result.warnings)
        )


if __name__ == "__main__":
    unittest.main()
