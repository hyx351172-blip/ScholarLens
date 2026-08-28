"""Structured PDF parser adapters used by ScholarLens."""

from .docling_parser import DoclingParser, DoclingParseResult, save_parse_result
from .models import ContentBlock, PaperDocument, PaperMetadata, ParseQualityReport

__all__ = [
    "ContentBlock",
    "DoclingParser",
    "DoclingParseResult",
    "PaperDocument",
    "PaperMetadata",
    "ParseQualityReport",
    "save_parse_result",
]
