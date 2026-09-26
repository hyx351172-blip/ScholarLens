"""Explicit docling-slim metadata adapter; frozen parser algorithms untouched."""
import argparse
import importlib.metadata as metadata
import os
from pathlib import Path
import subprocess
import sys
import time
import validate_table_records as protocol

from audit_table_decoder import ROOT, read, write, sha, parse_html_table
from experiment_unseen_tables import verify, worker


def distribution_version(name, lookup):
    try:return lookup(name)
    except metadata.PackageNotFoundError:
        if name!='docling':raise
        return lookup('docling-slim')


def baseline(root):
    protected=read(root/'frozen-inputs.json');verify(protected)
    dest=root/'baseline-fixed';dest.mkdir()
    write(dest/'adapter-provenance.json',{'adapter_sha256':sha(Path(__file__).resolve()),
        'docling_distribution':'docling-slim','version':metadata.version('docling-slim'),
        'change':'package version lookup only; original failed run preserved'})
    env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        HF_HOME=str(ROOT/'backend/data/benchmarks/model_cache/huggingface'),
        EASYOCR_MODULE_PATH=str(ROOT/'backend/data/benchmarks/model_cache/easyocr'),
        MPLCONFIGDIR=str(ROOT/'backend/data/benchmarks/model_cache/matplotlib'),OMP_NUM_THREADS='4',MKL_NUM_THREADS='4')
    rows=[]
    for item in read(root/'prepared/manifest.json')['cases']:
        out=dest/item['id'];out.mkdir();started=time.monotonic()
        with (out/'worker.log').open('w',encoding='utf-8') as log:
            try:
                p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'worker','--root',str(out),
                    '--crop',str(root/'prepared'/item['crop'])],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
                result=read(out/'result.json') if p.returncode==0 and (out/'result.json').is_file() else {'status':'process_failed','exit_code':p.returncode}
            except subprocess.TimeoutExpired:result={'status':'timeout','timeout_seconds':240}
        result.update(id=item['id'],wall_seconds=time.monotonic()-started);write(out/'result.json',result);rows.append(result)
        write(dest/'summary.json',{'complete':False,'results':rows});print('baseline-fixed',item['id'],result['status'],flush=True)
    verify(protected)
    write(dest/'summary.json',{'complete':True,'results':rows,
        'artifact_sha256':{p.relative_to(dest).as_posix():sha(p) for p in dest.rglob('*') if p.is_file() and p.name!='summary.json'}})


def finish(root):
    import cv2
    import numpy as np
    from table_header_reconstruction import repair_header
    protected=read(root/'frozen-inputs.json');verify(protected)
    manifest=read(root/'prepared/manifest.json')
    for arm in ('baseline-fixed','paddle'):
        summary=read(root/arm/'summary.json')
        if not summary['complete'] or len(summary['results'])!=len(manifest['cases']):raise ValueError('Incomplete inference')
        verify({str(root/arm/p):s for p,s in summary['artifact_sha256'].items()})
    output=root/'validation';output.mkdir();rows=[]
    for item in manifest['cases']:
        case=item['id'];src=root/'paddle'/case;dest=output/case;dest.mkdir()
        try:
            result=read(src/'result.json')
            if result['status']!='completed':raise ValueError('Paddle worker: '+result['status'])
            if any(result['capture_counts'].get(k)!=1 for k in ('match','render','geometry_reprocessing')):raise ValueError('Ambiguous capture')
            raw=(src/'structure.html').read_text(encoding='utf-8');parse_html_table(raw)
            gray=cv2.imdecode(np.frombuffer((root/'prepared'/item['crop']).read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
            trace=repair_header(raw,read(src/'binding-capture.json'),gray)
        except (ValueError,KeyError,FileNotFoundError,IndexError) as exc:trace={'gate':{'passed':False,'reasons':[str(exc)]}}
        base=root/'baseline-fixed'/case/'candidate.html'
        baseline=base.read_text(encoding='utf-8') if base.is_file() and read(base.parent/'result.json')['status']=='completed' else None
        old,new,a,b=protocol.compare(trace,baseline)
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
        'compat_adapter_sha256':sha(Path(__file__).resolve()),
        'scope':'new-page fixed-pipeline marginal v14 validation; not full v13 orientation pipeline'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['baseline','worker','finish']);p.add_argument('--root',required=True,type=Path);p.add_argument('--crop',type=Path)
    a=p.parse_args()
    if a.action=='baseline':baseline(a.root.resolve())
    elif a.action=='finish':finish(a.root.resolve())
    else:
        original=metadata.version
        metadata.version=lambda name:distribution_version(name,original)
        try:worker('baseline',a.crop.resolve(),a.root.resolve())
        finally:metadata.version=original
