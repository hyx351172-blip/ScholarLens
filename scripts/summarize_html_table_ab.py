"""Join two already-scored arms, without choosing candidates by gold accuracy."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import statistics

ARMS = ('generic_html', 'ocr_html')


def summarize(scores):
    if len(scores) != 2 or {s['arm'] for s in scores} != set(ARMS):
        raise ValueError('Expected exactly generic_html and ocr_html scores')
    a, b = scores
    for key in ('gold_sha256', 'manifest_sha256', 'evaluator_sha256'):
        if a[key] != b[key]:
            raise ValueError('Scoring provenance differs across arms')
    pages = [r['page'] for r in a['results']]
    if len(set(pages)) != len(pages) or pages != [r['page'] for r in b['results']]:
        raise ValueError('Page pairing differs across arms')
    result = {'schema_version': '1.0', 'experiment': 'omnidocbench-table-html-v6',
              'gold_sha256': a['gold_sha256'], 'manifest_sha256': a['manifest_sha256'],
              'evaluator_sha256': a['evaluator_sha256'], 'gold_access_in_model_stage': False,
              'production_applied': False, 'table_count': len(pages), 'arms': {}, 'tables': [],
              'heldout_gate': 'At least one arm must have all valid candidates and no TEDS regression on the fixed smoke set; not a quality guarantee.',
              'limitations': ['Three selected development tables, not an independent held-out set or full PDF evaluation.',
                 'HTML well-formedness does not prove cell accuracy. Numeric multiset F1 ignores cell alignment.',
                 'Usage totals include only returned usage, not unreported billable usage; currency cost is not inferred.',
                 'The v5 JSON run is historical, not a controlled JSON-vs-HTML format ablation.',
                 'No production parser, chunker, retrieval, database or frontend integration in this experiment.']}
    for left, right in zip(a['results'], b['results']):
        for key in ('teds', 'structure_only'):
            if abs(left['baseline'][key] - right['baseline'][key]) > 1e-9:
                raise ValueError('Baseline metrics differ across arms')
    for s in scores:
        runtimes = [r['runtime'] for r in s['results']]
        attempted = [r for r in runtimes if not r['status'].startswith('skipped')]
        latencies = [r['latency_seconds'] for r in attempted if r.get('latency_seconds') is not None]
        first_text = [r['first_text_seconds'] for r in attempted if r.get('first_text_seconds') is not None]
        valid = sum(r['candidate'] is not None for r in s['results'])
        regressions = [r['page'] for r in s['results'] if r['candidate_teds_delta'] is not None and r['candidate_teds_delta'] < -1e-9]
        result['arms'][s['arm']] = {**s['aggregate'],
            'baseline_matches_v4_all': s['baseline_matches_v4_all'],
            'valid_candidates': valid, 'calls_attempted': len(attempted),
            'regression_pages': regressions,
            'mean_latency_seconds': statistics.mean(latencies) if latencies else None,
            'mean_first_text_seconds': statistics.mean(first_text) if first_text else None,
            'known_total_tokens': sum((r.get('usage') or {}).get('total_tokens', 0) or 0 for r in attempted),
            'attempted_calls_without_usage': sum(not r.get('usage') or r['usage'].get('total_tokens') is None for r in attempted),
            'smoke_gate_pass': bool(pages) and valid == len(pages) and not regressions and s['baseline_matches_v4_all']}
    for i, page in enumerate(pages):
        row = {'page': page, 'baseline_teds': a['results'][i]['baseline']['teds'],
               'baseline_structure_only': a['results'][i]['baseline']['structure_only']}
        for s in scores:
            r = s['results'][i]
            row[s['arm']] = {'status': r['runtime']['status'],
                'candidate_teds': r['candidate']['teds'] if r['candidate'] else None,
                'effective_teds': r['effective']['teds'], 'delta': r['candidate_teds_delta'],
                'candidate_structure_only': r['candidate']['structure_only'] if r['candidate'] else None,
                'candidate_numeric_token_f1': r['candidate']['numeric_token_multiset']['f1'] if r['candidate'] else None,
                'latency_seconds': r['runtime'].get('latency_seconds'),
                'validation_error': r['runtime'].get('validation_error')}
        result['tables'].append(row)
    result['ready_for_heldout_expansion'] = any(s['smoke_gate_pass'] for s in result['arms'].values())
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generic-score', type=Path, required=True)
    p.add_argument('--ocr-score', type=Path, required=True)
    p.add_argument('--run-summary', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    paths = [args.generic_score.resolve(), args.ocr_score.resolve(), args.run_summary.resolve()]
    out = args.output_dir.resolve()
    if out.exists() or any(out == q or out in q.parents or q.parent in out.parents for q in paths):
        raise ValueError('Use a fresh output directory outside inputs')
    scores = [json.loads(q.read_text(encoding='utf-8')) for q in paths[:2]]
    result = summarize(scores)
    run = json.loads(paths[2].read_text(encoding='utf-8'))
    if run['manifest_sha256'] != result['manifest_sha256']:
        raise ValueError('Run and score provenance mismatch')
    result['run_settings'] = {k: run[k] for k in ('prompt_sha256', 'max_calls', 'calls_attempted', 'sdk_retries', 'arms')}
    result['inputs_sha256'] = {str(q): hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    out.mkdir(parents=True)
    (out / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    import os
    links = ''.join('<li><a href="' + html.escape(os.path.relpath(q.parent / 'index.html', out).replace('\\', '/'), quote=True) + '">' + label + '</a></li>'
                    for q, label in zip(paths[:2], ['Qwen3-VL + HTML', 'Qwen-OCR + HTML']))
    (out / 'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>ScholarLens HTML table A/B v6</h1><p>Offline development experiment, not deployed.</p><ul>' + links + '</ul><pre>' + html.escape(json.dumps(result, ensure_ascii=False, indent=2)) + '</pre>', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('arms', 'ready_for_heldout_expansion')}, indent=2))


if __name__ == '__main__':
    main()
