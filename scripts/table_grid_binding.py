"""Offline no-gold physical-edge -> logical-grid OCR binding (stdlib only).

Does not correct recognition or topology. Sparse physical detections may still
support a complete lattice; logical empty cells are NOT required to have a box.
Missing/unstable lattice lines cause rejection, never uniform interpolation.
"""
import copy
import math
from statistics import median

from audit_table_decoder import parse_html_table
from table_structure import render_table_html
from table_ocr_binding import coverage, key, rectangle, structure_signature


POLICY = {'edge_tolerance': .15, 'stability_tolerances': [.10, .20],
          'support_fraction': .02, 'min_edge_support': 2,
          'ocr_min_coverage': .7, 'ocr_min_margin': .4}


def _clusters(boxes, axis, tolerance):
    # Sorting both coordinates and IDs makes replay deterministic. Each source
    # detection can vote at most once for an edge cluster.
    scale = median(b[axis + 2] - b[axis] for b in boxes)
    groups = []
    for value, index in sorted((b[a], i) for i, b in enumerate(boxes) for a in (axis, axis + 2)):
        if not groups or value - median(v for v, _ in groups[-1]) > scale * tolerance:
            groups.append([])
        groups[-1].append((value, index))
    return [{'position': median(v for v, _ in g), 'support': len(set(i for _, i in g)),
             'detection_ids': sorted(set(i for _, i in g))} for g in groups], scale


def infer_axis(boxes, axis, expected):
    support = max(POLICY['min_edge_support'], math.ceil(len(boxes) * POLICY['support_fraction']))

    def select(tolerance):
        groups, scale = _clusters(boxes, axis, tolerance)
        selected = [g for i, g in enumerate(groups) if g['support'] >=
                    (POLICY['min_edge_support'] if i in (0, len(groups) - 1) else support)]
        return groups, selected, scale

    groups, selected, scale = select(POLICY['edge_tolerance'])
    boundaries = [g['position'] for g in selected]
    trials = [[g['position'] for g in select(t)[1]] for t in POLICY['stability_tolerances']]
    stable = all(len(v) == len(boundaries) and all(abs(a - b) <= scale * .1 for a, b in zip(v, boundaries)) for v in trials)
    return {'boundaries': boundaries, 'selected_edges': selected, 'all_clusters': groups,
            'median_cell_dimension': scale, 'interior_min_support': support,
            'expected_boundaries': expected + 1, 'count_matches': len(boundaries) == expected + 1,
            'stable': stable, 'stability_boundaries': trials}


def bind_grid(structure_html, captured, crop_size):
    structure = parse_html_table(structure_html)[0]
    if any(c['text'].strip() for c in structure['table_cells']):
        raise ValueError('Expected empty frozen structure, not prefilled text')
    if (not isinstance(crop_size, list) or len(crop_size) != 2 or
            any(type(v) is not int or not 0 < v <= 50000 for v in crop_size)):
        raise ValueError('Invalid crop dimensions')
    boxes = captured['geometry_reprocessing']['detected_boxes']
    ocr_boxes, texts = captured['match']['ocr_boxes'], captured['render']['texts']
    if (not isinstance(boxes, list) or not 1 <= len(boxes) <= 5000 or
            not isinstance(ocr_boxes, list) or not isinstance(texts, list) or
            not 0 <= len(texts) <= 10000 or len(texts) != len(ocr_boxes) or
            any(not isinstance(t, str) or len(t) > 10000 for t in texts) or
            sum(map(len, texts)) > 2_000_000):
        raise ValueError('Invalid or excessive capture dimensions')
    for box in boxes + ocr_boxes:
        rectangle(box)
        if not (0 <= box[0] < box[2] <= crop_size[0] and 0 <= box[1] < box[3] <= crop_size[1]):
            raise ValueError('Geometry outside crop')
    # Deduplicate exact rectangles before voting, retain original IDs separately.
    unique = sorted(set(tuple(b) for b in boxes))
    axes = {'x': infer_axis(unique, 0, structure['num_cols']),
            'y': infer_axis(unique, 1, structure['num_rows'])}
    reasons = []
    for name, axis in axes.items():
        if not axis['count_matches']: reasons.append(name + '_axis_count_mismatch')
        if not axis['stable']: reasons.append(name + '_axis_unstable')
    out = {'schema_version': 'grid-binding-v10', 'policy': copy.deepcopy(POLICY), 'axes': axes,
           'physical_boxes': len(boxes), 'unique_detections': [list(b) for b in unique],
           'unique_to_original_ids': [[i for i, b in enumerate(boxes) if tuple(b) == u] for u in unique],
           'logical_cells': len(structure['table_cells']), 'ocr_count': len(texts),
           'crop_size': crop_size[:], 'html': None, 'cells': [], 'assignments': [],
           'empty_cell_ids': [], 'unassigned_ocr_ids': list(range(len(texts))),
           'gate': {'passed': False, 'reasons': reasons,
                    'policy': 'Offline geometric integrity only; review required, no OCR-accuracy or production guarantee.'}}
    if reasons:
        return out
    xs, ys = axes['x']['boundaries'], axes['y']['boundaries']
    cells = []
    for index, cell in enumerate(structure['table_cells']):
        r, c, rs, cs = key(cell)
        cells.append({'cell_id': index, 'row': r, 'col': c, 'row_span': rs, 'col_span': cs,
                      'bbox': [xs[c], ys[r], xs[c + cs], ys[r + rs]], 'ocr_ids': [], 'ocr': [], 'text': ''})
    assignments = []
    for index, box in enumerate(ocr_boxes):
        ranked = sorted(((coverage(c['bbox'], box), c['cell_id']) for c in cells), reverse=True)
        best, target = ranked[0]; second = ranked[1][0] if len(ranked) > 1 else 0
        accepted = best >= POLICY['ocr_min_coverage'] and best - second >= POLICY['ocr_min_margin']
        assignments.append({'ocr_id': index, 'text': texts[index], 'bbox': box[:],
                            'cell_id': target if accepted else None, 'best_cell_id': target,
                            'coverage': best, 'runner_up_coverage': second,
                            'reason': 'assigned' if accepted else 'ambiguous_or_low_overlap'})
        if accepted:
            cells[target]['ocr_ids'].append(index)
    filled = copy.deepcopy(structure)
    for c, f in zip(cells, filled['table_cells']):
        # Preserve OCR exactly, including number/letter confusions. Sort spatially,
        # not by incoming ID or value; a one-space join is the only composition.
        c['ocr_ids'].sort(key=lambda i: (ocr_boxes[i][1], ocr_boxes[i][0], i))
        c['ocr'] = [copy.deepcopy(assignments[i]) for i in c['ocr_ids']]
        c['text'] = ' '.join(texts[i] for i in c['ocr_ids'])
        f['text'] = c['text']
    raw = render_table_html(filled)
    if structure_signature(raw) != structure_signature(structure_html):
        raise ValueError('Rendered structure drift')
    out.update(html=raw, cells=cells, assignments=assignments,
               empty_cell_ids=[c['cell_id'] for c in cells if not c['ocr_ids']],
               unassigned_ocr_ids=[a['ocr_id'] for a in assignments if a['cell_id'] is None])
    if out['unassigned_ocr_ids']: reasons.append('unassigned_or_ambiguous_ocr')
    if not texts: reasons.append('no_ocr_evidence')
    out['gate']['passed'] = not reasons
    return out
