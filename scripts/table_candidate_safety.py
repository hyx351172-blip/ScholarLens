"""Additional conservative admission veto. Does not repair or invent table rows."""
from collections import defaultdict
from copy import deepcopy
from statistics import median

from table_ocr_binding import rectangle

POLICY = {'min_aligned_bands': 3, 'min_columns': 2, 'line_merge_height': .35,
          'cross_column_height': .4, 'min_cell_height_lines': 3}


def line_bands(cell):
    items = cell['ocr']
    if not items: return []
    scale = median(a['bbox'][3]-a['bbox'][1] for a in items)
    groups = []
    for a in sorted(items, key=lambda x: ((x['bbox'][1]+x['bbox'][3])/2, x['ocr_id'])):
        y = (a['bbox'][1]+a['bbox'][3])/2
        if not groups or abs(y-median(x[0] for x in groups[-1])) > scale*POLICY['line_merge_height']:
            groups.append([])
        groups[-1].append((y,a['ocr_id']))
    return [{'y': median(y for y,_ in g), 'height': scale, 'ocr_ids': [i for _,i in g]} for g in groups]


def guard_candidate(trace):
    out = deepcopy(trace)
    out['row_safety'] = {'version': 'v13', 'policy': deepcopy(POLICY), 'suspicions': []}
    if not out['gate']['passed']:
        out['row_safety']['status'] = 'prior_rejection_retained'
        return out
    try:
        cells = out['cells']
        if not 0 < len(cells) <= 5000: raise ValueError('Invalid cells')
        seen = set(); total = 0
        for c in cells:
            rectangle(c['bbox'])
            if any(type(c[n]) is not int or c[n] < (1 if n.endswith('span') else 0)
                   for n in ('row','col','row_span','col_span','cell_id')):
                raise ValueError('Invalid cell coordinates')
            ids = []
            for a in c['ocr']:
                rectangle(a['bbox']); i = a['ocr_id']
                if type(i) is not int or i < 0 or i in seen: raise ValueError('Invalid OCR IDs')
                seen.add(i); ids.append(i); total += 1
            if total > 10000 or ids != c['ocr_ids']: raise ValueError('Invalid provenance')
    except (KeyError, TypeError, ValueError):
        out['gate']['passed'] = False
        out['gate']['reasons'].append('invalid_row_provenance')
        out['row_safety']['status'] = 'rejected'
        return out
    rows = defaultdict(list)
    for c in cells:
        # Spanning cells and explicit reconstructed headers are not records.
        if c.get('is_header') or c['row_span'] != 1 or c['col_span'] != 1: continue
        bands = line_bands(c)
        if len(bands) < POLICY['min_aligned_bands']: continue
        if c['bbox'][3]-c['bbox'][1] < bands[0]['height']*POLICY['min_cell_height_lines']: continue
        rows[c['row']].append((c,bands))
    for row, candidates in sorted(rows.items()):
        for i,(a,ab) in enumerate(candidates):
            for b,bb in candidates[i+1:]:
                if a['col'] == b['col']: continue
                matched = []; used = set()
                for band in ab:
                    choices = [(abs(band['y']-other['y']),j,other) for j,other in enumerate(bb) if j not in used]
                    if not choices: break
                    d,j,other = min(choices, key=lambda t:(t[0],t[1]))
                    if d <= min(band['height'],other['height'])*POLICY['cross_column_height']:
                        used.add(j); matched.append({'y': [band['y'],other['y']],
                            'ocr_ids': band['ocr_ids']+other['ocr_ids']})
                if len(matched) >= POLICY['min_aligned_bands']:
                    out['row_safety']['suspicions'].append({'row':row,'cell_ids':[a['cell_id'],b['cell_id']],
                                                          'aligned_bands':matched})
    if out['row_safety']['suspicions']:
        out['gate']['passed'] = False
        out['gate']['reasons'].append('aligned_multiline_row_ambiguity')
        out['row_safety']['status'] = 'rejected_ambiguous_records'
    else:
        out['row_safety']['status'] = 'no_extra_veto'
    return out
