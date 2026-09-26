"""V13 development replay + bounded local orientation experiment. No gold access."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from audit_table_decoder import ROOT, CACHE, read, write, sha, local_path
from experiment_unseen_tables import PADDLE_PYTHON, verify, paddle_worker, docling_worker
from finalize_unseen_table_outputs import export_baseline, package_versions
from table_candidate_safety import guard_candidate
from table_orientation import ANGLES, POLICY, choose_orientation, ocr_quality, original_bbox

SOURCE = ROOT/'output/benchmarks/omnidocbench-table-unseen-v12'
TARGETS = ('case-20','case-13','case-09')


def optional(path):
    return path.read_text(encoding='utf-8') if path.is_file() else None


def orient_worker(crop, dest):
    import numpy as np
    from PIL import Image
    from paddleocr import PaddleOCR
    opts=dict(device='cpu',cpu_threads=4,enable_mkldnn=False,
              use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False)
    for prefix,name in [('text_detection','PP-OCRv5_server_det'),('text_recognition','PP-OCRv5_server_rec')]:
        opts[prefix+'_model_name']=name; opts[prefix+'_model_dir']=local_path(CACHE/name)
    model=PaddleOCR(**opts)
    model.export_paddlex_config_to_yaml(str(dest/'pipeline-config.yaml'))
    with Image.open(crop) as im:
        im=im.convert('RGB'); original_size=list(im.size)
        if im.width*im.height>40_000_000: raise ValueError('Image exceeds pixel budget')
        im.thumbnail((POLICY['max_probe_side'],)*2,Image.Resampling.LANCZOS)
        small=np.asarray(im)[:,:,::-1].copy()
    quality={}; times={}
    for angle in ANGLES:
        started=time.monotonic()
        results=list(model.predict(np.rot90(small,angle//90).copy()))
        if len(results)!=1: raise ValueError('Expected one OCR result')
        raw=results[0].json
        if isinstance(raw,str): raw=json.loads(raw)
        write(dest/f'ocr-{angle}.json',raw)
        quality[angle]=ocr_quality(raw['res']); times[angle]=time.monotonic()-started
        print('probe',angle,quality[angle],flush=True)
    decision=choose_orientation(quality)
    decision.update(original_size=original_size,probe_size=[small.shape[1],small.shape[0]],
                    per_angle_seconds=times,coordinate_system='continuous pixel edges; angles counter-clockwise')
    if decision['angle_ccw']:
        with Image.open(crop) as im:
            arr=np.rot90(np.asarray(im.convert('RGB')),decision['angle_ccw']//90).copy()
            Image.fromarray(arr).save(dest/'oriented.png')
        decision['oriented_sha256']=sha(dest/'oriented.png')
    write(dest/'decision.json',decision)
    return {'status':'completed','decision':decision}


def baseline_worker(crop,dest):
    # Frozen v12 conversion writes raw JSON before its obsolete version lookup.
    # Recover this exact metadata exception only, never a conversion failure.
    from importlib.metadata import PackageNotFoundError
    recovered=False
    try: docling_worker(crop,dest)
    except PackageNotFoundError as exc:
        if str(exc)!='No package metadata was found for docling' or not (dest/'docling-document.json').is_file(): raise
        recovered=True
    candidate,info=export_baseline(read(dest/'docling-document.json'))
    write(dest/'baseline-export.json',info)
    if candidate: (dest/'candidate.html').write_text(candidate,encoding='utf-8')
    return {'status':info['status'],'metadata_recovery':recovered,'versions':package_versions()}


def worker(kind,crop,dest):
    started=time.monotonic()
    try: result={'orient':orient_worker,'baseline':baseline_worker,'paddle':paddle_worker}[kind](crop,dest)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result={'status':'failed','error_type':type(exc).__name__,'error':str(exc)}
    result.update(seconds=time.monotonic()-started,crop_sha256=sha(crop),gold_access=False,paid_api_calls=0)
    write(dest/'result.json',result)


def launch(kind,crop,dest,env):
    dest.mkdir(parents=True)
    python=sys.executable if kind=='baseline' else str(PADDLE_PYTHON)
    timeout=300 if kind=='orient' else 240
    started=time.monotonic()
    with (dest/'worker.log').open('w',encoding='utf-8') as log:
        try:
            p=subprocess.run([python,str(Path(__file__).resolve()),'worker','--kind',kind,
                              '--crop',str(crop),'--output',str(dest)],cwd=ROOT,env=env,
                              stdout=log,stderr=subprocess.STDOUT,timeout=timeout,check=False)
            result=read(dest/'result.json') if p.returncode==0 and (dest/'result.json').is_file() else {
                'status':'process_failed','exit_code':p.returncode}
        except subprocess.TimeoutExpired: result={'status':'timeout','timeout_seconds':timeout}
    result.update(wall_seconds=time.monotonic()-started)
    write(dest/'result.json',result)
    print(dest.parent.name,kind,result['status'],round(result['wall_seconds'],2),flush=True)
    return result


def replay_trace(src):
    trace=src/'grid-trace.json'
    if trace.is_file(): return guard_candidate(read(trace))
    return {'gate':read(src/'result.json')['gate'],'html':None,'cells':[],
            'row_safety':{'status':'no_candidate_retained'}}


def map_geometry(trace,raw,crop_size,angle,page_offset):
    cells=[]
    for cell in trace.get('cells',[]):
        cells.append({'cell_id':cell['cell_id'],'rotated_bbox':cell['bbox'],
            'original_crop_bbox':original_bbox(cell['bbox'],crop_size,angle),
            'original_page_bbox':original_bbox(cell['bbox'],crop_size,angle,page_offset),
            'ocr_ids':cell['ocr_ids']})
    # Keep raw OCR geometry as well, even if the table topology is rejected.
    ocr=raw['res']['overall_ocr_res']; boxes=ocr['rec_boxes']; texts=ocr['rec_texts']
    if len(boxes)!=len(texts): raise ValueError('OCR geometry mismatch')
    lines=[{'raw_ocr_id':i,'text':t,'rotated_bbox':b,
            'original_crop_bbox':original_bbox(b,crop_size,angle),
            'original_page_bbox':original_bbox(b,crop_size,angle,page_offset)} for i,(b,t) in enumerate(zip(boxes,texts))]
    return {'angle_ccw':angle,'original_size':crop_size,'page_offset':page_offset,
            'cell_ocr_id_namespace':'binding-capture; separate from raw OCR IDs','cells':cells,'raw_ocr':lines}


def run(out):
    import cv2
    import numpy as np
    if out.exists(): raise ValueError('Fresh output required')
    protected=read(SOURCE/'frozen-inputs.json')
    # Hash gold files as opaque bytes only, never read labels during inference.
    for p in SOURCE.rglob('*'):
        if p.is_file(): protected[str(p)]=sha(p)
    old=ROOT/'output/benchmarks/omnidocbench-table-header-v11'
    for p in old.rglob('*'):
        if p.is_file(): protected[str(p)]=sha(p)
    for n in ('table_candidate_safety.py','table_orientation.py','experiment_table_safety.py','finalize_unseen_table_outputs.py'):
        p=ROOT/'scripts'/n;protected[str(p)]=sha(p)
    verify(protected)
    out.mkdir(parents=True); write(out/'input-integrity.json',protected)
    manifest=read(SOURCE/'prepared/manifest.json')
    env=dict(os.environ,PYTHONUTF8='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        HF_HOME=str(ROOT/'backend/data/benchmarks/model_cache/huggingface'),
        EASYOCR_MODULE_PATH=str(ROOT/'backend/data/benchmarks/model_cache/easyocr'),
        MPLCONFIGDIR=str(ROOT/'backend/data/benchmarks/model_cache/matplotlib'),
        PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',PADDLE_PDX_CACHE_HOME='backend/data/benchmarks/model_cache/tablemagic',
        OMP_NUM_THREADS='4',MKL_NUM_THREADS='4')
    controls=[]
    for row in read(old/'summary.json')['results']:
        src=old/row['id']; trace=replay_trace(src)
        if trace['gate']!=row['gate']: raise ValueError('Older control gate changed: '+row['id'])
        if (src/'grid-trace.json').is_file() and trace.get('html')!=read(src/'grid-trace.json').get('html'):
            raise ValueError('Older control content changed')
        controls.append({'id':row['id'],'gate_unchanged':True,'html_unchanged':True})
    write(out/'older-controls.json',controls)
    probe_results={}
    def probe(case):
        return case,launch('orient',SOURCE/'prepared'/f'{case}.png',out/'orientation'/case,env)
    with ThreadPoolExecutor(max_workers=2) as pool:
        for case,result in pool.map(probe,TARGETS): probe_results[case]=result
    rows=[]
    for item in manifest['cases']:
        case=item['id']; src=SOURCE/'final'/case; dest=out/'final'/case;dest.mkdir(parents=True)
        base=optional(src/'baseline.html'); trace=replay_trace(src); angle=0
        baseline_source='v12_baseline'; fresh={}
        probe=probe_results.get(case)
        if probe and probe['status']=='completed': angle=probe['decision']['angle_ccw']
        if angle:
            crop=out/'orientation'/case/'oriented.png'; freshdir=out/'fresh'/case
            # Separate independent extraction arms on the same selected crop.
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs={k:pool.submit(launch,k,crop,freshdir/k,env) for k in ('baseline','paddle')}
                fresh={k:j.result() for k,j in jobs.items()}
            if fresh['baseline']['status']=='completed':
                base=optional(freshdir/'baseline/candidate.html'); baseline_source='oriented_docling'
            # A selected rotation cannot use an unrotated candidate as fallback.
            trace={'html':None,'cells':[],'gate':{'passed':False,'reasons':['oriented_candidate_unavailable']}}
            if fresh['paddle']['status']=='completed':
                from table_header_reconstruction import repair_header
                ps=freshdir/'paddle'
                try:
                    if any(fresh['paddle']['capture_counts'].get(k)!=1 for k in ('match','render','geometry_reprocessing')):
                        raise ValueError('Ambiguous capture')
                    gray=cv2.imdecode(np.frombuffer(crop.read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
                    trace=guard_candidate(repair_header(optional(ps/'structure.html'),read(ps/'binding-capture.json'),gray))
                except (ValueError,KeyError,IndexError,TypeError) as exc:
                    trace={'html':None,'cells':[],'gate':{'passed':False,'reasons':[str(exc)]}}
                mapping=map_geometry(trace,read(ps/'paddle-raw.json'),probe['decision']['original_size'],angle,item['crop_bbox'][:2])
                write(dest/'coordinate-map.json',mapping)
        effective=trace.get('html') if trace['gate']['passed'] else base
        for name,text in [('baseline',base),('candidate',trace.get('html')),('effective',effective)]:
            if text: (dest/f'{name}.html').write_text(text,encoding='utf-8')
        write(dest/'grid-trace.json',trace)
        row={'id':case,'page':item['page'],'angle_ccw':angle,'baseline_source':baseline_source,
             'gate':trace['gate'],'fresh_runs':fresh,'orientation':probe,
             'effective_source':'v13_candidate' if trace['gate']['passed'] else baseline_source}
        write(dest/'result.json',row);rows.append(row)
        print(case,angle,row['effective_source'],trace['gate']['reasons'],flush=True)
    verify(protected)
    artifacts={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}
    write(out/'summary.json',{'experiment':'table-safety-v13','source':str(SOURCE),'cohort':'development-regression',
        'gold_access_in_inference':False,'paid_api_calls':0,'production_applied':False,
        'targets':list(TARGETS),'older_controls':controls,'results':rows,'artifact_sha256':artifacts,
        'protected_inputs_unchanged':True})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['run','worker'])
    p.add_argument('--output',required=True,type=Path);p.add_argument('--kind',choices=['orient','paddle','baseline'])
    p.add_argument('--crop',type=Path);a=p.parse_args()
    if a.action=='run': run(a.output.resolve())
    else: worker(a.kind,a.crop.resolve(),a.output.resolve())
