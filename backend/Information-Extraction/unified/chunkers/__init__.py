"""Structure-aware chunking for canonical ScholarLens paper documents."""

from .structure_aware_chunker import (
    ChunkingConfig,
    ChunkingResult,
    ScientificChunk,
    StructureAwareChunker,
)

__all__ = [
    "ChunkingConfig",
    "ChunkingResult",
    "ScientificChunk",
    "StructureAwareChunker",
]
