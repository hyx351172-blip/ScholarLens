"""Score rejected rereads as diagnostics; NEVER alter frozen admission or fallback."""
import argparse
import html
import os
from pathlib import Path
import sys

from audit_table_decoder import ROOT,read,write,sha,parse_html_table
from experiment_unseen_tables import DATA,verify
from table_structure import render_table_html
from table_ocr_binding import aligned_metrics,key,normalized
from score_vlm_table_experiment import safe_table


def compose_diagnostic(original_html,plan,mapped):
    structure=parse_html_table(original_html)[0]
    if set(mapped)!={c['cell_id'] for c in plan['cells']}:raise ValueError('Incomplete rereads')
    for c in plan['cells']:
        cell=structure['table_cells'][c['cell_id']]
        if key(cell)[:2]!=(c['row'],c['col']):raise ValueError('Cell identity drift')
        lines=sorted(mapped[c['cell_id']]['lines'],key=lambda a:(a['bbox'][1],a['bbox'][0]))
        # Includes ALL results, even low confidence. No filters to improve scores.
        cell['text']=' '.join(a['text'] for a in lines)
    return render_table_html(structure)


def run(root,output=None):
    summary=read(root/'summary.json');audit=Path(summary['audit']);source=Path(summary['source'])
    frozen={str(root/p):s for p,s in summary['artifact_sha256'].items()};verify(frozen)
    dest=output or root/'text-diagnostics';dest.mkdir()
    planfile=read(root/'plan.json');diagnostics=[]
    # Freeze deterministic diagnostic text before reading gold.
    for case,plan in planfile['plans'].items():
        if plan['status']!='eligible':continue
        mapped={c['cell_id']:read(root/case/f"cell-{c['cell_id']}-mapped.json") for c in plan['cells']}
        original=read(audit/case/'diagnostics.json')['grid']
        candidate=compose_diagnostic(original['html'],plan,mapped)
        path=dest/f'{case}-diagnostic-only.html';path.write_text(candidate,encoding='utf-8')
        diagnostics.append((case,plan,mapped,original,path))
    write(dest/'frozen-diagnostic-candidates.json',{str(p):sha(p) for *_,p in diagnostics})
    os.environ['MPLCONFIGDIR']=str(ROOT/'backend/data/benchmarks/model_cache/matplotlib')
    sys.path.insert(0,str(DATA/'evaluator'))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS
    gold=read(source/'scoring-only-gold.json');results=[]
    for case,plan,mapped,original,path in diagnostics:
        truth=gold[case]['html'];goldcells={key(c):c for c in parse_html_table(safe_table(truth))[0]['table_cells']}
        candidate=path.read_text(encoding='utf-8');arms={
            'previous_effective':(root/case/'previous-effective.html').read_text(encoding='utf-8'),
            'old_grid_partial':original['html'],'reread_diagnostic_only':candidate}
        scores={};review=['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
            '<style>body{font:15px system-ui;margin:24px}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:6px}</style>',
            '<h1>Rejected reread: diagnostics only</h1><p>All reread text retained, including low-confidence output. NOT admitted or deployed.</p>']
        for label,text in {**arms,'gold':truth}.items():
            review.extend(['<h2>'+html.escape(label)+'</h2>',safe_table(text)])
            if label=='gold':continue
            diag=aligned_metrics(text,truth);write(dest/f'{case}-{label}-cells.json',diag)
            scores[label]={'teds':TEDS().evaluate(normalized_html_table(text),normalized_html_table(truth)),
                'structure_teds':TEDS(structure_only=True).evaluate(normalized_html_table(text),normalized_html_table(truth)),
                'all_gold_cells':diag['all_gold_cells'],'numeric_cells':diag['numeric_cells']}
        review_path=dest/f'{case}-comparison.html';review_path.write_text(''.join(review),encoding='utf-8')
        per_cell=[];candidatecells=parse_html_table(candidate)[0]['table_cells']
        for c in plan['cells']:
            cid=c['cell_id'];before=original['cells'][cid]['text'];after=candidatecells[cid]['text'];truthcell=goldcells.get(key(candidatecells[cid]))
            per_cell.append({'cell_id':cid,'row':c['row'],'col':c['col'],'old_partial_text':before,
                'reread_text':after,'gold':truthcell['text'] if truthcell else None,
                'old_exact':bool(truthcell) and normalized(before)==normalized(truthcell['text']),
                'new_exact':bool(truthcell) and normalized(after)==normalized(truthcell['text']),
                'low_confidence':[l for l in mapped[cid]['lines'] if l['score']<.5]})
        results.append({'id':case,'scores':scores,'affected_cells':per_cell,'gate_unchanged':True})
    verify(frozen);verify(read(dest/'frozen-diagnostic-candidates.json'))
    write(dest/'results.json',{'results':results,'gold_used_to_select':False,'admission_changed':False,
        'production_applied':False,'interpretation':'Development diagnostics, not a held-out improvement claim.',
        'score_code_sha256':sha(Path(__file__).resolve()),'gold_sha256':sha(source/'scoring-only-gold.json')})
    for r in results:print(r['id'],r['scores'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args();run(args.root.resolve(),args.output.resolve() if args.output else None)
