"""Separate, post-freeze scoring. Gold cannot influence v17 admission."""
import argparse
import html
import os
from pathlib import Path
from statistics import mean
import sys

from audit_table_decoder import ROOT,read,write,sha
from experiment_unseen_tables import DATA,verify
from table_ocr_binding import aligned_metrics
from score_vlm_table_experiment import safe_table


def run(root):
    summary=read(root/'summary.json');source=Path(summary['source']);audit=Path(summary['audit'])
    protected={str(root/p):v for p,v in summary['artifact_sha256'].items()}
    for p in (root/'summary.json',source/'scoring-only-gold.json',Path(__file__).resolve()):protected[str(p)]=sha(p)
    verify(protected)
    dest=root/'scored';dest.mkdir();write(dest/'scoring-inputs.json',protected)
    os.environ['MPLCONFIGDIR']=str(ROOT/'backend/data/benchmarks/model_cache/matplotlib')
    sys.path.insert(0,str(DATA/'evaluator'))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS
    gold=read(source/'scoring-only-gold.json');rows=[]
    def optional(path):return path.read_text(encoding='utf-8') if path.is_file() else None
    for info in summary['results']:
        case=info['id'];out=dest/case;out.mkdir();folder=root/case
        previous=optional(folder/'previous-effective.html');candidate=optional(folder/'candidate.html');effective=optional(folder/'effective.html')
        if effective!=(candidate if info['gate']['passed'] else previous):raise ValueError('Frozen admission drift')
        original=audit/case/'effective.html'
        if original.is_file()!=(folder/'previous-effective.html').is_file():raise ValueError('Fallback presence changed')
        if original.is_file() and sha(original)!=sha(folder/'previous-effective.html'):raise ValueError('Fallback bytes changed')
        truth=normalized_html_table(gold[case]['html']);scores={}
        for label,text in [('previous',previous),('candidate',candidate),('effective',effective)]:
            if not text:
                scores[label]={'teds':0.,'structure_teds':0.,'missing':True};continue
            norm=normalized_html_table(text)
            scores[label]={'teds':TEDS().evaluate(norm,truth),'structure_teds':TEDS(structure_only=True).evaluate(norm,truth),'missing':False}
            if candidate:
                diagnostics=aligned_metrics(text,gold[case]['html']);write(out/f'{label}-cells.json',diagnostics)
                scores[label]['numeric_cells']=diagnostics['numeric_cells']
                scores[label]['all_gold_cells']=diagnostics['all_gold_cells']
        if candidate:
            original_partial=read(audit/case/'diagnostics.json')['grid']['html']
            diag=aligned_metrics(original_partial,gold[case]['html']);write(out/'old-grid-partial-cells.json',diag)
            scores['old_grid_partial']={'teds':TEDS().evaluate(normalized_html_table(original_partial),truth),
                'numeric_cells':diag['numeric_cells'],'all_gold_cells':diag['all_gold_cells'],
                'note':'Rejected partial OCR grid, not previous effective output'}
            review=['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
                '<style>body{font:15px system-ui;margin:24px}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:6px}</style>',
                '<h1>Development diagnostic comparison</h1><p>Rejected candidate is not deployed.</p>']
            for label,text in [('Gold',gold[case]['html']),('Previous effective',previous),('Old rejected partial grid',original_partial),('Reread candidate',candidate)]:
                review+=['<h2>'+html.escape(label)+'</h2>',safe_table(text)]
            (out/'comparison.html').write_text(''.join(review),encoding='utf-8')
        rows.append({'id':case,'status':info['status'],'gate':info['gate'],'scores':scores,'effective_changed':effective!=previous})
    verify(protected)
    aggregate={'cases':len(rows),'changed':sum(r['effective_changed'] for r in rows),
        'admitted':sum(r['gate']['passed'] for r in rows)}
    for arm in ('previous','effective'):
        for metric in ('teds','structure_teds'):aggregate[arm+'_'+metric]=mean(r['scores'][arm][metric] for r in rows)
    result={'experiment':'cell-ocr-v17','cohort':'diagnosed development cohort, NOT held-out',
        'aggregate':aggregate,'results':rows,'gold_access_in_inference':False,'production_applied':False,
        'local_ocr_calls_completed_run':summary['local_ocr_calls'],'paid_api_calls':0}
    write(dest/'results.json',result)
    print(aggregate)
    for row in rows:
        if row['scores']['candidate']['missing'] is False:print(row)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    run(p.parse_args().root.resolve())
