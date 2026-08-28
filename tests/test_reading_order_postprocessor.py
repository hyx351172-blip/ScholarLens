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
from parsers.reading_order_postprocessor import ReadingOrderPostProcessor  # noqa: E402


def block(order, text, bbox, *, page=1, block_type="paragraph"):
    return ContentBlock(
        block_id=f"block_{order:06d}",
        order=order,
        type=block_type,
        text=text,
        page=page,
        bbox=bbox,
        relations={},
    )


class ReadingOrderPostProcessorTests(unittest.TestCase):
    def setUp(self):
        self.processor = ReadingOrderPostProcessor()

    def test_orders_single_column_from_top_to_bottom(self):
        blocks = [
            block(0, "bottom", [50, 300, 550, 250]),
            block(1, "top", [50, 700, 550, 650]),
            block(2, "middle", [50, 500, 550, 450]),
        ]

        result = self.processor.process(blocks)

        self.assertEqual([item.text for item in result.blocks], ["top", "middle", "bottom"])
        self.assertEqual(result.page_methods[1], "single_column_geometry")
        self.assertEqual(
            [item.relations["original_order"] for item in result.blocks],
            [1, 2, 0],
        )

    def test_reads_complete_left_column_before_right_column(self):
        blocks = [
            block(0, "right top", [320, 700, 560, 640]),
            block(1, "left bottom", [50, 500, 290, 440]),
            block(2, "title", [50, 780, 560, 740], block_type="heading"),
            block(3, "right bottom", [320, 500, 560, 440]),
            block(4, "left top", [50, 700, 290, 640]),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(
            [item.text for item in result.blocks],
            ["title", "left top", "left bottom", "right top", "right bottom"],
        )
        self.assertEqual(result.page_methods[1], "two_column_geometry")
        self.assertEqual(result.blocks[1].relations["column_index"], 0)
        self.assertEqual(result.blocks[3].relations["column_index"], 1)

    def test_full_width_figure_splits_two_column_page_into_bands(self):
        blocks = [
            block(0, "lower right", [320, 220, 560, 160]),
            block(1, "upper right", [320, 700, 560, 620]),
            block(2, "figure", [50, 500, 560, 360], block_type="figure"),
            block(3, "lower left", [50, 220, 290, 160]),
            block(4, "upper left", [50, 700, 290, 620]),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(
            [item.text for item in result.blocks],
            ["upper left", "upper right", "figure", "lower left", "lower right"],
        )
        self.assertEqual(result.blocks[2].relations["column_index"], -1)
        self.assertEqual(result.blocks[2].relations["reading_band_index"], 1)

    def test_page_with_missing_bbox_falls_back_to_original_order(self):
        blocks = [
            block(0, "first", [50, 100, 550, 50]),
            block(1, "second", None),
            block(2, "third", [50, 700, 550, 650]),
        ]

        result = self.processor.process(blocks)

        self.assertEqual([item.text for item in result.blocks], ["first", "second", "third"])
        self.assertEqual(result.page_methods[1], "original_order_fallback")
        self.assertTrue(result.warnings)

    def test_small_midpoint_overlap_does_not_create_false_spanning_bands(self):
        blocks = [
            block(0, "left top", [49, 735, 299, 677]),
            block(1, "left bottom", [4, 560, 299, 490]),
            block(2, "right top", [334, 733, 462, 684], block_type="code"),
            block(3, "right bottom", [314, 672, 565, 628]),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(
            [item.text for item in result.blocks],
            ["left top", "left bottom", "right top", "right bottom"],
        )
        self.assertTrue(all(item.relations["column_index"] >= 0 for item in result.blocks))

    def test_preserves_contiguous_multipart_table_group(self):
        blocks = [
            block(0, "Table 4 part one", [50, 700, 560, 520], block_type="table"),
            block(1, "Table 4 caption", [50, 490, 560, 460], block_type="caption"),
            block(2, "Table 4 part two", [50, 510, 560, 300], block_type="table"),
            block(3, "Following text", [50, 280, 560, 220]),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(
            [item.block_id for item in result.blocks[:3]],
            ["block_000000", "block_000001", "block_000002"],
        )

    def test_keeps_top_author_blocks_before_abstract_across_columns(self):
        blocks = [
            block(0, "paper title", [130, 720, 480, 680], block_type="heading"),
            block(1, "left author", [65, 665, 220, 630]),
            block(2, "middle author", [150, 608, 300, 575]),
            block(3, "Abstract", [54, 554, 100, 544], block_type="heading"),
            block(4, "abstract text", [54, 538, 296, 194]),
            block(5, "1 Introduction", [54, 171, 142, 161], block_type="heading"),
            block(6, "introduction left", [54, 155, 296, 74]),
            block(7, "introduction right", [318, 517, 560, 78]),
            block(8, "right author", [429, 665, 512, 630]),
        ]

        result = self.processor.process(blocks)

        abstract_index = next(
            index for index, item in enumerate(result.blocks) if item.text == "Abstract"
        )
        author_indexes = [
            next(index for index, item in enumerate(result.blocks) if item.text == text)
            for text in ("left author", "middle author", "right author")
        ]
        self.assertTrue(all(index < abstract_index for index in author_indexes))

    def test_pages_never_interleave_and_processing_is_idempotent(self):
        blocks = [
            block(0, "page two", [50, 700, 550, 650], page=2),
            block(1, "page one bottom", [50, 300, 550, 250], page=1),
            block(2, "page one top", [50, 700, 550, 650], page=1),
        ]

        first = self.processor.process(blocks)
        second = self.processor.process(first.blocks)

        self.assertEqual(
            [item.text for item in first.blocks],
            ["page one top", "page one bottom", "page two"],
        )
        self.assertEqual(first.blocks, second.blocks)


if __name__ == "__main__":
    unittest.main()
