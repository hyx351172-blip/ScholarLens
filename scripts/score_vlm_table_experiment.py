"""Gold-only scoring/visualization stage; never imports or calls a VLM client.

Run in the pinned OmniDocBench evaluation environment. Reuses its unmodified
normalization/TEDS implementation for fixed 1:1 table pairs (not E2E matching).
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import time


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SafeTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.texts = [], []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.suppressed += 1
        if self.suppressed:
            return
        if tag in {"table", "tr", "td", "th"}:
            spans = ""
            if tag in {"td", "th"}:
                for k, v in attrs:
                    if k in {"colspan", "rowspan"} and v and v.isascii() and v.isdigit() and 1 <= int(v) <= 5000:
                        spans += f' {k}="{int(v)}"'
            self.parts.append(f'<{tag}{spans}>')
        elif tag == "br":
            self.parts.append('<br>')
            self.texts.append(' ')

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.suppressed = max(0, self.suppressed - 1)
            return
        if not self.suppressed and tag in {"table", "tr", "td", "th"}:
            self.parts.append(f'</{tag}>')
            self.texts.append(' ')

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(html.escape(data))
            self.texts.append(data)


def safe_table(raw):
    parser = SafeTableParser(); parser.feed(raw)
    return ''.join(parser.parts)


def numeric_diagnostic(pred, gold):
    """Surface numeric multiset only. NOT numeric cell accuracy or alignment."""
    def tokens(raw):
        parser = SafeTableParser(); parser.feed(raw)
        return Counter(re.findall(r'(?<![A-Za-z0-9.])[+-]?\d+(?:\.\d+)?(?![A-Za-z0-9.])', ''.join(parser.texts)))
    p, g = tokens(pred), tokens(gold)
    overlap = sum((p & g).values())
    pn, gn = sum(p.values()), sum(g.values())
    precision = overlap / pn if pn else float(not gn)
    recall = overlap / gn if gn else float(not pn)
    return {'precision': precision, 'recall': recall,
            'f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            'pred_count': pn, 'gold_count': gn, 'matched_count': overlap,
            'missing': dict(g - p), 'extra': dict(p - g)}


def aggregate_pairs(records):
    n = len(records)
    if not n:
        raise ValueError('No paired results')
    return {'table_count': n,
            'candidate_valid_count': sum(r['candidate'] is not None for r in records),
            'baseline_teds': sum(r['baseline']['teds'] for r in records) / n,
            'candidate_teds_failed_as_zero': sum((r['candidate'] or {}).get('teds', 0) for r in records) / n,
            'fallback_teds': sum(r['effective']['teds'] for r in records) / n,
            'fallback_policy': 'schema-invalid/request failure retains baseline; never select by gold'}


def inspect_response(raw, response_format='json'):
    """Describe even rejected grids, without repairing them or consulting gold."""
    if response_format == 'html':
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend/Information-Extraction/unified/parsers'))
        from html_table_candidate import parse_html_table
        try:
            structure, _ = parse_html_table(raw)
        except ValueError as exc:
            return {'html_valid': False, 'validation_error': str(exc)}
        return {'html_valid': True, 'rows': structure['num_rows'], 'cols': structure['num_cols'],
                'cell_count': len(structure['table_cells']), 'uncertain_cells': structure['uncertain_cells'],
                'note': 'Syntactic diagnosis only; stream completion is checked separately.'}
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError):
        return {'json_valid': False}
    if not isinstance(obj, dict):
        return {'json_valid': True, 'object_valid': False}
    rows, cols, cells = obj.get('rows'), obj.get('cols'), obj.get('cells')
    result = {'json_valid': True, 'rows': rows, 'cols': cols,
              'cell_count': len(cells) if isinstance(cells, list) else None}
    if (type(rows) is not int or type(cols) is not int or not 0 < rows * cols <= 5000
            or rows <= 0 or cols <= 0 or not isinstance(cells, list) or len(cells) > 5000):
        return result
    occupancy, out_of_bounds, malformed, uncertain = Counter(), [], [], []
    for index, cell in enumerate(cells):
        if not isinstance(cell, list) or len(cell) != 7 or any(type(n) is not int for n in cell[:4]):
            malformed.append(index); continue
        r, c, rs, cs, _, _, unknown = cell
        if unknown:
            uncertain.append(index)
        if not (rs > 0 and cs > 0 and 0 <= r < r + rs <= rows and 0 <= c < c + cs <= cols):
            out_of_bounds.append(index); continue
        occupancy.update((rr, cc) for rr in range(r, r + rs) for cc in range(c, c + cs))
    result.update(overlap_slots=sum(n > 1 for n in occupancy.values()),
                  uncovered_slots=rows * cols - len(occupancy),
                  out_of_bounds_cell_indices=out_of_bounds, malformed_cell_indices=malformed,
                  uncertain_cell_indices=uncertain)
    return result


def score(prepared, run_dir, gold_path, evaluator, output, previous_results):
    prepared, run_dir, gold_path, evaluator, output = [p.resolve() for p in (prepared, run_dir, gold_path, evaluator, output)]
    if output.exists() or any(output == p or p in output.parents or output in p.parents for p in (prepared, run_dir, gold_path, evaluator)):
        raise ValueError('Use a fresh output directory outside the inputs')
    sys.path.insert(0, str(evaluator))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS
    import Levenshtein

    manifest, run = read_json(prepared / 'manifest.json'), read_json(run_dir / 'summary.json')
    if run['manifest_sha256'] != sha(prepared / 'manifest.json'):
        raise ValueError('Run and preparation do not match')
    gold = {p['page_info']['image_path']: p for p in read_json(gold_path)}
    previous = {p['img_id']: p for p in read_json(previous_results)}
    output.mkdir(parents=True)
    records, toc = [], []
    baseline_check = True
    for item in manifest['results']:
        name, case = item['page'], item['id']
        if Path(case).name != case or case in ('.', '..'):
            raise ValueError('Invalid case identifier')
        gs = [d for d in gold[name]['layout_dets'] if d['category_type'] == 'table' and not d.get('ignore')]
        if len(gs) != 1:
            raise ValueError('Fixed pairing requires exactly one gold table')
        baseline_path = prepared / case / 'baseline.html'
        if sha(baseline_path) != item['baseline_sha256']:
            raise ValueError('Baseline was modified')
        raw_gold, raw_baseline = gs[0]['html'], baseline_path.read_text(encoding='utf-8')
        gold_norm = normalized_html_table(raw_gold)
        runtime = next(r for r in run['results'] if r['id'] == case)
        response_path = run_dir / case / 'response.json'
        response_text = read_json(response_path).get('content') if response_path.is_file() else None
        raw_candidate = (run_dir / case / 'candidate.html').read_text(encoding='utf-8') if runtime['status'] == 'valid_candidate_review_required' else None
        normalized = {'gold': gold_norm}

        def metrics(raw, label):
            norm = normalized_html_table(raw)
            normalized[label] = norm
            started = time.monotonic()
            result = {'teds': TEDS().evaluate(norm, gold_norm),
                      'structure_only': TEDS(structure_only=True).evaluate(norm, gold_norm),
                      'html_edit_distance': Levenshtein.distance(norm, gold_norm) / max(len(norm), len(gold_norm), 1),
                      'numeric_token_multiset': numeric_diagnostic(norm, gold_norm)}
            result['score_seconds'] = round(time.monotonic() - started, 3)
            return result

        baseline = metrics(raw_baseline, 'baseline')
        candidate = metrics(raw_candidate, 'candidate') if raw_candidate is not None else None
        matches_v4 = (abs(baseline['teds'] - previous[name]['metric']['TEDS']) < 1e-9
                      and abs(baseline['structure_only'] - previous[name]['metric']['TEDS_structure_only']) < 1e-9)
        baseline_check = baseline_check and matches_v4
        record = {'page': name, 'baseline': baseline, 'candidate': candidate,
                  'effective': candidate if candidate else baseline, 'runtime': runtime,
                  'raw_candidate_diagnostics': inspect_response(response_text, run.get('response_format', 'json')),
                  'baseline_matches_v4': matches_v4,
                  'candidate_teds_delta': candidate['teds'] - baseline['teds'] if candidate else None}
        records.append(record)
        dest = output / case; dest.mkdir()
        for label, value in normalized.items():
            (dest / f'{label}.normalized.html').write_text(value, encoding='utf-8')
        def rel(path):
            return html.escape(os.path.relpath(path, dest).replace('\\', '/'), quote=True)
        report = ['<!doctype html><meta charset="utf-8">',
                  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'">',
                  '<style>body{font:14px system-ui;margin:20px;color:#20202b}section{overflow:auto;max-height:90vh;border:1px solid #ddd;padding:12px}main{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}img{max-width:48%}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:4px;white-space:pre-wrap}pre{white-space:pre-wrap}</style>',
                  f'<h1>{html.escape(name)}</h1><p>Offline development set. Gold is for scoring only. No production replacement.</p>',
                  f'<a href="{rel(Path(manifest["images"]) / name)}">Full page</a> | <a href="{rel(prepared / case / "native-overlay.png")}">Native cell overlay</a>',
                  f'<p><img src="{rel(prepared / case / "crop.png")}"><img src="{rel(prepared / case / "native-overlay.png")}"></p>',
                  '<details><summary>Metrics / runtime</summary><pre>' + html.escape(json.dumps(record, ensure_ascii=False, indent=2)) + '</pre></details><main>']
        for title, raw in [('Docling baseline', raw_baseline), ('Gold (scoring only)', raw_gold), ('Model candidate (not deployed)', raw_candidate)]:
            report += ['<section><h2>' + title + '</h2>', safe_table(raw) if raw else '<p>No valid candidate; baseline retained.</p>', '</section>']
        report.append('</main>')
        if response_text:
            report.append('<details><summary>Raw model response (including rejected cells; not repaired)</summary><pre>'
                          + html.escape(response_text) + '</pre></details>')
        (dest / 'comparison.html').write_text(''.join(report), encoding='utf-8')
        toc.append(f'<li><a href="{html.escape(case)}/comparison.html">{html.escape(name)}</a></li>')
        print(f'{name}: baseline={baseline["teds"]:.6f}, candidate={candidate["teds"] if candidate else "invalid"}, v4_match={matches_v4}', flush=True)
    experiment = run.get('experiment', 'omnidocbench-table-vlm-v5')
    result = {'schema_version': '1.0', 'experiment': experiment,
              'arm': run.get('arm'),
              'scope': '3 fixed development table pairs; not a full E2E or held-out benchmark',
              'gold_sha256': sha(gold_path), 'gold_access_in_model_stage': False,
              'manifest_sha256': sha(prepared / 'manifest.json'), 'run_sha256': sha(run_dir / 'summary.json'),
              'evaluator': 'pinned OmniDocBench normalized_html_table + TEDS; direct 1:1 table scoring',
              'evaluator_sha256': {file: sha(evaluator / file) for file in [
                  'src/core/preprocess/data_preprocess.py', 'src/metrics/table_metric.py']},
              'baseline_matches_v4_all': baseline_check,
              'aggregate': aggregate_pairs(records), 'results': records,
              'limitations': ['Only 3 development tables, selected after observing baseline errors.',
                              'Numeric token multiset ignores cell alignment, labels, units and values with letters; not cell numeric accuracy.',
                              'Fallback aggregate uses schema validity only, not gold-based best-of selection.',
                              'No downstream retrieval, generation, chunking or production integration tested.']}
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>ScholarLens — ' + html.escape(experiment) + '</h1><p>Offline paired diagnostics, no production changes.</p><ul>' + ''.join(toc) + '</ul>', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared-dir', 'run-dir', 'gold', 'evaluator', 'output-dir', 'previous-results'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = score(args.prepared_dir, args.run_dir, args.gold, args.evaluator, args.output_dir, args.previous_results)
    print(json.dumps(result['aggregate'], indent=2))
    return 0 if result['baseline_matches_v4_all'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
