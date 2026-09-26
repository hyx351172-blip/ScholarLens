"""Post-scoring audit: preserve raw official values, diagnose out-of-range TEDS."""
import argparse
import os
import sys
from pathlib import Path
from audit_table_decoder import ROOT, read, write, sha


def audit(root):
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'backend/data/benchmarks/model_cache/matplotlib'))
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    evaluator = ROOT / 'backend/data/benchmarks/omnidocbench/evaluator'
    sys.path.insert(0, str(evaluator))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS, APTED, CustomConfig
    from lxml import html
    scores = root / 'scored/results.json'; before = sha(scores); result = read(scores)
    gold = read(root / 'scoring-only-gold.json'); anomalies = []
    for row in result['results']:
        for arm in ('baseline', 'candidate_diagnostic', 'raw_paddle_diagnostic'):
            score = row[arm]
            if not score or 0 <= score['teds'] <= 1: continue
            label = {'baseline': 'baseline', 'candidate_diagnostic': 'candidate', 'raw_paddle_diagnostic': 'raw-paddle'}[arm]
            pred_path = root / 'scored' / row['id'] / (label + '.normalized.html')
            pred_raw = pred_path.read_text(encoding='utf-8')
            gold_raw = normalized_html_table(gold[row['id']]['html'])
            parser = html.HTMLParser(remove_comments=True, encoding='utf-8')
            pred = html.fromstring(pred_raw, parser=parser).xpath('body/table')[0]
            true = html.fromstring(gold_raw, parser=parser).xpath('body/table')[0]
            np, ng = len(pred.xpath('.//*')), len(true.xpath('.//*'))
            scorer = TEDS()
            distance = APTED(scorer.load_html_tree(pred), scorer.load_html_tree(true), CustomConfig()).compute_edit_distance()
            reproduced = 1. - float(distance) / max(np, ng)
            if abs(reproduced-score['teds']) > 1e-10: raise ValueError('Official score not reproducible')
            anomalies.append({'id': row['id'], 'arm': arm, 'raw_teds': score['teds'],
                'prediction_descendant_nodes': np, 'gold_descendant_nodes': ng,
                'edit_distance': float(distance), 'normalization_denominator': max(np, ng),
                'reproduced_teds': reproduced, 'prediction_sha256': sha(pred_path)})
    if sha(scores) != before: raise ValueError('Frozen scoring output changed')
    n = result['cohort_size']
    output = root / 'score-range-audit.json'
    if output.exists(): raise ValueError('Fresh audit output required')
    report = {'source_results_sha256': before, 'audit_code_sha256': sha(Path(__file__).resolve()),
              'official_metric_sha256': sha(evaluator / 'src/metrics/table_metric.py'),
              'original_scores_unchanged': True, 'out_of_range': anomalies,
              'diagnostic_only_clipped_means': {arm: sum(max(0., min(1., r[arm]['teds'])) for r in result['results']) / n
                                              for arm in ('baseline', 'effective')},
              'note': 'Official formula is 1 - edit_distance / max(descendant_node_counts), without clipping. Clipped means are explicitly post-hoc sensitivity diagnostics, never replacements for the frozen official scores.'}
    write(output, report)
    print(report, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--root', required=True, type=Path)
    audit(p.parse_args().root.resolve())
