"""V13b resource-bounded follow-up; preserves the first attempt including timeout."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time
from audit_table_decoder import ROOT,read,write,sha
from experiment_unseen_tables import verify,PADDLE_PYTHON
from experiment_table_safety import SOURCE,TARGETS,launch,optional,map_geometry
from table_candidate_safety import guard_candidate

PRIOR=ROOT/'output/benchmarks/omnidocbench-table-safety-v13'


def worker(crop,dest):
    from bounded_table_orientation import probe
    start=time.monotonic()
    try:result=probe(crop,dest)
    except Exception as exc:
        import traceback
        traceback.print_exc();result={'status':'failed','error_type':type(exc).__name__,'error':str(exc)}
    result.update(seconds=time.monotonic()-start,crop_sha256=sha(crop),gold_access=False,paid_api_calls=0)
    write(dest/'result.json',result)


def run(out):
    import numpy as np
    import cv2
    if out.exists():raise ValueError('Fresh output required')
    previous=read(PRIOR/'summary.json');protected=read(PRIOR/'input-integrity.json')
    protected.update({str(PRIOR/p):v for p,v in previous['artifact_sha256'].items()})
    for p in [PRIOR/'summary.json',Path(__file__).resolve(),ROOT/'scripts/bounded_table_orientation.py']:
        protected[str(p)]=sha(p)
    verify(protected);out.mkdir(parents=True);write(out/'input-integrity.json',protected)
    env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        HF_HOME=str(ROOT/'backend/data/benchmarks/model_cache/huggingface'),
        EASYOCR_MODULE_PATH=str(ROOT/'backend/data/benchmarks/model_cache/easyocr'),
        MPLCONFIGDIR=str(ROOT/'backend/data/benchmarks/model_cache/matplotlib'),
        PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',PADDLE_PDX_CACHE_HOME='backend/data/benchmarks/model_cache/tablemagic',
        OMP_NUM_THREADS='4',MKL_NUM_THREADS='4')
    def orient(case):
        dest=out/'orientation'/case;dest.mkdir(parents=True);start=time.monotonic()
        with (dest/'worker.log').open('w',encoding='utf-8') as log:
            try:
                proc=subprocess.run([str(PADDLE_PYTHON),str(Path(__file__).resolve()),'worker','--crop',
                    str(SOURCE/'prepared'/f'{case}.png'),'--output',str(dest)],cwd=ROOT,env=env,
                    stdout=log,stderr=subprocess.STDOUT,timeout=240,check=False)
                result=read(dest/'result.json') if proc.returncode==0 and (dest/'result.json').is_file() else {'status':'process_failed'}
            except subprocess.TimeoutExpired:result={'status':'timeout','timeout_seconds':240}
        result['wall_seconds']=time.monotonic()-start;write(dest/'result.json',result)
        print(case,'bounded orientation',result['status'],result.get('decision',{}).get('angle_ccw'),flush=True)
        return case,result
    with ThreadPoolExecutor(max_workers=2) as pool:probes=dict(pool.map(orient,TARGETS))
    items={c['id']:c for c in read(SOURCE/'prepared/manifest.json')['cases']};rows=[]
    for prior in previous['results']:
        case=prior['id'];src=PRIOR/'final'/case;dest=out/'final'/case;dest.mkdir(parents=True)
        trace=read(src/'grid-trace.json');base=optional(src/'baseline.html');angle=0;fresh={}
        baseline_source=prior['baseline_source'];probe=probes.get(case)
        if probe and probe['status']=='completed':angle=probe['decision']['angle_ccw']
        if angle:
            crop=out/'orientation'/case/'oriented.png';f=out/'fresh'/case
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs={k:pool.submit(launch,k,crop,f/k,env) for k in ('baseline','paddle')}
                fresh={k:j.result() for k,j in jobs.items()}
            if fresh['baseline']['status']=='completed':base=optional(f/'baseline/candidate.html');baseline_source='oriented_docling'
            trace={'html':None,'cells':[],'gate':{'passed':False,'reasons':['oriented_candidate_unavailable']}}
            if fresh['paddle']['status']=='completed':
                from table_header_reconstruction import repair_header
                ps=f/'paddle'
                try:
                    if any(fresh['paddle']['capture_counts'].get(k)!=1 for k in ('match','render','geometry_reprocessing')):
                        raise ValueError('Ambiguous capture')
                    gray=cv2.imdecode(np.frombuffer(crop.read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
                    trace=guard_candidate(repair_header(optional(ps/'structure.html'),read(ps/'binding-capture.json'),gray))
                except (ValueError,KeyError,IndexError,TypeError) as exc:
                    trace={'html':None,'cells':[],'gate':{'passed':False,'reasons':[str(exc)]}}
                write(dest/'coordinate-map.json',map_geometry(trace,read(ps/'paddle-raw.json'),
                    probe['decision']['original_size'],angle,items[case]['crop_bbox'][:2]))
        effective=trace.get('html') if trace['gate']['passed'] else base
        for name,text in [('baseline',base),('candidate',trace.get('html')),('effective',effective)]:
            if text:(dest/f'{name}.html').write_text(text,encoding='utf-8')
        write(dest/'grid-trace.json',trace)
        row={'id':case,'page':prior['page'],'angle_ccw':angle,'baseline_source':baseline_source,
             'gate':trace['gate'],'fresh_runs':fresh,'orientation':probe,
             'effective_source':'v13_candidate' if trace['gate']['passed'] else baseline_source}
        write(dest/'result.json',row);rows.append(row)
        print(case,angle,row['effective_source'],trace['gate']['reasons'],flush=True)
    verify(protected)
    artifacts={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}
    write(out/'summary.json',{'experiment':'table-safety-v13-bounded','source':str(SOURCE),'prior_attempt':str(PRIOR),
        'cohort':'development-regression','gold_access_in_inference':False,'production_applied':False,'paid_api_calls':0,
        'targets':list(TARGETS),'results':rows,'older_controls':previous['older_controls'],
        'protected_inputs_unchanged':True,'artifact_sha256':artifacts})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['run','worker'])
    p.add_argument('--output',required=True,type=Path);p.add_argument('--crop',type=Path);a=p.parse_args()
    if a.action=='run':run(a.output.resolve())
    else:worker(a.crop.resolve(),a.output.resolve())
