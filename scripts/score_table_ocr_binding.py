"""Separate gold-only v9 scoring: content TEDS, coordinate errors, binding gate.

Even rejected but strict-HTML-valid raw candidates are scored DIAGNOSTICALLY.
Their scores do not override the gold-independent binding gate or baseline fallback.
"""
import argparse
import html
import json
import os
from pathlib import Path
import sys

from audit_table_decoder import read, write, sha, preflight, parse_html_table
from table_ocr_binding import audit_binding, aligned_metrics, binding_gate, structure_signature, label_anchored_metrics
from score_vlm_table_experiment import safe_table, numeric_diagnostic


def score(prepared, run_dir, v8, gold_path, evaluator, previous_path, output):
    prepared, run_dir, v8, gold_path, evaluator, previous_path, output = [p.resolve() for p in
        (prepared, run_dir, v8, gold_path, evaluator, previous_path, output)]
    if any(output == p or p in output.parents or output in p.parents for p in (run_dir, v8, gold_path, evaluator, previous_path)):
        raise ValueError('Score output overlaps protected input')
    manifest = preflight(prepared, output)
    run = read(run_dir / 'summary.json')
    if (run['manifest_sha256'] != sha(prepared / 'manifest.json') or not run.get('protected_inputs_unchanged')
            or not run.get('frozen_15_files_unchanged')):
        raise ValueError('Input provenance/integrity mismatch')
    sys.path.insert(0, str(evaluator))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS
    gold = {p['page_info']['image_path']: p for p in read(gold_path)}
    previous = {p['img_id']: p for p in read(previous_path)}
    output.mkdir(parents=True)
    records, sections = [], []
    for item in manifest['results']:
        case, page = item['id'], item['page']
        tables = [d for d in gold[page]['layout_dets'] if d['category_type'] == 'table' and not d.get('ignore')]
        if len(tables) != 1: raise ValueError('Fixed pairing requires one gold table')
        gold_raw = tables[0]['html']; gold_norm = normalized_html_table(gold_raw)
        baseline_raw = (prepared / case / 'baseline.html').read_text(encoding='utf-8')
        dest = output / case; dest.mkdir()

        def metrics(raw, label):
            norm = normalized_html_table(raw)
            (dest / (label + '.normalized.html')).write_text(norm, encoding='utf-8')
            out = {'teds': TEDS().evaluate(norm, gold_norm), 'structure_teds': TEDS(structure_only=True).evaluate(norm, gold_norm),
                   'numeric_token_multiset': numeric_diagnostic(norm, gold_norm)}
            try:
                aligned = aligned_metrics(norm, gold_norm)
            except ValueError as exc:
                out['aligned_cells'] = {'available': False, 'reason': str(exc)}
            else:
                write(dest / (label + '-aligned-cells.json'), aligned)
                out['label_anchored'] = label_anchored_metrics(norm, gold_norm)
                out['aligned_cells'] = dict(available=True, error_count=len(aligned['errors']),
                                           error_preview=aligned['errors'][:12],
                                           **{k: v for k, v in aligned.items() if k != 'errors'})
            return out

        baseline = metrics(baseline_raw, 'baseline')
        if (abs(baseline['teds'] - previous[page]['metric']['TEDS']) > 1e-9 or
                abs(baseline['structure_teds'] - previous[page]['metric']['TEDS_structure_only']) > 1e-9):
            raise ValueError('Baseline does not reproduce v4')
        (dest / 'gold.normalized.html').write_text(gold_norm, encoding='utf-8')
        row = {'id': case, 'page': page, 'baseline': baseline, 'raw_candidate_diagnostic': None,
               'binding_gate': {'passed': False, 'reasons': ['v8_structure_invalid_or_no_output']},
               'baseline_matches_v4': True}
        response_path = run_dir / case / 'response.json'
        raw = None
        if response_path.is_file():
            response = read(response_path); raw = response['content']
            frozen = (v8 / 'extended' / case / 'structure.html').read_text(encoding='utf-8')
            if response['structure_sha256'] != sha(v8 / 'extended' / case / 'structure.html') or response['crop_sha256'] != item['crop_sha256']:
                raise ValueError('Raw response provenance changed')
            row['artifact_sha256'] = {name: sha(run_dir / case / name) for name in
                                      ('response.json', 'binding-capture.json', 'paddle-raw.json', 'raw.html')}
            try:
                parse_html_table(raw)
                if structure_signature(raw) != structure_signature(frozen): raise ValueError('Structure drift after binding')
            except ValueError as exc:
                row['raw_structure_error'] = str(exc)
            else:
                # Evaluate binding without gold first, then score the same raw output.
                try:
                    trace = audit_binding(frozen, raw, read(run_dir / case / 'binding-capture.json'))
                except (ValueError, KeyError) as exc:
                    row['binding_gate'] = {'passed': False, 'reasons': ['binding_trace_error'], 'detail': str(exc)}
                else:
                    write(dest / 'binding-trace.json', trace)
                    row['binding_gate'] = binding_gate(trace)
                    row['binding_summary'] = {k: v for k, v in trace.items() if k != 'cells'}
                row['raw_candidate_diagnostic'] = metrics(raw, 'raw-candidate')
        row['effective'] = row['raw_candidate_diagnostic'] if row['binding_gate']['passed'] else baseline
        records.append(row)
        rel_crop = html.escape(os.path.relpath(prepared / case / 'crop.png', dest).replace('\\', '/'), quote=True)
        preview = ['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'">',
                   '<style>body{font:14px system-ui;margin:20px}main{display:flex;gap:20px}section{max-width:33%;overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:3px}pre{white-space:pre-wrap;max-height:600px;overflow:auto}</style>',
                   '<h1>' + html.escape(case) + '</h1><p>Offline diagnostic; no production replacement.</p>',
                   f'<a href="{rel_crop}">Frozen crop</a><pre>' + html.escape(json.dumps(row, ensure_ascii=False, indent=2)) + '</pre><main>']
        for title, value in [('Gold: scoring only', gold_raw), ('Docling baseline', baseline_raw), ('Raw OCR-bound diagnostic (may be rejected)', raw)]:
            preview.append('<section><h2>' + title + '</h2>' + (safe_table(value) if value else '<p>No candidate.</p>') + '</section>')
        preview.append('</main>')
        (dest / 'comparison.html').write_text(''.join(preview), encoding='utf-8')
        sections.append(f'<li><a href="{html.escape(case)}/comparison.html">{html.escape(case)}</a></li>')
        cand = row['raw_candidate_diagnostic']
        print(case, 'baseline=', round(baseline['teds'], 6), 'raw diagnostic=', round(cand['teds'], 6) if cand else None,
              'binding gate=', row['binding_gate']['passed'], flush=True)
    report = {'experiment': 'table-ocr-binding-v9', 'gold_access_in_inference': False, 'production_applied': False,
              'manifest_sha256': sha(prepared / 'manifest.json'), 'gold_sha256': sha(gold_path),
              'run_sha256': sha(run_dir / 'summary.json'), 'baseline_matches_v4_all': True,
              'evaluator_sha256': {f: sha(evaluator / f) for f in ('src/core/preprocess/data_preprocess.py', 'src/metrics/table_metric.py')},
              'aggregate': {'cases': len(records), 'raw_candidates_scored': sum(r['raw_candidate_diagnostic'] is not None for r in records),
                            'binding_gate_passed': sum(r['binding_gate']['passed'] for r in records),
                            'baseline_teds': sum(r['baseline']['teds'] for r in records) / len(records),
                            'effective_teds': sum(r['effective']['teds'] for r in records) / len(records)},
              'results': records,
              'limitations': ['Three selected development cases, not held-out; two datasheets and one paper table.',
                              'Raw candidate TEDS is diagnostic even when binding gate rejects it.',
                              'Exact-coordinate diagnostics have no semantic row-shift rescue; numeric and unit lexicons are limited.',
                              'No downstream RAG or production acceptance.']}
    write(output / 'results.json', report)
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>ScholarLens OCR binding v9</h1><p>Content scores and conservative binding gate are separate.</p><ul>' + ''.join(sections) + '</ul>', encoding='utf-8')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'run-dir', 'v8', 'gold', 'evaluator', 'previous', 'output'): p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    report = score(a.prepared, a.run_dir, a.v8, a.gold, a.evaluator, a.previous, a.output)
    print(json.dumps(report['aggregate'], indent=2))


if __name__ == '__main__': main()
