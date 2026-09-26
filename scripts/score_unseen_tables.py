"""Gold-only scoring of frozen v12 outputs. Never promotes rejected candidates."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import html
import json
import os
from pathlib import Path
import subprocess
import sys
from statistics import mean, median

from experiment_unseen_tables import ROOT, DATA, read, write, sha, verify, aggregate_scores
from table_ocr_binding import aligned_metrics, key, normalized, parse_html_table
from score_table_header_reconstruction import header_diagnostics
from score_vlm_table_experiment import safe_table


def optional_text(path):
    return path.read_text(encoding='utf-8') if path.is_file() else None


def score_case(root, case, output):
    sys.path.insert(0, str(DATA / 'evaluator'))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS
    gold = read(root / 'scoring-only-gold.json')[case]['html']
    gold_norm = normalized_html_table(gold)
    src = root / 'final' / case; row = read(src / 'result.json')
    baseline = optional_text(src / 'baseline.html')
    candidate = optional_text(src / 'candidate.html')
    effective = optional_text(src / 'effective.html')
    expected = candidate if row['gate']['passed'] else baseline
    if effective != expected: raise ValueError('Frozen gate/output drift')
    raw_paddle = optional_text(root / 'paddle' / case / 'raw.html')
    def metrics(raw, label):
        if not raw: return {'teds': 0., 'structure_teds': 0., 'missing_output': True}
        norm = normalized_html_table(raw)
        (output / (label + '.normalized.html')).write_text(norm, encoding='utf-8')
        result = {'teds': TEDS().evaluate(norm, gold_norm),
                  'structure_teds': TEDS(structure_only=True).evaluate(norm, gold_norm), 'missing_output': False}
        try:
            diag = aligned_metrics(raw, gold)
            pm = {key(c): normalized(c['text']) for c in parse_html_table(safe_table(raw))[0]['table_cells']}
            gm = {key(c): normalized(c['text']) for c in parse_html_table(safe_table(gold))[0]['table_cells']}
            diag['nonempty_in_gold_empty'] = sum(bool(pm.get(k)) for k, v in gm.items() if not v)
            diag['extra_nonempty_coordinates'] = sum(bool(v) for k, v in pm.items() if k not in gm)
        except ValueError as exc:
            result['raw_cell_diagnostic'] = {'available': False, 'reason': str(exc)}
        else:
            write(output / (label + '-cells.json'), diag)
            result['raw_cell_diagnostic'] = {'available': True, **{k: v for k, v in diag.items() if k != 'errors'},
                                             'error_count': len(diag['errors']), 'error_preview': diag['errors'][:5]}
        result['header_prefix'] = header_diagnostics(raw, gold)
        return result
    result = {'id': case, 'page': row['page'], 'gate': row['gate'], 'gate_passed': row['gate']['passed'],
              'baseline_status': row['baseline_status'], 'baseline': metrics(baseline, 'baseline')}
    result['candidate_diagnostic'] = metrics(candidate, 'candidate') if candidate else None
    result['raw_paddle_diagnostic'] = metrics(raw_paddle, 'raw-paddle') if raw_paddle else None
    result['effective'] = result['candidate_diagnostic'] if row['gate']['passed'] else result['baseline']
    write(output / 'result.json', result)
    crop = '../../prepared/' + case + '.png'
    parts = ['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'">',
        '<style>body{font:14px system-ui;margin:20px}main{display:flex;gap:20px}section{max-width:33%;overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:3px}pre{white-space:pre-wrap}</style>',
        '<h1>' + html.escape(case) + '</h1><p>Oracle crop, offline only; gold never selects output.</p>',
        '<a href="' + crop + '">Source crop</a><pre>' + html.escape(json.dumps(result, ensure_ascii=False, indent=2)) + '</pre><main>']
    for title, text in [('Gold', gold), ('Docling', baseline), ('Effective frozen pipeline', effective)]:
        parts += ['<section><h2>' + title + '</h2>' + (safe_table(text) if text else '<p>No output</p>') + '</section>']
    (output / 'comparison.html').write_text(''.join(parts) + '</main>', encoding='utf-8')


def run(root):
    final = read(root / 'final/summary.json')
    protected = dict(final['source_sha256'])
    protected.update({str(root / 'final' / p): digest for p, digest in final['artifact_sha256'].items()})
    # Model/algorithm/source hashes were verified by finalization; verify all again after scoring.
    protected.update(read(root / 'frozen-inputs.json'))
    for p in (root / 'final/summary.json', Path(__file__).resolve()): protected[str(p)] = sha(p)
    verify(protected)
    output = root / 'scored'; output.mkdir()
    write(output / 'scoring-inputs.json', protected)
    evaluator_python = DATA / '.eval-venv/Scripts/python.exe'
    env = dict(os.environ, PYTHONUTF8='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        MPLCONFIGDIR=str(ROOT / 'backend/data/benchmarks/model_cache/matplotlib'))
    def evaluate(item):
        case = item['id']; dest = output / case; dest.mkdir()
        with (dest / 'worker.log').open('w', encoding='utf-8') as log:
            try:
                proc = subprocess.run([str(evaluator_python), str(Path(__file__).resolve()), '--worker', '--root', str(root),
                    '--case', case, '--output', str(dest)], cwd=ROOT, env=env,
                    stdout=log, stderr=subprocess.STDOUT, timeout=300, check=False)
                completed = proc.returncode == 0 and (dest / 'result.json').is_file()
            except subprocess.TimeoutExpired:
                completed = False
        return (read(dest / 'result.json'), None) if completed else (None, case)
    rows = []; failures = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for row, error in pool.map(evaluate, final['results']):
            if row is not None:
                rows.append(row)
                print(row['id'], 'baseline', round(row['baseline']['teds'], 4), 'effective', round(row['effective']['teds'], 4),
                      'accepted', row['gate_passed'], flush=True)
            else:
                failures.append(error); print(error, 'SCORING ERROR: retained in cohort, aggregate withheld', flush=True)
    verify(protected)
    manifest = read(root / 'prepared/manifest.json')
    runtime = {}
    for arm in ('baseline', 'paddle'):
        runs = read(root / arm / 'summary.json')['results']
        durations = [r['wall_seconds'] for r in runs]
        runtime[arm] = {'original_worker_statuses': dict(Counter(r['status'] for r in runs)),
                        'mean_cold_seconds': mean(durations), 'median_cold_seconds': median(durations),
                        'max_cold_seconds': max(durations), 'sum_cold_seconds': sum(durations),
                        'per_case': {r['id']: {'status': r['status'], 'seconds': r['wall_seconds']} for r in runs}}
    prior_reasons = Counter(); unclosed_tbody = []
    for item in manifest['cases']:
        trace = root / 'final' / item['id'] / 'grid-trace.json'
        if trace.is_file(): prior_reasons.update(read(trace).get('prior_gate', {}).get('reasons', []))
        structure = optional_text(root / 'paddle' / item['id'] / 'structure.html')
        if structure and structure.lower().count('<tbody>') > structure.lower().count('</tbody>'):
            unclosed_tbody.append(item['id'])
    report = {'experiment': 'omnidocbench-table-unseen-v12', 'cohort_size': len(final['results']),
              'scoring_errors': failures, 'aggregate': aggregate_scores(rows) if not failures else None,
              'scoring_workers': 2, 'scoring_timeout_seconds': 300,
              'input_integrity': True, 'paid_api_calls': 0, 'production_applied': False,
              'gold_access_in_inference': False, 'oracle_bbox': True,
              'metadata_subsets': dict(Counter(x['subset'] for x in manifest['cases'])),
              'manifest_sha256': sha(root / 'prepared/manifest.json'), 'final_sha256': sha(root / 'final/summary.json'),
              'scoring_code_sha256': sha(Path(__file__).resolve()),
              'gate_reasons': dict(Counter(r for row in final['results'] for r in row['gate']['reasons'])),
              'baseline_export_statuses': dict(Counter(r['baseline_status'] for r in final['results'])),
              'baseline_metadata_recoveries': sum(r['baseline_metadata_recovery'] for r in final['results']),
              'prior_v10_gate_reasons': dict(prior_reasons), 'runtime': runtime,
              'missing_explicit_tbody_close_cases': unclosed_tbody,
              'tbody_note': 'Diagnostic only; no tag insertion or candidate promotion was performed.',
              'results': rows,
              'limitations': ['Page-held-out from prior development; some pages share papers, no document-disjoint guarantee.',
                 'Gold bbox crops bypass full-page detection and boundary errors.',
                 'Frozen experimental v8 graph and v11 geometric gate; no production/RAG acceptance.',
                 'Fresh CPU inference, 240 seconds/case, no retries; failed outputs score zero.',
                 'Public benchmark model-training overlap unknown; no statistical generalization claim.',
                 'Coordinate/numeric/header diagnostics are not semantic QA correctness.']}
    write(output / 'results.json', report)
    links = ''.join('<li><a href="' + x['id'] + '/comparison.html">' + x['id'] + '</a></li>' for x in rows)
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>ScholarLens unseen-page tables v12</h1><ul>' + links + '</ul>', encoding='utf-8')
    print(json.dumps(report['aggregate'], ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True); p.add_argument('--worker', action='store_true')
    p.add_argument('--case'); p.add_argument('--output', type=Path); a = p.parse_args()
    if a.worker: score_case(a.root.resolve(), a.case, a.output.resolve())
    else: run(a.root.resolve())
