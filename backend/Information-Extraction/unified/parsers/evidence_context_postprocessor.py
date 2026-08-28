"""Bind figures and formulas to captions and explanatory text blocks."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .models import ContentBlock


_FIGURE_LABEL_RE = re.compile(
    r"^\s*(?:Figure|Fig\.)\s*(\d+)\s*[:.]", re.IGNORECASE
)
_EQUATION_NUMBER_RE = re.compile(r"\((\d+[a-z]?)\)\s*[.,;]?\s*$", re.IGNORECASE)
_CONTEXT_TYPES = {"paragraph", "list_item"}


@dataclass
class LogicalFigure:
    figure_id: str
    label: Optional[str]
    number: Optional[int]
    caption: Optional[str]
    page: Optional[int]
    section_path: List[str]
    source_block_ids: List[str]
    caption_block_ids: List[str]
    explanation_block_ids: List[str]
    status: str
    is_generated_description: bool = False
    warnings: List[str] = field(default_factory=list)


@dataclass
class LogicalFormula:
    formula_id: str
    equation_number: Optional[str]
    text: str
    page: Optional[int]
    section_path: List[str]
    source_block_id: str
    context_block_ids: List[str]
    status: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class EvidenceContextResult:
    blocks: List[ContentBlock]
    figures: List[LogicalFigure]
    formulas: List[LogicalFormula]
    warnings: List[str] = field(default_factory=list)


class EvidenceContextPostProcessor:
    """Create deterministic, auditable evidence relationships."""

    def __init__(self, *, reference_window: int = 12) -> None:
        self.reference_window = max(1, reference_window)

    def process(self, blocks: Sequence[ContentBlock]) -> EvidenceContextResult:
        processed = [
            replace(block, relations=copy.deepcopy(block.relations)) for block in blocks
        ]
        figures, figure_warnings = self._bind_figures(processed)
        formulas, formula_warnings = self._bind_formulas(processed)
        return EvidenceContextResult(
            blocks=processed,
            figures=figures,
            formulas=formulas,
            warnings=figure_warnings + formula_warnings,
        )

    def _bind_figures(
        self, blocks: List[ContentBlock]
    ) -> Tuple[List[LogicalFigure], List[str]]:
        figure_indexes = [
            index for index, block in enumerate(blocks) if block.type == "figure"
        ]
        caption_labels = {
            index: _figure_number(block.text)
            for index, block in enumerate(blocks)
            if block.type in {"caption", "figure_caption"}
        }
        caption_labels = {
            index: number
            for index, number in caption_labels.items()
            if number is not None
        }
        caption_target: Dict[int, int] = {}
        claimed_figures: Set[int] = set()
        warnings: List[str] = []

        for caption_index, number in caption_labels.items():
            target = self._find_figure_target(
                caption_index,
                number,
                blocks,
                figure_indexes,
                claimed_figures,
            )
            if target is None:
                warnings.append(
                    f"{blocks[caption_index].block_id}: Figure {number} caption "
                    "has no matching figure block"
                )
                continue
            caption_target[caption_index] = target
            claimed_figures.add(target)

        logical_figures: List[LogicalFigure] = []
        for figure_index in figure_indexes:
            figure_block = blocks[figure_index]
            caption_indexes = sorted(
                index for index, target in caption_target.items() if target == figure_index
            )
            number = (
                caption_labels[caption_indexes[0]]
                if caption_indexes
                else _figure_number(figure_block.text)
            )
            figure_id = (
                f"figure_{number:04d}_{figure_block.order:06d}"
                if number is not None
                else f"figure_unlabelled_{figure_block.order:06d}"
            )
            explanation_indexes = self._figure_explanations(
                figure_index,
                number,
                blocks,
            )
            figure_warnings = []
            if not caption_indexes:
                figure_warnings.append("caption_missing")
                warnings.append(f"{figure_block.block_id}: figure caption missing")
            status = "context_bound" if caption_indexes else "caption_missing"
            caption = (
                " ".join(blocks[index].text.strip() for index in caption_indexes)
                if caption_indexes
                else None
            )
            logical = LogicalFigure(
                figure_id=figure_id,
                label=f"Figure {number}" if number is not None else None,
                number=number,
                caption=caption,
                page=figure_block.page,
                section_path=list(figure_block.section_path),
                source_block_ids=[figure_block.block_id],
                caption_block_ids=[blocks[index].block_id for index in caption_indexes],
                explanation_block_ids=[
                    blocks[index].block_id for index in explanation_indexes
                ],
                status=status,
                warnings=figure_warnings,
            )
            logical_figures.append(logical)
            figure_block.relations.update(
                {
                    "figure_id": figure_id,
                    "figure_label": logical.label,
                    "caption_block_ids": logical.caption_block_ids,
                    "explanation_block_ids": logical.explanation_block_ids,
                    "evidence_binding_status": status,
                }
            )
            for caption_index in caption_indexes:
                blocks[caption_index].type = "figure_caption"
                blocks[caption_index].relations.update(
                    {
                        "figure_id": figure_id,
                        "describes_block_ids": [figure_block.block_id],
                        "evidence_binding_status": "attached_to_figure",
                    }
                )
            for explanation_index in explanation_indexes:
                _append_relation(blocks[explanation_index], "figure_ids", figure_id)

        return logical_figures, warnings

    def _find_figure_target(
        self,
        caption_index: int,
        number: int,
        blocks: Sequence[ContentBlock],
        figure_indexes: Sequence[int],
        claimed_figures: Set[int],
    ) -> Optional[int]:
        caption_id = blocks[caption_index].block_id
        existing = [
            index
            for index in figure_indexes
            if caption_id in blocks[index].relations.get("caption_block_ids", [])
        ]
        if existing:
            return existing[0]

        candidates = [
            index
            for index in figure_indexes
            if index not in claimed_figures
            and blocks[index].page is not None
            and blocks[index].page == blocks[caption_index].page
        ]
        labelled = [
            index
            for index in candidates
            if _figure_number(blocks[index].text) == number
            or blocks[index].relations.get("figure_label") == f"Figure {number}"
        ]
        pool = labelled or candidates
        if not pool:
            return None
        return min(
            pool,
            key=lambda index: (
                abs(index - caption_index),
                0 if index < caption_index else 1,
            ),
        )

    def _figure_explanations(
        self,
        figure_index: int,
        number: Optional[int],
        blocks: Sequence[ContentBlock],
    ) -> List[int]:
        if number is None:
            return []
        pattern = re.compile(
            rf"\b(?:Figure|Fig\.?)\s*{number}\b",
            re.IGNORECASE,
        )
        figure = blocks[figure_index]
        candidates = []
        start = max(0, figure_index - self.reference_window)
        end = min(len(blocks), figure_index + self.reference_window + 1)
        for index in range(start, end):
            block = blocks[index]
            if block.type not in _CONTEXT_TYPES or not pattern.search(block.text):
                continue
            if not _compatible_context(figure, block):
                continue
            candidates.append(index)
        return candidates

    def _bind_formulas(
        self, blocks: List[ContentBlock]
    ) -> Tuple[List[LogicalFormula], List[str]]:
        logical_formulas: List[LogicalFormula] = []
        warnings: List[str] = []
        for index, block in enumerate(blocks):
            if block.type != "formula":
                continue
            number = _equation_number(block.text)
            formula_id = f"formula_{block.order:06d}"
            context_indexes = set()
            for direction in (-1, 1):
                nearest = _nearest_formula_context(index, direction, blocks)
                if nearest is not None:
                    context_indexes.add(nearest)
            if number:
                reference_re = re.compile(
                    rf"\b(?:Equation|Eq\.?)\s*\(?{re.escape(number)}\)?",
                    re.IGNORECASE,
                )
                start = max(0, index - self.reference_window)
                end = min(len(blocks), index + self.reference_window + 1)
                for candidate in range(start, end):
                    context = blocks[candidate]
                    if (
                        context.type in _CONTEXT_TYPES
                        and reference_re.search(context.text)
                        and _compatible_context(block, context)
                    ):
                        context_indexes.add(candidate)
            ordered_context = sorted(context_indexes)
            formula_warnings = []
            if not block.text.strip():
                formula_warnings.append("formula_text_missing")
            if not ordered_context:
                formula_warnings.append("context_missing")
                warnings.append(f"{block.block_id}: formula context missing")
            status = "context_bound" if ordered_context else "context_missing"
            logical = LogicalFormula(
                formula_id=formula_id,
                equation_number=number,
                text=block.text,
                page=block.page,
                section_path=list(block.section_path),
                source_block_id=block.block_id,
                context_block_ids=[blocks[i].block_id for i in ordered_context],
                status=status,
                warnings=formula_warnings,
            )
            logical_formulas.append(logical)
            block.relations.update(
                {
                    "formula_id": formula_id,
                    "equation_number": number,
                    "context_block_ids": logical.context_block_ids,
                    "evidence_binding_status": status,
                }
            )
            for context_index in ordered_context:
                _append_relation(blocks[context_index], "formula_ids", formula_id)
        return logical_formulas, warnings


def _figure_number(text: str) -> Optional[int]:
    match = _FIGURE_LABEL_RE.match(text or "")
    return int(match.group(1)) if match else None


def _equation_number(text: str) -> Optional[str]:
    match = _EQUATION_NUMBER_RE.search(text or "")
    return match.group(1) if match else None


def _compatible_context(evidence: ContentBlock, context: ContentBlock) -> bool:
    if evidence.page is not None and context.page is not None:
        if abs(evidence.page - context.page) > 1:
            return False
    if evidence.section_path and context.section_path:
        return evidence.section_path == context.section_path
    return True


def _nearest_formula_context(
    formula_index: int,
    direction: int,
    blocks: Sequence[ContentBlock],
) -> Optional[int]:
    formula = blocks[formula_index]
    index = formula_index + direction
    while 0 <= index < len(blocks):
        block = blocks[index]
        if block.type in {"heading", "title", "formula"}:
            return None
        if block.type in _CONTEXT_TYPES and _compatible_context(formula, block):
            return index
        index += direction
    return None


def _append_relation(block: ContentBlock, key: str, value: str) -> None:
    values = list(block.relations.get(key, []))
    if value not in values:
        values.append(value)
    block.relations[key] = values
