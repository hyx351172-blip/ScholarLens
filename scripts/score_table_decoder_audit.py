"""Gold-reading stage ONLY: strict-valid, structure-only TEDS for decoder v8.

No OCR text is predicted by this experiment. Never report full/content TEDS or
promote a candidate based on gold. Invalid candidates retain the Docling baseline.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import sys

from audit_table_decoder import read, write, sha, preflight, validate_output
from score_vlm_table_experiment import safe_table


def aggregate_structure(records):
    if not records:
        raise ValueError('No paired records')
    aggregate = {}
    for arm in ('original', 'extended'):
        values = [r['arms'][arm] for r in records]
        aggregate[arm] = {'table_count': len(values), 'valid_count': sum(v['valid'] for v in values),
                          'fallback_structure_teds': sum(v['fallback_structure_teds'] for v in values) / len(values),
                          'valid_candidates_structure_teds': [v['candidate_structure_teds'] for v in values if v['valid']]}
    return aggregate


def score(prepared, run_dir, gold_path, evaluator, previous_path, output):
    prepared, run_dir, gold_path, evaluator, previous_path, output = [p.resolve() for p in
        (prepared, run_dir, gold_path, evaluator, previous_path, output)]
    if any(output == p or p in output.parents or output in p.parents for p in (run_dir, gold_path, evaluator, previous_path)):
        raise ValueError('Score output overlaps evidence inputs')
    manifest = preflight(prepared, output)
    run = read(run_dir / 'summary.json')
    if (run['manifest_sha256'] != sha(prepared / 'manifest.json') or run.get('stopped')
            or not run.get('original_models_unchanged') or not run.get('frozen_inputs_unchanged')):
        raise ValueError('Unfinished, mismatched or mutated experiment')
    sys.path.insert(0, str(evaluator))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS

    metric = TEDS(structure_only=True)
    gold = {p['page_info']['image_path']: p for p in read(gold_path)}
    previous = {p['img_id']: p for p in read(previous_path)}
    records, views = [], []
    # Preflight all artifacts and reproduce baseline before writing the report.
    for item in manifest['results']:
        case, page = item['id'], item['page']
        tables = [d for d in gold[page]['layout_dets'] if d['category_type'] == 'table' and not d.get('ignore')]
        if len(tables) != 1:
            raise ValueError('Requires exactly one gold table per frozen crop')
        gold_html = normalized_html_table(tables[0]['html'])
        baseline_html = (prepared / case / 'baseline.html').read_text(encoding='utf-8')
        baseline = metric.evaluate(normalized_html_table(baseline_html), gold_html)
        if abs(baseline - previous[page]['metric']['TEDS_structure_only']) > 1e-9:
            raise ValueError('Baseline structure score does not reproduce v4')
        row = {'id': case, 'page': page, 'baseline_structure_teds': baseline, 'arms': {}}
        raw_arms = {}
        for arm in ('original', 'extended'):
            path = run_dir / arm / case
            result = read(path / 'result.json')
            raw = (path / 'structure.html').read_text(encoding='utf-8')
            valid = validate_output(raw, result)
            if valid != result['validation'] or result['crop_sha256'] != item['crop_sha256']:
                raise ValueError('Artifact/validation mismatch')
            value = metric.evaluate(normalized_html_table(raw), gold_html) if valid['valid'] else None
            row['arms'][arm] = {'valid': valid['valid'], 'candidate_structure_teds': value,
                               'fallback_structure_teds': value if value is not None else baseline,
                               'delta_vs_docling': value - baseline if value is not None else None,
                               'validation': valid, 'steps': result['steps'], 'eos_index': result['eos_index'],
                               'inference_seconds': result['inference_seconds'],
                               'artifact_sha256': {f: sha(path / f) for f in
                                                  ('result.json', 'decoder.json', 'decoder-tensors.npz', 'structure.html')}}
            raw_arms[arm] = raw
        records.append(row)
        views.append((case, tables[0]['html'], baseline_html, raw_arms, row))
    output.mkdir(parents=True)
    aggregate = aggregate_structure(records)
    report = {'experiment': 'table-decoder-v8-structure-only', 'manifest_sha256': sha(prepared / 'manifest.json'),
              'run_sha256': sha(run_dir / 'summary.json'), 'gold_sha256': sha(gold_path),
              'previous_sha256': sha(previous_path), 'baseline_matches_v4_all': True,
              'evaluator_sha256': {f: sha(evaluator / f) for f in
                                     ('src/core/preprocess/data_preprocess.py', 'src/metrics/table_metric.py')},
              'content_accuracy_evaluated': False, 'promotion_policy': 'none; offline only',
              'fallback_policy': 'strict-invalid retains baseline; valid candidates included even if worse than baseline',
              'aggregate': aggregate, 'results': records}
    write(output / 'results.json', report)
    sections = []
    for case, gold_raw, baseline_raw, arms, row in views:
        crop = html.escape(os.path.relpath(prepared / case / 'crop.png', output).replace('\\', '/'), quote=True)
        sections.append(f'<h2>{html.escape(case)}</h2><a href="{crop}">Frozen crop</a><pre>' +
                        html.escape(json.dumps(row, ensure_ascii=False, indent=2)) + '</pre><main>')
        for label, raw in [('Gold (scoring only)', gold_raw), ('Docling baseline', baseline_raw),
                           ('Original structure-only', arms['original']), ('Extended structure-only', arms['extended'])]:
            is_valid = label in ('Gold (scoring only)', 'Docling baseline') or row['arms']['extended' if label.startswith('Extended') else 'original']['valid']
            sections.append('<section><h3>' + label + '</h3>' + (safe_table(raw) if is_valid else '<pre>REJECTED\n' + html.escape(raw) + '</pre>') + '</section>')
        sections.append('</main>')
    (output / 'index.html').write_text(
        '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'">'
        '<title>ScholarLens table decoder audit v8</title><style>body{font:14px system-ui;margin:24px}main{display:flex;gap:20px}section{max-width:25%;overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:3px;min-width:6px;min-height:8px}pre{white-space:pre-wrap;max-height:300px;overflow:auto}</style>'
        '<h1>Structure-only decoder audit (no OCR text; not deployed)</h1>' + ''.join(sections), encoding='utf-8')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('prepared', 'run-dir', 'gold', 'evaluator', 'previous', 'output'):
        p.add_argument('--' + key, required=True, type=Path)
    a = p.parse_args()
    report = score(a.prepared, a.run_dir, a.gold, a.evaluator, a.previous, a.output)
    print(json.dumps(report['aggregate'], indent=2))


if __name__ == '__main__':
    main()
