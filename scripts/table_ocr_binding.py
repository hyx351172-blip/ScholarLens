"""Pure OCR-binding audit and gold-only, coordinate-aligned diagnostics.

No model, network or gold-file access. Audits installed Paddle renderer semantics;
it never moves text, repairs tags, or supplies missing values.
"""
from collections import Counter
import math
import re
import unicodedata

from audit_table_decoder import parse_html_table
from score_vlm_table_experiment import safe_table


def key(cell):
    return (cell['start_row_offset_idx'], cell['start_col_offset_idx'], cell['row_span'], cell['col_span'])


def structure_signature(raw):
    return [key(c) for c in parse_html_table(raw)[0]['table_cells']]


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def rectangle(value):
    if (not isinstance(value, list) or len(value) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e7 for v in value)
            or value[2] <= value[0] or value[3] <= value[1]):
        raise ValueError('Invalid geometry rectangle')
    return value


def coverage(cell_box, ocr_box):
    a, b = rectangle(cell_box), rectangle(ocr_box)
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return intersection / ((b[2] - b[0]) * (b[3] - b[1]))


def audit_binding(structure_html, filled_html, captured):
    structure = parse_html_table(structure_html)[0]
    filled = parse_html_table(filled_html)[0]
    cells = structure['table_cells']
    if [key(c) for c in cells] != [key(c) for c in filled['table_cells']]:
        raise ValueError('Binding changed the accepted logical structure')
    m, render = captured['match'], captured['render']
    boxes, texts, groups = m['cell_boxes'], render['texts'], render['groups']
    ocr_boxes, starts, breaks = m['ocr_boxes'], m['group_starts'], render['breaks']
    if (not 0 < len(groups) <= 5000 or not 0 < len(texts) <= 10000 or len(texts) != len(ocr_boxes)
            or len(starts) != len(groups) + 1 or len(breaks) != len(groups) + 1
            or len(boxes) > 5000 or any(not isinstance(t, str) or len(t) > 10000 for t in texts)):
        raise ValueError('Inconsistent matcher dimensions')
    for seq, maximum in ((starts, len(boxes)), (breaks, max(len(boxes), len(cells)))):
        # Paddle appends physical-box count to logical-row starts. The final
        # sentinel is never used to advance past the final group, but may decrease.
        # Preserve/flag it for diagnosis; do not use it to remap any text.
        ordered = seq[:-1] if seq is breaks else seq
        if seq[0] != 0 or any(type(v) is not int or not 0 <= v <= maximum for v in seq) or ordered != sorted(ordered):
            raise ValueError('Invalid renderer boundaries')
    for b in boxes + ocr_boxes:
        rectangle(b)
    used = Counter(); result = []; low = []; text_mismatches = []; group = local = 0
    for index, cell in enumerate(cells):
        matches = groups[group]
        ids = matches.get(str(local), matches.get(local))
        if ids is not None and (not isinstance(ids, list) or not ids):
            # Installed renderer's empty-list `continue` skips both tag closure
            # and index advancement; don't simulate that as a successful mapping.
            raise ValueError('Empty matcher list triggers renderer skip hazard')
        ids = [] if ids is None else ids
        if len(ids) > 10000 or any(type(i) is not int or not 0 <= i < len(texts) for i in ids):
            raise ValueError('OCR index outside captured source')
        gid = starts[group] + local
        geometry = boxes[gid] if starts[group] <= gid < starts[group + 1] else None
        provenance = []
        for i in ids:
            used[i] += 1
            overlap = coverage(geometry, ocr_boxes[i]) if geometry is not None else None
            provenance.append({'id': i, 'text': texts[i], 'bbox': ocr_boxes[i], 'coverage': overlap})
            if overlap is None or overlap <= .7:
                low.append({'cell_id': index, 'ocr_id': i, 'coverage': overlap})
        expected = normalized(' '.join(t.replace('<b>', '').replace('</b>', '') for t in (texts[i] for i in ids)))
        actual = normalized(filled['table_cells'][index]['text'])
        if expected != actual:
            text_mismatches.append(index)
        result.append({'cell_id': index, 'row': key(cell)[0], 'col': key(cell)[1],
                       'row_span': key(cell)[2], 'col_span': key(cell)[3],
                       'geometry_id': gid if geometry is not None else None, 'bbox': geometry,
                       'ocr_ids': ids, 'ocr': provenance, 'rendered_text': filled['table_cells'][index]['text']})
        local += 1
        if index + 1 >= breaks[group + 1] and group < len(groups) - 1:
            group += 1; local = 0
    return {'logical_cells': len(cells), 'physical_boxes': len(boxes), 'ocr_count': len(texts),
            'geometry_count_matches': len(cells) == len(boxes), 'cells': result,
            'terminal_boundary_anomaly': breaks[-1] != len(cells) or breaks != sorted(breaks),
            'unassigned_ocr_ids': [i for i in range(len(texts)) if not used[i]],
            'duplicated_ocr_ids': sorted(i for i, count in used.items() if count > 1),
            'missing_geometry_cell_ids': [c['cell_id'] for c in result if c['bbox'] is None],
            'low_overlap_assignments': low, 'renderer_text_mismatch_cell_ids': text_mismatches,
            'warning': 'This traces the existing matcher, not proof of semantic alignment or production acceptance.'}


