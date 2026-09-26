"""Separate gold-only v11 scoring. Gate decisions come from no-gold replay."""
import argparse
import html
import json
import os
from pathlib import Path
import sys

from audit_table_decoder import read, write, sha, preflight, parse_html_table
from experiment_table_grid_binding import fresh_output, verify_hashes, verify_run
from table_ocr_binding import aligned_metrics, label_anchored_metrics, key, normalized
from score_vlm_table_experiment import safe_table


def header_diagnostics(pred_raw, gold_raw):
    """Scoring-only span-prefix diagnostic, not a gold semantic-header label."""
    def prefix(raw):
        s = parse_html_table(safe_table(raw))[0]; cells = s['table_cells']
        def regular(r):
            covering = [c for c in cells if key(c)[0] <= r < key(c)[0] + key(c)[2]]
            return len(covering) == s['num_cols'] and all(key(c)[2:] == (1, 1) for c in covering)
        depth = next((r for r in range(1, min(7, s['num_rows'] - 2))
                      if all(regular(y) for y in (r, r + 1, r + 2))), None)
        return depth, {key(c): normalized(c['text']) for c in cells if depth is not None and key(c)[0] < depth}
    try:
        pd, pc = prefix(pred_raw); gd, gc = prefix(gold_raw)
    except ValueError as exc:
        return {'available': False, 'reason': str(exc)}
    if pd is None or gd is None:
        return {'available': False, 'reason': 'No unambiguous regular-body prefix'}
    matched = pc.keys() & gc.keys()
    return {'available': True, 'prediction_header_rows': pd, 'gold_header_rows': gd,
            'prediction_header_cells': len(pc), 'gold_header_cells': len(gc),
            'matched_span_cells': len(matched), 'missing_span_cells': len(gc.keys() - pc.keys()),
            'extra_span_cells': len(pc.keys() - gc.keys()),
            'exact_text_cells': sum(pc.get(k) == v for k, v in gc.items()),
            'text_errors': [{'coordinates': k, 'gold': v, 'prediction': pc.get(k)}
                            for k, v in gc.items() if pc.get(k) != v],
            'limitation': 'Header prefix inferred from spans and regular-body onset; not explicit semantic-header annotation.'}


