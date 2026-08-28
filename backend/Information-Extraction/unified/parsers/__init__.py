"""Structured PDF parser adapters used by ScholarLens."""

from .docling_parser import DoclingParser, DoclingParseResult, save_parse_result
from .evidence_context_postprocessor import (
    EvidenceContextPostProcessor,
    EvidenceContextResult,
    LogicalFigure,
    LogicalFormula,
)
from .models import ContentBlock, PaperDocument, PaperMetadata, ParseQualityReport
from .section_hierarchy_postprocessor import (
    SectionHierarchyPostProcessor,
    SectionHierarchyResult,
)
from .table_postprocessor import LogicalTable, TablePostProcessResult, TablePostProcessor

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
    "SectionHierarchyPostProcessor",
    "SectionHierarchyResult",
    "LogicalTable",
    "TablePostProcessResult",
    "TablePostProcessor",
    "save_parse_result",
]