def binding_gate(trace):
    reasons = []
    if not trace['geometry_count_matches']: reasons.append('physical_logical_cell_count_mismatch')
    if trace['terminal_boundary_anomaly']: reasons.append('renderer_terminal_boundary_anomaly')
    for name in ('unassigned_ocr_ids', 'duplicated_ocr_ids', 'missing_geometry_cell_ids',
                 'low_overlap_assignments', 'renderer_text_mismatch_cell_ids'):
        if trace[name]: reasons.append(name)
    return {'passed': not reasons, 'reasons': reasons,
            'policy': 'Conservative offline integrity gate; no gold use. Passing does not prove content accuracy.'}


NUMBER = re.compile(r'(?<![\w.])[+\-−]?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?(?![\w.])')
UNIT = re.compile(r'(?<![A-Za-z])(?:mV|V|mA|μA|uA|A|kΩ|MΩ|Ω|MHz|kHz|Hz|ms|ns|ps|s|mW|W|°C|%)(?![A-Za-z])')


def label_anchored_metrics(pred_html, gold_html):
    """Scoring-only complement: exact unique first-column labels, no fuzzy match.

    No column reordering or numeric-value-based matching. Missing labeled rows
    remain in denominators. Report coverage/ambiguity; this is NOT header accuracy.
    """
    def index(raw):
        cells = parse_html_table(safe_table(raw))[0]['table_cells']
        labels = [(normalized(c['text']), key(c)[0]) for c in cells
                  if key(c)[1:] == (0, 1, 1) and normalized(c['text'])]
        counts = Counter(label for label, _ in labels)
        unique = {label: row for label, row in labels if counts[label] == 1}
        rows = {row: {(key(c)[1], key(c)[2], key(c)[3]): normalized(c['text']) for c in cells if key(c)[0] == row and key(c)[1] > 0}
                for row in unique.values()}
        return unique, rows, sorted(label for label, count in counts.items() if count > 1)
    pl, pr, pa = index(pred_html); gl, gr, ga = index(gold_html)
    nums = {'total': 0, 'exact': 0}; text = {'total': 0, 'exact': 0}; errors = []
    for label, row in gl.items():
        actual_row = pr.get(pl.get(label), {})
        for coord, expected in gr[row].items():
            actual = actual_row.get(coord)
            if expected:
                text['total'] += 1; text['exact'] += int(actual == expected)
            numbers = Counter(NUMBER.findall(expected))
            if numbers:
                nums['total'] += 1
                correct = actual is not None and Counter(NUMBER.findall(actual)) == numbers
                nums['exact'] += int(correct)
                if not correct: errors.append({'row_label': label, 'col': coord[0], 'gold': expected, 'prediction': actual})
    for subset in (nums, text): subset['accuracy'] = subset['exact'] / subset['total'] if subset['total'] else None
    return {'unique_gold_label_rows': len(gl), 'unique_predicted_label_rows': len(pl),
            'matched_label_rows': len(gl.keys() & pl.keys()), 'missing_gold_labels': sorted(gl.keys() - pl.keys()),
            'ambiguous_gold_labels': ga, 'ambiguous_prediction_labels': pa,
            'body_numeric_cells': nums, 'body_nonempty_cells': text, 'numeric_error_preview': errors[:20],
            'limitation': 'Exact unique first-column label anchors only. No semantic/fuzzy row matching, no column remapping; not a replacement for strict coordinates or header/span validation.'}


def aligned_metrics(pred_html, gold_html):
    # Gold normalization is restricted to scoring; candidate admission is handled
    # separately by strict parse_html_table on the unmodified raw HTML.
    pred = parse_html_table(safe_table(pred_html))[0]['table_cells']
    gold = parse_html_table(safe_table(gold_html))[0]['table_cells']
    pm, gm = {key(c): c for c in pred}, {key(c): c for c in gold}
    subsets = {name: {'total': 0, 'exact': 0} for name in ('all_gold_cells', 'nonempty_gold_cells',
               'numeric_cells', 'explicit_header_cells', 'first_column_cells', 'unit_bearing_cells')}
    errors = []
    for coord, cell in gm.items():
        target = normalized(cell['text'])
        actual = normalized(pm[coord]['text']) if coord in pm else None
        numbers = Counter(NUMBER.findall(target))
        tests = {'all_gold_cells': True, 'nonempty_gold_cells': bool(target), 'numeric_cells': bool(numbers),
                 'explicit_header_cells': cell['column_header'], 'first_column_cells': coord[1] == 0 and bool(target),
                 'unit_bearing_cells': bool(numbers) and bool(UNIT.search(target))}
        for name, applies in tests.items():
            if applies:
                subsets[name]['total'] += 1
                equal = actual == target if name != 'numeric_cells' else (actual is not None and Counter(NUMBER.findall(actual)) == numbers)
                subsets[name]['exact'] += int(equal)
        if target != actual:
            errors.append({'row': coord[0], 'col': coord[1], 'row_span': coord[2], 'col_span': coord[3],
                           'gold': cell['text'], 'prediction': pm[coord]['text'] if coord in pm else None,
                           'numeric_gold': list(numbers.elements()), 'explicit_header': cell['column_header']})
    for subset in subsets.values():
        subset['accuracy'] = subset['exact'] / subset['total'] if subset['total'] else None
    return dict(subsets, matched_span_cells=len(pm.keys() & gm.keys()), gold_cells=len(gm), prediction_cells=len(pm),
                missing_span_cells=len(gm.keys() - pm.keys()), extra_span_cells=len(pm.keys() - gm.keys()),
                errors=errors, interpretation='Exact (row,column,rowspan,colspan), no row-shift rescue. NFKC and whitespace only; numeric regex and finite unit vocabulary are diagnostics, not general scientific validation.')
