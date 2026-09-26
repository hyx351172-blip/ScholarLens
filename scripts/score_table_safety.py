"""Score frozen v13 outputs; reuse v12 scores only for byte-identical artifacts."""
import argparse
import html
import os
from pathlib import Path
import sys
from statistics import mean
from audit_table_decoder import ROOT, read, write, sha
from experiment_unseen_tables import verify, DATA
from score_vlm_table_experiment import safe_table


def run(root):
    summary=read(root/'summary.json'); source=Path(summary['source'])
    protected={str(root/p):digest for p,digest in summary['artifact_sha256'].items()}
    protected.update(read(root/'input-integrity.json'))
    protected[str(root/'summary.json')]=sha(root/'summary.json')
    protected[str(Path(__file__).resolve())]=sha(Path(__file__).resolve())
    verify(protected)
    dest=root/'scored';dest.mkdir()
    write(dest/'scoring-inputs.json',protected)
    os.environ['MPLCONFIGDIR']=str(ROOT/'backend/data/benchmarks/model_cache/matplotlib')
    sys.path.insert(0,str(DATA/'evaluator'))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS
    prior={r['id']:r for r in read(source/'scored/results.json')['results']}
    gold=read(source/'scoring-only-gold.json')
    rows=[]
    for info in summary['results']:
        case=info['id']; out=dest/case;out.mkdir()
        new=root/'final'/case/'effective.html'; old=source/'final'/case/'effective.html'
        chosen=root/'final'/case/('candidate.html' if info['gate']['passed'] else 'baseline.html')
        if new.is_file()!=chosen.is_file() or (new.is_file() and sha(new)!=sha(chosen)):
            raise ValueError('Frozen gate/output drift')
        if info['gate']['passed'] and not chosen.is_file():raise ValueError('Passing gate without candidate')
        same=(new.is_file()==old.is_file()) and (not new.is_file() or sha(new)==sha(old))
        metrics={};g=normalized_html_table(gold[case]['html'])
        def score(path):
            if not path.is_file():return {'teds':0.,'structure_teds':0.,'missing_output':True}
            norm=normalized_html_table(path.read_text(encoding='utf-8'))
            return {'teds':TEDS().evaluate(norm,g),'structure_teds':TEDS(structure_only=True).evaluate(norm,g),
                    'missing_output':False}
        if same:
            metrics={k:prior[case]['effective'][k] for k in ('teds','structure_teds','missing_output')}
        else: metrics=score(new)
        row={'id':case,'angle_ccw':info['angle_ccw'],'gate':info['gate'],'effective_source':info['effective_source'],
             'score_reused_byte_identical':same,'baseline_v12':prior[case]['baseline'],
             'effective_v12':prior[case]['effective'],'effective_v13':metrics}
        raw=root/'fresh'/case/'paddle/raw.html'
        if raw.is_file():row['oriented_paddle_raw_diagnostic']=score(raw)
        row['delta_from_v12']=metrics['teds']-prior[case]['effective']['teds']
        rows.append(row);write(out/'result.json',row)
        parts=['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
               '<style>body{font:14px system-ui;margin:20px}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:3px}</style>',
               '<h1>'+html.escape(case)+'</h1>']
        for title,text in [('Gold',gold[case]['html']),('Previous effective',old.read_text(encoding='utf-8') if old.is_file() else None),
                           ('V13 effective',new.read_text(encoding='utf-8') if new.is_file() else None)]:
            parts+=['<h2>'+title+'</h2>',safe_table(text) if text else '<p>No output</p>']
        (out/'comparison.html').write_text(''.join(parts),encoding='utf-8')
        print(case,metrics['teds'],row['delta_from_v12'],'reused',same,flush=True)
    verify(protected)
    aggregate={'cases':len(rows),'accepted_candidates':sum(r['gate']['passed'] for r in rows),
               'rotated':sum(r['angle_ccw']!=0 for r in rows),
               'improved_vs_v12':sum(r['delta_from_v12']>1e-9 for r in rows),
               'regressed_vs_v12':sum(r['delta_from_v12']< -1e-9 for r in rows),
               'unchanged_vs_v12':sum(abs(r['delta_from_v12'])<=1e-9 for r in rows)}
    for arm in ('baseline_v12','effective_v12','effective_v13'):
        for metric in ('teds','structure_teds'):aggregate[arm+'_'+metric]=mean(r[arm][metric] for r in rows)
    result={'experiment':'table-safety-v13','aggregate':aggregate,'results':rows,
            'cohort':'development-regression','gold_access_in_inference':False,'production_applied':False,
            'protected_inputs_unchanged':True,'scoring_code_sha256':sha(Path(__file__).resolve()),
            'notes':['Scores reused only after exact effective HTML hash equality and frozen input verification.',
                     'Raw official TEDS retained, no negative-score clipping.','No new held-out or RAG-quality claim.']}
    write(dest/'results.json',result)
    print(aggregate,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    run(p.parse_args().root.resolve())