def score(prepared, run_dir, v9_scored, gold, evaluator, output):
    prepared, run_dir, v9_scored, gold, evaluator, output = [p.resolve() for p in (prepared, run_dir, v9_scored, gold, evaluator, output)]
    fresh_output(output, [prepared, run_dir, v9_scored, gold, evaluator])
    manifest = preflight(prepared, output)
    run = read(run_dir / 'summary.json'); verify_run(run_dir, run)
    prior = read(v9_scored)
    if run['manifest_sha256'] != sha(prepared / 'manifest.json') or prior['manifest_sha256'] != run['manifest_sha256']:
        raise ValueError('Scoring manifest mismatch')
    if prior['gold_sha256'] != sha(gold): raise ValueError('Gold changed since v9')
    for rel, digest in prior['evaluator_sha256'].items():
        if sha(evaluator / rel) != digest: raise ValueError('Official evaluator changed')
    scoring_hashes = {str(p): sha(p) for p in [gold, v9_scored, run_dir / 'summary.json', Path(__file__).resolve()]}
    sys.path.insert(0, str(evaluator))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS
    annotations = {p['page_info']['image_path']: p for p in read(gold)}
    old = {r['id']: r for r in prior['results']}; new = {r['id']: r for r in run['results']}
    if set(old) != set(new) or set(new) != {r['id'] for r in manifest['results']}:
        raise ValueError('Cohort mismatch')
    output.mkdir(parents=True); records = []; links = []
    for item in manifest['results']:
        case = item['id']; dest = output / case; dest.mkdir()
        tables = [d for d in annotations[item['page']]['layout_dets'] if d['category_type'] == 'table' and not d.get('ignore')]
        if len(tables) != 1: raise ValueError('Fixed pairing requires one gold table')
        gold_raw = tables[0]['html']; gold_norm = normalized_html_table(gold_raw)
        (dest / 'gold.normalized.html').write_text(gold_norm, encoding='utf-8')
        baseline_raw = (prepared / case / 'baseline.html').read_text(encoding='utf-8')

        def metrics(raw, label):
            norm = normalized_html_table(raw)
            (dest / (label + '.normalized.html')).write_text(norm, encoding='utf-8')
            out = {'teds': TEDS().evaluate(norm, gold_norm),
                   'structure_teds': TEDS(structure_only=True).evaluate(norm, gold_norm)}
            try: aligned = aligned_metrics(norm, gold_norm)
            except ValueError as exc: out['aligned_cells'] = {'available': False, 'reason': str(exc)}
            else:
                write(dest / (label + '-aligned-cells.json'), aligned)
                out['aligned_cells'] = {'available': True, 'error_count': len(aligned['errors']),
                                        'error_preview': aligned['errors'][:12], **{k:v for k,v in aligned.items() if k != 'errors'}}
                out['label_anchored'] = label_anchored_metrics(norm, gold_norm)
            # Official normalization changes some glyphs, including em dash.
            # Keep a separate raw-glyph diagnostic so it cannot conceal OCR errors.
            try: raw_aligned = aligned_metrics(raw, gold_raw)
            except ValueError as exc: out['raw_aligned_cells'] = {'available': False, 'reason': str(exc)}
            else:
                write(dest / (label + '-raw-aligned-cells.json'), raw_aligned)
                out['raw_aligned_cells'] = {'available': True, 'error_count': len(raw_aligned['errors']),
                                           'error_preview': raw_aligned['errors'][:12],
                                           **{k:v for k,v in raw_aligned.items() if k != 'errors'}}
            out['header_prefix'] = header_diagnostics(raw, gold_raw)
            return out

        baseline = metrics(baseline_raw, 'baseline')
        if any(abs(baseline[k] - old[case]['baseline'][k]) > 1e-9 for k in ('teds', 'structure_teds')):
            raise ValueError('Baseline failed to reproduce v9/v4')
        row = {'id': case, 'page': item['page'], 'baseline': baseline, 'v9_raw_diagnostic': old[case]['raw_candidate_diagnostic'],
               'gate': new[case]['gate'], 'status': new[case]['status'], 'candidate': None}
        path = run_dir / case / 'raw-candidate.html'; raw = None
        if path.is_file():
            relative = path.relative_to(run_dir).as_posix()
            if relative not in run['artifact_sha256']: raise ValueError('Unrecorded candidate')
            raw = path.read_text(encoding='utf-8')
            trace = read(run_dir / case / 'grid-trace.json')
            if raw != trace['html'] or trace['gate'] != row['gate']: raise ValueError('Trace/HTML/gate drift')
            row['candidate'] = metrics(raw, 'candidate')
        if row['gate']['passed'] and row['candidate'] is None: raise ValueError('Passing gate without candidate')
        row['effective_offline'] = row['candidate'] if row['gate']['passed'] else baseline
        records.append(row)
        crop = html.escape(os.path.relpath(prepared / case / 'crop.png', dest).replace('\\', '/'), quote=True)
        parts = ['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'">',
                 '<style>body{font:14px system-ui;margin:20px}main{display:flex;gap:20px}section{width:33%;overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:3px}pre{white-space:pre-wrap;max-height:400px;overflow:auto}</style>',
                 '<h1>' + html.escape(case) + '</h1><p>Offline only. Rejection retains baseline; gold never selects output.</p>',
                 f'<a href="{crop}">Frozen crop</a><pre>' + html.escape(json.dumps(row, ensure_ascii=False, indent=2)) + '</pre><main>']
        for title, value in [('Gold (scoring only)', gold_raw), ('Docling baseline', baseline_raw), ('v11 header candidate', raw)]:
            parts.append('<section><h2>' + title + '</h2>' + (safe_table(value) if value else '<p>No candidate: rejected before binding.</p>') + '</section>')
        (dest / 'comparison.html').write_text(''.join(parts) + '</main>', encoding='utf-8')
        links.append('<li><a href="' + html.escape(case) + '/comparison.html">' + html.escape(case) + '</a></li>')
        print(case, 'baseline', round(baseline['teds'], 6), 'candidate', round(row['candidate']['teds'], 6) if row['candidate'] else None, 'gate', row['gate']['passed'], flush=True)
    verify_run(run_dir, run); verify_hashes(scoring_hashes)
    report = {'experiment': 'table-header-reconstruction-v11', 'gold_access_in_inference': False, 'production_applied': False,
              'manifest_sha256': run['manifest_sha256'], 'scoring_input_sha256': scoring_hashes,
              'evaluator_sha256': prior['evaluator_sha256'], 'baseline_reproduced_all': True,
              'aggregate': {'cases': len(records), 'candidates_scored': sum(r['candidate'] is not None for r in records),
                            'gate_passed': sum(r['gate']['passed'] for r in records),
                            'baseline_teds': sum(r['baseline']['teds'] for r in records) / len(records),
                            'effective_offline_teds': sum(r['effective_offline']['teds'] for r in records) / len(records)},
              'results': records, 'limitations': ['Three selected development tables, two datasheets and one paper; not held-out.',
                         'Same OCR/model outputs as v9; v10 successes unchanged, supported local header topology reconstructed.',
                         'Geometric gate is not recognition correctness. Official scores cannot promote production.',
                         'Requires corroborated ruling lines and top-level groups; arbitrary borderless or invalid structures remain unsupported.',
                         'Explicit header/unit subsets may be unavailable; zero denominator is not perfect accuracy.']}
    write(output / 'results.json', report)
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>ScholarLens header reconstruction v11</h1><ul>' + ''.join(links) + '</ul>', encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'run-dir', 'v9-scored', 'gold', 'evaluator', 'output'): p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args(); r = score(a.prepared, a.run_dir, a.v9_scored, a.gold, a.evaluator, a.output)
    print(json.dumps(r['aggregate'], indent=2))


