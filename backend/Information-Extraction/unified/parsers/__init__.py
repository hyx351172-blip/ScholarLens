"""Structured PDF parser adapters used by ScholarLens."""

from .docling_parser import DoclingParser, DoclingParseResult, save_parse_result
from .evidence_context_postprocessor import (
    EvidenceContextPostProcessor,
    EvidenceContextResult,
    LogicalFigure,
    LogicalFormula,
)
from .models import ContentBlock, PaperDocument, PaperMetadata, ParseQualityReport
from .reading_order_postprocessor import (
    ReadingOrderPostProcessor,
    ReadingOrderResult,
)
from .section_hierarchy_postprocessor import (
    SectionHierarchyPostProcessor,
    SectionHierarchyResult,
)
from .table_postprocessor import LogicalTable, TablePostProcessResult, TablePostProcessor
from .vlm_page_repairer import (
    OpenAICompatibleVLMClient,
    VLMPageRepairConfig,
    VLMPageRepairResult,
    VLMPageRepairer,
    render_pdf_page_data_url,
)

__all__ = [
    "ContentBlock",
    "DoclingParser",
    "DoclingParseResult",
    "EvidenceContextPostProcessor",
    "EvidenceContextResult",
    "LogicalFigure",
    "LogicalFormula",
    "PaperDocument",
    "PaperMetadata",
    "ParseQualityReport",
    "ReadingOrderPostProcessor",
    "ReadingOrderResult",
    "SectionHierarchyPostProcessor",
    "SectionHierarchyResult",
    "LogicalTable",
    "TablePostProcessResult",
    "TablePostProcessor",
    "OpenAICompatibleVLMClient",
    "VLMPageRepairConfig",
    "VLMPageRepairResult",
    "VLMPageRepairer",
    "render_pdf_page_data_url",
    "save_parse_result",
]
