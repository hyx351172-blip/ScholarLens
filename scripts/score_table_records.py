"""Independent official scoring after v14 outputs are frozen; never admits by gold."""
import argparse
import html
import os
from pathlib import Path
from statistics import mean
import sys

from audit_table_decoder import ROOT,read,write,sha
from experiment_unseen_tables import verify,DATA
from table_ocr_binding import aligned_metrics
from score_vlm_table_experiment import safe_table


def optional(path):return path.read_text(encoding='utf-8') if path.is_file() else None


def same_content(a,b):return a.is_file()==b.is_file() and (not a.is_file() or sha(a)==sha(b))


def run(root):
    summary=read(root/'summary.json');source=Path(summary['source'])
    gold_source=Path(read(source/'summary.json')['source'])
    protected=read(root/'input-integrity.json')
    protected.update({str(root/p):v for p,v in summary['artifact_sha256'].items()})
    for p in (root/'summary.json',Path(__file__).resolve(),source/'scored/results.json',gold_source/'scoring-only-gold.json'):
        protected[str(p)]=sha(p)
    verify(protected)
    output=root/'scored';output.mkdir();write(output/'scoring-inputs.json',protected)
    os.environ['MPLCONFIGDIR']=str(ROOT/'backend/data/benchmarks/model_cache/matplotlib')
    sys.path.insert(0,str(DATA/'evaluator'))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS
    previous={r['id']:r for r in read(source/'scored/results.json')['results']}
    gold=read(gold_source/'scoring-only-gold.json');rows=[]
    for info in summary['results']:
        case=info['id'];dest=output/case;dest.mkdir()
        final=root/'final'/case;effective=final/'effective.html'
        expected=final/('candidate.html' if info['gate']['passed'] else 'previous-effective.html')
        if not same_content(effective,expected) or (info['gate']['passed'] and not expected.is_file()):
            raise ValueError('Frozen gate/output drift')
        old=source/'final'/case/'effective.html'
        if not same_content(final/'previous-effective.html',old):raise ValueError('Previous fallback drift')
        reused=same_content(effective,old)
        prior={k:previous[case]['effective_v13'][k] for k in ('teds','structure_teds','missing_output')}
        diag=None
        if reused:score=dict(prior)
        elif not effective.is_file():score={'teds':0.,'structure_teds':0.,'missing_output':True}
        else:
            truth=normalized_html_table(gold[case]['html']);pred=normalized_html_table(optional(effective))
            score={'teds':TEDS().evaluate(pred,truth),'structure_teds':TEDS(structure_only=True).evaluate(pred,truth),
                   'missing_output':False}
            for label,text in [('gold',truth),('effective',pred)]:
                (dest/f'{label}.normalized.html').write_text(text,encoding='utf-8')
            try:diag=aligned_metrics(optional(effective),gold[case]['html'])
            except ValueError as exc:diag={'available':False,'reason':str(exc)}
            write(dest/'cell-diagnostics.json',diag)
        row={'id':case,'status':info['status'],'gate':info['gate'],'previous_v13':prior,'effective_v14':score,
             'delta_from_v13':score['teds']-prior['teds'],'score_reused_byte_identical':reused,
             'effective_source':info['effective_source']}
        rows.append(row);write(dest/'result.json',row)
        parts=['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
            '<style>body{font:15px system-ui;margin:24px}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:8px}</style>',
            '<h1>'+html.escape(case)+'</h1><p>Development only; gold does not select the output.</p>']
        for label,text in [('Gold',gold[case]['html']),('v13 effective',optional(old)),('v14 effective',optional(effective))]:
            parts+=['<h2>'+label+'</h2>',safe_table(text) if text else '<p>No output</p>']
        (dest/'comparison.html').write_text(''.join(parts),encoding='utf-8')
        print(case,round(score['teds'],6),'delta',round(row['delta_from_v13'],6),flush=True)
    verify(protected)
    aggregate={'cases':len(rows),'reconstructed':sum(r['status']=='reconstructed' for r in rows),
        'improved_vs_v13':sum(r['delta_from_v13']>1e-9 for r in rows),
        'regressed_vs_v13':sum(r['delta_from_v13']< -1e-9 for r in rows),
        'unchanged_vs_v13':sum(abs(r['delta_from_v13'])<=1e-9 for r in rows)}
    for arm in ('previous_v13','effective_v14'):
        for metric in ('teds','structure_teds'):aggregate[arm+'_'+metric]=mean(r[arm][metric] for r in rows)
    write(output/'results.json',{'experiment':'table-record-reconstruction-v14','cohort':'development-regression',
        'aggregate':aggregate,'results':rows,'protected_inputs_unchanged':True,'gold_access_in_inference':False,
        'production_applied':False,'model_calls':0,'paid_api_calls':0,'code_sha256':sha(Path(__file__).resolve()),
        'limitations':['Only one eligible real merged-row failure in this cohort.','Normal wrapping/spans mainly covered by synthetic negatives.',
            'Restricted typed record anchors, not general borderless-table recognition.','Unchanged scores reused after exact HTML hash equality.']})
    print(aggregate,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    run(p.parse_args().root.resolve())
