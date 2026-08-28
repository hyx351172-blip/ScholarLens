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


if __name__ == "__main__":
    unittest.main()
