"""Frozen prospective page-level v14 validation; no production edits or paid APIs.

Prepare may read annotation crops/gold. Inference/finalize never read gold HTML.
Selection is not stratified by repair outcome; missing eligible positives remain
a coverage failure, never silently replaced with easier examples.
"""
import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_table_decoder import read, write, sha
from experiment_unseen_tables import DATA, select_cases, freeze_inputs, verify, run_arm, finalize


def excluded_pages(root):
    names = set(); sources = []
    for path in sorted(root.rglob('manifest.json')):
        value = read(path)
        cases = value.get('cases', []) if isinstance(value, dict) else []
        found = {c['page'] for c in cases if 'page' in c}
        if found:
            names.update(found); sources.append(path)
    for path in sorted(root.glob('*/selected_annotations.json')):
        names.update(p['page_info']['image_path'] for p in read(path)); sources.append(path)
    return names, sources


def prepare(root, count):
    from PIL import Image
    if root.exists(): raise ValueError('Fresh output required')
    excluded, exclusion_files = excluded_pages(ROOT / 'output/benchmarks')
    source = DATA / 'OmniDocBench_academic_en_100.json'
    pages = read(source); cases = select_cases(pages, excluded, count)
    protected = freeze_inputs()
    for path in [source, Path(__file__).resolve(), *exclusion_files,
                 ROOT/'scripts/table_candidate_safety.py', ROOT/'scripts/table_record_reconstruction.py']:
        protected[str(path)] = sha(path)
    root.mkdir(); (root/'prepared').mkdir(); gold = {}
    bypage = {p['page_info']['image_path']: p for p in pages}
    for case in cases:
        src = DATA/'images_academic_en_100'/case['page']; protected[str(src)] = sha(src)
        with Image.open(src) as image:
            l,t,r,b = case['bbox']
            box = (max(0,math.floor(l)-12), max(0,math.floor(t)-12),
                   min(image.width,math.ceil(r)+12), min(image.height,math.ceil(b)+12))
            if (box[2]-box[0])*(box[3]-box[1]) > 40_000_000: raise ValueError('Crop exceeds budget')
            dest = root/'prepared'/(case['id']+'.png'); image.convert('RGB').crop(box).save(dest)
        case.update(crop=dest.name,crop_sha256=sha(dest),crop_bbox=list(box))
        protected[str(dest)] = sha(dest)
        table = next(d for d in bypage[case['page']]['layout_dets'] if str(d['anno_id'])==case['anno_id'])
        gold[case['id']] = {'html':table['html'],'page':case['page'],'anno_id':case['anno_id']}
    write(root/'prepared/manifest.json',{'cases':cases,'excluded_pages':sorted(excluded),
        'selection':'frozen v12 hash ranking, round-robin subsets; exclude all prior manifests/pages',
        'oracle_bbox':True,'independence':'new pages, not verified document-disjoint or model-training-disjoint',
        'gold_access_in_inference':False})
    write(root/'scoring-only-gold.json',gold)
    for name in ('prepared/manifest.json','scoring-only-gold.json'):
        protected[str(root/name)] = sha(root/name)
    write(root/'frozen-inputs.json',protected)
    print('Frozen',len(cases),'new pages; excluded',len(excluded),flush=True)


def compare(trace, baseline):
    from table_candidate_safety import guard_candidate
    from table_record_reconstruction import reconstruct_records
    old = guard_candidate(trace); new = reconstruct_records(old)
    def effective(t):
        if t['gate']['passed']:
            if not t.get('html'): raise ValueError('Passing gate without HTML')
            return t['html']
        return baseline
    a,b = effective(old),effective(new)
    status = new.get('record_reconstruction',{}).get('status','unchanged')
    if status!='reconstructed' and a!=b: raise ValueError('Unexpected output drift')
    return old,new,a,b


