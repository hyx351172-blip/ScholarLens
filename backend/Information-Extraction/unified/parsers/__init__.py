"""Structured PDF parser adapters used by ScholarLens."""

from .docling_parser import DoclingParser, DoclingParseResult, save_parse_result
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
