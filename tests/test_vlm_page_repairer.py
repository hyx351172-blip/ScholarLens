from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_DIR = PROJECT_ROOT / "backend" / "Information-Extraction" / "unified"
sys.path.insert(0, str(UNIFIED_DIR))

from parsers.docling_parser import DoclingParseResult  # noqa: E402
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
from parsers.vlm_page_repairer import (  # noqa: E402
    VLMPageRepairConfig,
    VLMPageRepairer,
)


class FakeVLMClient:
    def __init__(self, payloads: dict[int, dict]) -> None:
        self.payloads = payloads
        self.calls: list[dict] = []

    def analyze_page(self, *, page: int, image_data_url: str, context: dict) -> dict:
        self.calls.append(
            {"page": page, "image_data_url": image_data_url, "context": context}
        )
        return copy.deepcopy(self.payloads.get(page, {}))


def block(
    block_id: str,
    order: int,
    block_type: str,
    text: str,
    page: int,
) -> ContentBlock:
    return ContentBlock(
        block_id=block_id,
        order=order,
        type=block_type,
        text=text,
        page=page,
        bbox=[10.0, 10.0 + order, 100.0, 30.0 + order],
        section_path=[],
    )


def fixture() -> DoclingParseResult:
    blocks = [
        block("title", 0, "title", "A Reliable Paper Title", 1),
        block("abstract_heading", 1, "heading", "Abstract", 1),
        block("abstract_body", 2, "paragraph", "This study evaluates robust repair.", 1),
        block("table_caption", 3, "caption", "Table 1: Main results", 2),
        block("table_body", 4, "table", "| Model | Score |\n|---|---|\n| A | 9 |", 2),
        block("figure_body", 5, "figure", "", 3),
        block("figure_caption", 6, "caption", "Figure 1: System overview", 3),
    ]
    document = PaperDocument(
        schema_version="1.0",
        paper_id="paper",
        file_id="file",
        filename="paper.pdf",
        parser=ParserInfo(),
        metadata=PaperMetadata(
            title="https://arxiv.org/abs/1234.5678",
            authors=[],
            abstract=None,
        ),
        sections=[],
        blocks=blocks,
        quality=ParseQualityReport(total_pages=3, parsed_pages=3),
    )
    return DoclingParseResult(
        document=document,
        markdown="",
        raw_document={},
        logical_tables=[
            LogicalTable(
                table_id="table_1",
                label=None,
                number=None,
                caption=None,
                page_start=2,
                page_end=2,
                section_path=[],
                source_block_ids=["table_body"],
                caption_block_ids=[],
                text=blocks[4].text,
                status="unlabelled",
            )
        ],
        logical_figures=[
            LogicalFigure(
                figure_id="figure_1",
                label=None,
                number=None,
                caption=None,
                page=3,
                section_path=[],
                source_block_ids=["figure_body"],
                caption_block_ids=[],
                explanation_block_ids=[],
                status="unlabelled",
            )
        ],
        logical_formulas=[
            LogicalFormula(
                formula_id="formula_1",
                equation_number=None,
                text="x = 1",
                page=3,
                section_path=[],
                source_block_id="abstract_body",
                context_block_ids=["abstract_body"],
                status="bound",
            )
        ],
    )