def finish(root):
    if (root/'validation').exists(): raise ValueError('Fresh validation required')
    protected = read(root/'frozen-inputs.json'); verify(protected)
    finalize(root)  # Frozen v11 builder; keeps the same baseline for both arms.
    rows=[]; output=root/'validation'; output.mkdir()
    for item in read(root/'prepared/manifest.json')['cases']:
        case=item['id']; src=root/'final'/case; dest=output/case; dest.mkdir()
        path=src/'grid-trace.json'
        trace=read(path) if path.is_file() else {'gate':read(src/'result.json')['gate']}
        base=root/'baseline'/case/'candidate.html'
        baseline=base.read_text(encoding='utf-8') if base.is_file() and read(root/'baseline'/case/'result.json')['status']=='completed' else None
        old,new,a,b=compare(trace,baseline)
        for name,text in [('v13',a),('v14',b)]:
            if text is not None:(dest/(name+'.html')).write_text(text,encoding='utf-8')
        write(dest/'v13-trace.json',old);write(dest/'v14-trace.json',new)
        row={'id':case,'page':item['page'],'v13_gate':old['gate'],'v14_gate':new['gate'],
            'status':new.get('record_reconstruction',{}).get('status','unchanged'),
            'repair_reasons':new.get('record_reconstruction',{}).get('reasons',[]),
            'output_changed':a!=b,'missing_output':b is None}
        rows.append(row);print(case,row['status'],row['v13_gate'],flush=True)
    verify(protected)
    artifacts={p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()}
    write(output/'summary.json',{'results':rows,'artifact_sha256':artifacts,'paid_api_calls':0,
        'gold_access_in_inference':False,'production_applied':False,'orientation_repair':False,
        'scope':'new-page fixed-pipeline marginal v14 validation; not full v13 orientation pipeline'})


def score(root):
    import os
    from statistics import mean
    from score_vlm_table_experiment import safe_table
    protected=read(root/'frozen-inputs.json'); summary=read(root/'validation/summary.json')
    protected.update({str(root/p):s for p,s in summary['artifact_sha256'].items()});verify(protected)
    os.environ['MPLCONFIGDIR']=str(ROOT/'backend/data/benchmarks/model_cache/matplotlib')
    sys.path.insert(0,str(DATA/'evaluator'))
    from src.core.preprocess.data_preprocess import normalized_html_table
    from src.metrics.table_metric import TEDS
    gold=read(root/'scoring-only-gold.json');output=root/'scored';output.mkdir();rows=[]
    for row in summary['results']:
        item=dict(row);case=item['id'];truth=normalized_html_table(gold[case]['html'])
        preview=['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
            '<style>body{font:14px system-ui}td,th{border:1px solid gray;padding:5px}table{border-collapse:collapse}</style>',
            '<h1>'+case+'</h1><h2>Gold</h2>',safe_table(gold[case]['html'])]
        for arm in ('v13','v14'):
            p=root/'validation'/case/(arm+'.html');text=p.read_text(encoding='utf-8') if p.is_file() else None
            pred=normalized_html_table(text) if text else None
            item[arm]={'teds':TEDS().evaluate(pred,truth) if pred else 0.,
                'structure_teds':TEDS(structure_only=True).evaluate(pred,truth) if pred else 0.}
            preview+=['<h2>'+arm+'</h2>',safe_table(text) if text else '<p>No output</p>']
        item['delta']=item['v14']['teds']-item['v13']['teds'];rows.append(item)
        (output/(case+'.html')).write_text(''.join(preview),encoding='utf-8')
    aggregate={'cases':len(rows),'eligible':sum(r['v13_gate']['reasons']==['aligned_multiline_row_ambiguity'] for r in rows),
        'reconstructed':sum(r['status']=='reconstructed' for r in rows),
        'changed':sum(r['output_changed'] for r in rows),'missing':sum(r['missing_output'] for r in rows),
        'improved':sum(r['delta']>1e-9 for r in rows),'regressed':sum(r['delta']< -1e-9 for r in rows)}
    for arm in ('v13','v14'):
        for metric in ('teds','structure_teds'):aggregate[arm+'_'+metric]=mean(r[arm][metric] for r in rows)
    verify(protected);write(output/'results.json',{'aggregate':aggregate,'results':rows,
        'scope':summary['scope'],'rule_sha256':sha(ROOT/'scripts/table_record_reconstruction.py'),
        'gold_access_in_inference':False,'production_applied':False,'paid_api_calls':0})
    print(aggregate,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','baseline','paddle','finish','score'])
    p.add_argument('--root',type=Path,required=True);p.add_argument('--count',type=int,default=12)
    a=p.parse_args();root=a.root.resolve()
    if a.action=='prepare':prepare(root,a.count)
    elif a.action in ('baseline','paddle'):run_arm(root,a.action)
    elif a.action=='finish':finish(root)
    else:score(root)
