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

from parsers.evidence_context_postprocessor import (  # noqa: E402
    EvidenceContextPostProcessor,
)
from parsers.models import ContentBlock  # noqa: E402


def block(order, block_type, text="", *, page=1, section_path=None, relations=None):
    return ContentBlock(
        block_id=f"block_{order:06d}",
        order=order,
        type=block_type,
        text=text,
        page=page,
        bbox=[50.0, 700.0 - order, 550.0, 680.0 - order],
        section_path=section_path or ["4 Experiments", "4.2 Results"],
        relations=relations or {},
    )


class EvidenceContextPostProcessorTests(unittest.TestCase):
    def setUp(self):
        self.processor = EvidenceContextPostProcessor()

    def test_binds_figure_caption_and_explicit_explanation_bidirectionally(self):
        blocks = [
            block(10, "figure"),
            block(11, "caption", "Figure 2: Retrieval architecture."),
            block(12, "paragraph", "As shown in Figure 2, retrieval has two stages."),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(len(result.figures), 1)
        figure = result.figures[0]
        self.assertEqual(figure.label, "Figure 2")
        self.assertEqual(figure.source_block_ids, ["block_000010"])
        self.assertEqual(figure.caption_block_ids, ["block_000011"])
        self.assertEqual(figure.explanation_block_ids, ["block_000012"])
        self.assertEqual(result.blocks[1].type, "figure_caption")
        self.assertEqual(result.blocks[0].relations["figure_id"], figure.figure_id)
        self.assertEqual(result.blocks[1].relations["describes_block_ids"], ["block_000010"])
        self.assertEqual(result.blocks[2].relations["figure_ids"], [figure.figure_id])

    def test_matches_multiple_figures_to_nearest_captions_on_same_page(self):
        blocks = [
            block(20, "figure"),
            block(21, "caption", "Figure 1: First result."),
            block(22, "figure"),
            block(23, "caption", "Figure 2: Second result."),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(
            [figure.caption_block_ids for figure in result.figures],
            [["block_000021"], ["block_000023"]],
        )
        self.assertEqual([figure.label for figure in result.figures], ["Figure 1", "Figure 2"])

    def test_preserves_table_retyped_figure_relations(self):
        blocks = [
            block(
                30,
                "figure",
                "Figure 3: ASR matrix.",
                relations={
                    "original_type": "table",
                    "caption_block_ids": ["block_000031"],
                    "postprocess_status": "retyped_as_figure",
                },
            ),
            block(31, "caption", "Figure 3: ASR matrix."),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(result.blocks[0].relations["original_type"], "table")
        self.assertEqual(result.figures[0].caption_block_ids, ["block_000031"])

    def test_binds_formula_to_nearest_context_in_same_section(self):
        blocks = [
            block(40, "paragraph", "We define the retrieval score as follows."),
            block(41, "formula", "Score(m,q,a) = s(m,q)ρ(m,a). (3)"),
            block(42, "paragraph", "In Equation (3), rho is the policy factor."),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(len(result.formulas), 1)
        formula = result.formulas[0]
        self.assertEqual(formula.equation_number, "3")
        self.assertEqual(
            formula.context_block_ids,
            ["block_000040", "block_000042"],
        )
        self.assertEqual(result.blocks[0].relations["formula_ids"], [formula.formula_id])
        self.assertEqual(result.blocks[2].relations["formula_ids"], [formula.formula_id])

    def test_formula_context_does_not_cross_heading_or_another_formula(self):
        blocks = [
            block(50, "paragraph", "First formula introduction.", section_path=["3 Method"]),
            block(51, "formula", "a = b. (1)", section_path=["3 Method"]),
            block(52, "heading", "4 Experiments", section_path=["4 Experiments"]),
            block(53, "paragraph", "Unrelated text.", section_path=["4 Experiments"]),
        ]

        result = self.processor.process(blocks)

        self.assertEqual(result.formulas[0].context_block_ids, ["block_000050"])
        self.assertNotIn("formula_ids", result.blocks[3].relations)

    def test_processing_is_idempotent(self):
        blocks = [
            block(60, "figure"),
            block(61, "caption", "Figure 4: Overview."),
            block(62, "paragraph", "Figure 4 summarizes the workflow."),
            block(63, "formula", "y = f(x). (4)"),
            block(64, "paragraph", "Equation (4) defines the output."),
        ]

        first = self.processor.process(blocks)
        second = self.processor.process(first.blocks)

        self.assertEqual(first.blocks, second.blocks)
        self.assertEqual(first.figures, second.figures)
        self.assertEqual(first.formulas, second.formulas)


if __name__ == "__main__":
    unittest.main()