class VLMPageRepairerTests(unittest.TestCase):
    def test_repairs_metadata_and_caption_bindings_using_existing_blocks(self) -> None:
        """AC-VLM-001/002: difficult pages are repaired with auditable block IDs."""
        parsed = fixture()
        original = copy.deepcopy(parsed)
        client = FakeVLMClient(
            {
                1: {
                    "title_block_ids": ["title"],
                    "abstract_block_ids": ["abstract_body"],
                    "bindings": [],
                },
                2: {
                    "title_block_ids": [],
                    "abstract_block_ids": [],
                    "bindings": [
                        {
                            "kind": "table",
                            "object_block_ids": ["table_body"],
                            "caption_block_ids": ["table_caption"],
                            "confidence": 0.96,
                            "reason": "Caption is directly above the table.",
                        }
                    ],
                },
                3: {
                    "title_block_ids": [],
                    "abstract_block_ids": [],
                    "bindings": [
                        {
                            "kind": "figure",
                            "object_block_ids": ["figure_body"],
                            "caption_block_ids": ["figure_caption"],
                            "confidence": 0.92,
                            "reason": "The numbered caption is below the figure.",
                        }
                    ],
                },
            }
        )
        repairer = VLMPageRepairer(
            client=client,
            config=VLMPageRepairConfig(min_confidence=0.8, max_pages=8),
            renderer=lambda _path, page, _dpi: f"data:image/png;base64,page-{page}",
        )

        result = repairer.repair(Path("paper.pdf"), parsed)

        self.assertEqual([call["page"] for call in client.calls], [1, 2, 3])
        self.assertEqual(result.parse_result.document.metadata.title, "A Reliable Paper Title")
        self.assertEqual(
            result.parse_result.document.metadata.abstract,
            "This study evaluates robust repair.",
        )
        self.assertEqual(result.parse_result.logical_tables[0].caption_block_ids, ["table_caption"])
        self.assertEqual(result.parse_result.logical_figures[0].caption_block_ids, ["figure_caption"])
        repaired_blocks = {
            item.block_id: item for item in result.parse_result.document.blocks
        }
        self.assertEqual(
            repaired_blocks["table_body"].relations["caption_block_ids"],
            ["table_caption"],
        )
        self.assertEqual(
            repaired_blocks["table_caption"].relations["describes_block_ids"],
            ["table_body"],
        )
        self.assertEqual(len(result.accepted_repairs), 4)
        self.assertEqual(parsed.document.metadata, original.document.metadata)
        self.assertEqual(parsed.logical_tables, original.logical_tables)

    def test_rejects_low_confidence_unknown_and_cross_page_relationships(self) -> None:
        """AC-VLM-003: hallucinated or unsafe relationships never mutate evidence."""
        parsed = fixture()
        client = FakeVLMClient(
            {
                1: {
                    "title_block_ids": ["unknown"],
                    "abstract_block_ids": [],
                    "bindings": [],
                },
                2: {
                    "bindings": [
                        {
                            "kind": "table",
                            "object_block_ids": ["table_body"],
                            "caption_block_ids": ["figure_caption"],
                            "confidence": 0.99,
                            "reason": "Wrong page.",
                        },
                        {
                            "kind": "table",
                            "object_block_ids": ["table_body"],
                            "caption_block_ids": ["table_caption"],
                            "confidence": 0.2,
                            "reason": "Low confidence.",
                        },
                    ]
                },
                3: {"bindings": []},
            }
        )
        result = VLMPageRepairer(
            client=client,
            config=VLMPageRepairConfig(min_confidence=0.8),
            renderer=lambda _path, page, _dpi: f"data:image/png;base64,page-{page}",
        ).repair(Path("paper.pdf"), parsed)

        self.assertEqual(result.parse_result.logical_tables[0].caption_block_ids, [])
        self.assertEqual(result.parse_result.document.metadata.title, parsed.document.metadata.title)
        self.assertEqual(result.accepted_repairs, [])
        self.assertGreaterEqual(len(result.rejected_repairs), 3)

    def test_page_selection_is_deduplicated_limited_and_deterministic(self) -> None:
        """AC-VLM-004: only high-value difficult pages are sent to the paid model."""
        parsed = fixture()
        repairer = VLMPageRepairer(
            client=FakeVLMClient({}),
            config=VLMPageRepairConfig(max_pages=2),
            renderer=lambda _path, page, _dpi: f"data:image/png;base64,page-{page}",
        )

        self.assertEqual(repairer.select_candidate_pages(parsed), [1, 2])


if __name__ == "__main__":
    unittest.main()
