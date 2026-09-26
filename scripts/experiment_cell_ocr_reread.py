"""One bounded local v17 run. No gold loading in inference; no promotion."""
import argparse
from pathlib import Path
import os
import time

from audit_table_decoder import ROOT,CACHE,read,write,sha,local_path
from experiment_unseen_tables import verify
from table_cell_ocr_reread import plan_reread,apply_reread,POLICY

SOURCE=ROOT/'output/benchmarks/omnidocbench-table-records-validation-v15'
AUDIT=ROOT/'output/benchmarks/omnidocbench-table-geometry-audit-v16'
OUTPUT=ROOT/'output/benchmarks/omnidocbench-table-cell-ocr-v17'
MODEL_NAMES=('PP-OCRv5_server_det','PP-OCRv5_server_rec')


def run(output):
    if output.exists():raise ValueError('Fresh output required; prior evidence cannot be overwritten')
    from PIL import Image,ImageOps
    import numpy as np
    from experiment_table_ocr_binding import plain
    configs={
        'text_detection_model_name':MODEL_NAMES[0],
        'text_detection_model_dir':local_path(CACHE/MODEL_NAMES[0]),
        'text_recognition_model_name':MODEL_NAMES[1],
        'text_recognition_model_dir':local_path(CACHE/MODEL_NAMES[1]),
        'use_doc_orientation_classify':False,'use_doc_unwarping':False,
        'use_textline_orientation':False,'device':'cpu','cpu_threads':4,
        'enable_mkldnn':False,'text_rec_score_thresh':0.0,
        'text_det_limit_side_len':960,'text_det_limit_type':'max'}
    files=[Path(__file__).resolve(),ROOT/'scripts/table_cell_ocr_reread.py',
           ROOT/'scripts/table_grid_binding.py',ROOT/'scripts/table_candidate_safety.py',
           ROOT/'scripts/table_ocr_binding.py',ROOT/'scripts/audit_table_decoder.py',
           ROOT/'backend/Information-Extraction/unified/parsers/html_table_candidate.py',
           ROOT/'backend/Information-Extraction/unified/parsers/table_structure.py',
           SOURCE/'prepared/manifest.json']
    for name in MODEL_NAMES:
        files.extend(CACHE/name/n for n in ('inference.json','inference.pdiparams','inference.yml'))
    cases=read(SOURCE/'prepared/manifest.json')['cases'];plans={}
    for item in cases:
        case=item['id'];base=AUDIT/case
        files.extend([base/'diagnostics.json',SOURCE/'paddle'/case/'binding-capture.json',SOURCE/'prepared'/item['crop']])
        for name in ('normalized-structure.html','effective.html'):
            if (base/name).is_file():files.append(base/name)
        diagnostic=read(base/'diagnostics.json')
        plan=plan_reread(diagnostic['grid']) if diagnostic['grid'] else {'status':'ineligible','cells':[]}
        plans[case]=plan
    if sum(p['status']=='eligible' for p in plans.values())>1:raise ValueError('Bounded run permits one eligible table')
    frozen={str(p):sha(p) for p in files}  # missing cache fails before Paddle initialization
    output.mkdir();write(output/'frozen-inputs.json',frozen)
    write(output/'plan.json',{'policy':POLICY,'plans':plans,'ocr_config':configs,
        'gold_access':False,'production_applied':False,'timeout_seconds':600})
    for key,value in {'PYTHONUTF8':'1','PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK':'True',
            'PADDLE_PDX_CACHE_HOME':str(CACHE.parent),'HF_HUB_OFFLINE':'1',
            'TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4'}.items():os.environ[key]=value
    started=time.monotonic()
    from paddleocr import PaddleOCR
    from importlib.metadata import version
    pipeline=PaddleOCR(**configs);calls=0;rows=[]
    for item in cases:
        case=item['id'];dest=output/case;dest.mkdir();plan=plans[case];base=AUDIT/case
        previous=base/'effective.html'
        if previous.is_file():
            (dest/'previous-effective.html').write_bytes(previous.read_bytes())
            (dest/'effective.html').write_bytes(previous.read_bytes())
        if plan['status']!='eligible':
            rows.append({'id':case,'status':'ineligible_unchanged','gate':{'passed':False,'reasons':['outside_scope']}})
            continue
        diagnostic=read(base/'diagnostics.json');grid=diagnostic['grid']
        results={};pad=POLICY['padding']
        with Image.open(SOURCE/'prepared'/item['crop']) as im:source_image=im.convert('RGB')
        for cell in plan['cells']:
            if time.monotonic()-started>600:raise TimeoutError('Bounded OCR budget exceeded')
            cid=cell['cell_id'];crop=cell['crop_bbox'];image=source_image.crop(tuple(crop))
            image.save(dest/f'cell-{cid}.png')
            padded=ImageOps.expand(image,border=pad,fill='white')
            t=time.monotonic();raw=list(pipeline.predict(np.asarray(padded)[:,:,::-1].copy()))
            calls+=1
            if len(raw)!=1:raise ValueError('Expected one OCR result per cell')
            raw=plain(raw[0].json['res']);write(dest/f'cell-{cid}-raw.json',raw)
            lines=[]
            boxes,texts,scores=raw['rec_boxes'],raw['rec_texts'],raw['rec_scores']
            if not len(boxes)==len(texts)==len(scores):raise ValueError('OCR field length mismatch')
            for box,text,score in zip(boxes,texts,scores):
                mapped=[box[0]+crop[0]-pad,box[1]+crop[1]-pad,box[2]+crop[0]-pad,box[3]+crop[1]-pad]
                lines.append({'text':text,'score':float(score),'bbox':mapped,'padded_bbox':box})
            results[cid]={'lines':lines,'crop_bbox':crop,'padding':pad,'seconds':time.monotonic()-t}
            write(dest/f'cell-{cid}-mapped.json',results[cid])
            print(case,cid,'lines',len(lines),'seconds',round(results[cid]['seconds'],2),flush=True)
        capture=read(SOURCE/'paddle'/case/'binding-capture.json')
        structure=(base/'normalized-structure.html').read_text(encoding='utf-8')
        result=apply_reread(structure,capture,grid,plan,results)
        write(dest/'replacement.json',result)
        if result['trace'] and result['trace']['html']:
            (dest/'candidate.html').write_text(result['trace']['html'],encoding='utf-8')
        if result['gate']['passed']:(dest/'effective.html').write_bytes((dest/'candidate.html').read_bytes())
        rows.append({'id':case,'status':'candidate_admitted_review_required' if result['gate']['passed'] else 'candidate_rejected_fallback_retained',
                     'gate':result['gate'],'selected_cells':len(plan['cells']),'reread_calls':len(results)})
    verify(frozen)
    artifacts={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file()}
    write(output/'summary.json',{'source':str(SOURCE),'audit':str(AUDIT),'results':rows,
        'artifact_sha256':artifacts,'model_names':MODEL_NAMES,'paddleocr_version':version('paddleocr'),
        'seconds':time.monotonic()-started,'local_ocr_calls':calls,'paid_api_calls':0,
        'gold_access_in_inference':False,'production_applied':False,'protected_inputs_unchanged':True})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUTPUT)
    run(p.parse_args().output.resolve())
