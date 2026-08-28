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
from parsers.section_hierarchy_postprocessor import (  # noqa: E402
    SectionHierarchyPostProcessor,
)


def block(order, block_type, text, *, page=1):
    return ContentBlock(
        block_id=f"block_{order:06d}",
        order=order,
        type=block_type,
        text=text,
        page=page,
        bbox=[50.0, 700.0 - order, 550.0, 680.0 - order],
        relations={"docling_heading_level": 1} if block_type == "heading" else {},
    )


class SectionHierarchyPostProcessorTests(unittest.TestCase):
    def setUp(self):
        self.processor = SectionHierarchyPostProcessor()

    def test_builds_numbered_tree_and_assigns_paths_to_all_blocks(self):
        blocks = [
            block(0, "heading", "A Reliable Paper"),
            block(1, "heading", "Abstract"),
            block(2, "paragraph", "Abstract text."),
            block(3, "heading", "1 Introduction"),
            block(4, "paragraph", "Introduction text."),
            block(5, "heading", "2 Method"),
            block(6, "heading", "2.1 Retrieval"),
            block(7, "paragraph", "Retrieval text."),
            block(8, "heading", "2.1.1 Dense Retrieval"),
            block(9, "formula", "score(q, d)"),
            block(10, "heading", "2.2 Generation"),
            block(11, "table", "| Model | Score |"),
            block(12, "heading", "3 Conclusion"),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(result.blocks[0].type, "title")
        self.assertEqual(result.blocks[0].section_path, [])
        sections = {section.title: section for section in result.sections}
        self.assertNotIn("A Reliable Paper", sections)
        self.assertEqual(sections["2 Method"].level, 1)
        self.assertEqual(sections["2.1 Retrieval"].level, 2)
        self.assertEqual(
            sections["2.1 Retrieval"].parent_id,
            sections["2 Method"].section_id,
        )
        self.assertEqual(sections["2.1.1 Dense Retrieval"].level, 3)
        self.assertEqual(
            sections["2.1.1 Dense Retrieval"].parent_id,
            sections["2.1 Retrieval"].section_id,
        )
        self.assertEqual(
            result.blocks[9].section_path,
            ["2 Method", "2.1 Retrieval", "2.1.1 Dense Retrieval"],
        )
        self.assertEqual(
            result.blocks[11].section_path,
            ["2 Method", "2.2 Generation"],
        )

    def test_splits_plausible_merged_heading_without_splitting_numeric_phrase(self):
        blocks = [
            block(0, "heading", "MAP-Graph"),
            block(
                1,
                "heading",
                "2 Background and Problem Formulation 2.1 Multi-Agent Shared Memory",
            ),
            block(2, "paragraph", "Shared memory text."),
            block(3, "heading", "3 Evaluation with 2 Models"),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(
            [section.title for section in result.sections],
            [
                "2 Background and Problem Formulation",
                "2.1 Multi-Agent Shared Memory",
                "3 Evaluation with 2 Models",
            ],
        )
        self.assertEqual(
            result.blocks[1].relations["section_postprocess_status"],
            "split_merged_heading",
        )
        self.assertEqual(
            result.blocks[2].section_path,
            [
                "2 Background and Problem Formulation",
                "2.1 Multi-Agent Shared Memory",
            ],
        )

    def test_unnumbered_heading_becomes_sibling_under_nearest_numbered_parent(self):
        blocks = [
            block(0, "heading", "MemLineage"),
            block(1, "heading", "1 Introduction"),
            block(2, "heading", "Contributions."),
            block(3, "paragraph", "Contribution text."),
            block(4, "heading", "Motivation."),
            block(5, "paragraph", "Motivation text."),
            block(6, "heading", "2 Threat Model"),
        ]

        result = self.processor.process(blocks)

        sections = {section.title: section for section in result.sections}
        self.assertEqual(sections["Contributions."].level, 2)
        self.assertEqual(
            sections["Contributions."].parent_id,
            sections["1 Introduction"].section_id,
        )
        self.assertEqual(sections["Motivation."].level, 2)
        self.assertEqual(
            sections["Motivation."].parent_id,
            sections["1 Introduction"].section_id,
        )
        self.assertEqual(
            result.blocks[4].relations["section_postprocess_status"],
            "hierarchy_fallback",
        )

    def test_out_of_order_abstract_does_not_steal_following_subheading(self):
        blocks = [
            block(0, "heading", "MemLineage"),
            block(1, "heading", "1 Introduction"),
            block(2, "heading", "Abstract"),
            block(3, "paragraph", "Abstract text."),
            block(4, "heading", "Contributions."),
            block(5, "paragraph", "Contribution text."),
            block(6, "heading", "2 Threat Model"),
        ]

        result = self.processor.process(blocks)

        sections = {section.title: section for section in result.sections}
        self.assertEqual(
            sections["Contributions."].parent_id,
            sections["1 Introduction"].section_id,
        )
        self.assertEqual(
            result.blocks[5].section_path,
            ["1 Introduction", "Contributions."],
        )

    def test_processing_is_idempotent(self):
        blocks = [
            block(0, "heading", "Paper Title"),
            block(1, "heading", "1 Introduction"),
            block(2, "heading", "1.1 Motivation"),
            block(3, "paragraph", "Text."),
        ]

        first = self.processor.process(blocks)
        second = self.processor.process(first.blocks)

        self.assertEqual(first.blocks, second.blocks)
        self.assertEqual(first.sections, second.sections)


if __name__ == "__main__":
    unittest.main()
