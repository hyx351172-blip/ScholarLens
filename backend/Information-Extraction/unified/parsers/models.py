"""Parser-side data contracts.

These models intentionally stop at document blocks. Chunking and retrieval models
belong to later pipeline stages and are not part of this module.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PaperMetadata:
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    abstract: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    language: Optional[str] = None


@dataclass
class Section:
    section_id: str
    title: str
    level: int
    parent_id: Optional[str] = None
    page: Optional[int] = None
    kind: str = "regular"


@dataclass
class ContentBlock:
    block_id: str
    order: int
    type: str
    text: str
    page: Optional[int] = None
    bbox: Optional[List[float]] = None
    section_path: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    source_label: Optional[str] = None
    relations: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParserInfo:
    name: str = "docling"
    version: str = "unknown"
    table_mode: str = "accurate"
    ocr_enabled: bool = False


@dataclass
class ParseQualityReport:
    total_pages: int = 0
    parsed_pages: int = 0
    total_blocks: int = 0
    block_counts: Dict[str, int] = field(default_factory=dict)
    provenance_coverage: float = 0.0
    empty_page_numbers: List[int] = field(default_factory=list)
    empty_block_count: int = 0
    duration_seconds: float = 0.0
    reading_order_pages_reordered: int = 0
    reading_order_page_methods: Dict[int, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PaperDocument:
    schema_version: str
    paper_id: str
    file_id: str
    filename: str
    parser: ParserInfo
    metadata: PaperMetadata
    sections: List[Section]
    blocks: List[ContentBlock]
    quality: ParseQualityReport

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
