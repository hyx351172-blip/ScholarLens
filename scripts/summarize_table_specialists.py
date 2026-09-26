"""Compare already-scored table arms with matched provenance; never choose by gold."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import statistics


def summarize(scores):
    arms = [s['arm'] for s in scores]
    if not 2 <= len(arms) <= 4 or len(set(arms)) != len(arms) or any(
            a not in ('pp_tablemagic', 'qwen_native', 'generic_html', 'ocr_html') for a in arms):
        raise ValueError('Expected 2..4 distinct recognized arms')
    first = scores[0]
    pages = [r['page'] for r in first['results']]
    if not pages or len(set(pages)) != len(pages):
        raise ValueError('Empty or repeated pages')
    for s in scores:
        if not s['baseline_matches_v4_all'] or [r['page'] for r in s['results']] != pages:
            raise ValueError('Page pairing/baseline verification differs')
        for key in ('gold_sha256', 'manifest_sha256', 'evaluator_sha256'):
            if s[key] != first[key]:
                raise ValueError('Scoring provenance differs')
        for a, b in zip(first['results'], s['results']):
            if any(abs(a['baseline'][k] - b['baseline'][k]) > 1e-9 for k in ('teds', 'structure_only')):
                raise ValueError('Baseline metrics differ')
    result = {'experiment': 'omnidocbench-table-specialist-v7', 'schema_version': '1.0',
              **{k: first[k] for k in ('gold_sha256', 'manifest_sha256', 'evaluator_sha256')},
              'production_applied': False, 'gold_access_in_model_stage': False,
              'table_count': len(pages), 'arms': {}, 'tables': [],
              'limitations': ['Selected development crops, not held-out or full PDF/RAG evaluation.',
                  'Two electronics datasheets and one scientific benchmark; do not infer general paper quality.',
                  'Native task and model pipelines differ in prompting/preprocessing; not a single-variable ablation.',
                  'Schema validity does not imply correct cells; no gold-based best-of selection.',
                  'Paddle cold initialization/download excluded from inference time; not equivalent to API latency.',
                  'Invalid candidates are not scored as HTML; failed-as-zero is task completion, not raw TEDS.',
                  'Numeric multiset F1 ignores cell positions and is not cell numeric accuracy.']}
    for s in scores:
        rows = s['results']; runtimes = [r['runtime'] for r in rows]
        attempted = [r for r in runtimes if not r['status'].startswith('skipped')]
        known = [r['usage']['total_tokens'] for r in attempted if r.get('usage') and r['usage'].get('total_tokens') is not None]
        latencies = [r['latency_seconds'] for r in attempted if r.get('latency_seconds') is not None]
        valid = sum(r['candidate'] is not None for r in rows)
        regressions = [r['page'] for r in rows if r['candidate'] and r['candidate']['teds'] < r['baseline']['teds'] - 1e-9]
        result['arms'][s['arm']] = {**s['aggregate'], 'valid_candidates': valid,
            'calls_attempted': len(attempted), 'regression_pages': regressions,
            'mean_latency_seconds': statistics.mean(latencies) if latencies else None,
            'known_total_tokens': sum(known) if known else None,
            'calls_without_usage': len(attempted) - len(known) if s['arm'] != 'pp_tablemagic' else None,
            'smoke_gate_pass': valid == len(rows) and not regressions}
    for i, page in enumerate(pages):
        table = {'page': page, 'baseline': first['results'][i]['baseline']}
        for s in scores:
            r = s['results'][i]
            table[s['arm']] = {k: r[k] for k in ('candidate', 'effective', 'runtime')}
        result['tables'].append(table)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scores', nargs='+', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    paths, output = [p.resolve() for p in args.scores], args.output_dir.resolve()
    if output.exists() or any(output == p.parent or output in p.parents or p.parent in output.parents for p in paths):
        raise ValueError('Use a fresh output directory outside scored inputs')
    scores = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    result = summarize(scores)
    root = Path(__file__).resolve().parents[1]
    result['inputs_sha256'] = {os.path.relpath(p, root).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    output.mkdir(parents=True)
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    links = ''.join(f'<li><a href="{html.escape(os.path.relpath(p.parent / "index.html", output).replace(chr(92), "/"), quote=True)}">{html.escape(s["arm"])}</a></li>' for p, s in zip(paths, scores))
    headers = ''.join('<th>' + html.escape(s['arm']) + '</th>' for s in scores)
    rows = []
    for row in result['tables']:
        cells = []
        for s in scores:
            r = row[s['arm']]
            cells.append('<td>' + (f'TEDS {r["candidate"]["teds"]:.6f}' if r['candidate'] else html.escape(r['runtime'].get('validation_error') or r['runtime']['status'])) + '</td>')
        rows.append(f'<tr><td>{html.escape(row["page"])}</td><td>{row["baseline"]["teds"]:.6f}</td>' + ''.join(cells) + '</tr>')
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><style>body{font:15px system-ui;margin:28px;color:#222}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:12px}pre{white-space:pre-wrap}</style><h1>ScholarLens — table specialists v7</h1><p>Development comparison, no production deployment. Invalid candidates retain baseline.</p><ul>' + links + '</ul><table><tr><th>Page</th><th>Docling baseline</th>' + headers + '</tr>' + ''.join(rows) + '</table><pre>' + html.escape(json.dumps(result, ensure_ascii=False, indent=2)) + '</pre>', encoding='utf-8')
    print(json.dumps(result['arms'], indent=2))


if __name__ == '__main__':
    main()
