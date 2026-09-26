"""Bound orientation cost by recognizing spatially sampled horizontal prefixes."""
import json
import math
import time
from audit_table_decoder import CACHE, local_path, write, sha
from table_orientation import ANGLES, POLICY, ocr_quality, choose_orientation

SAMPLE_POLICY={'max_lines_per_angle':24,'max_prefix_aspect':12,'min_height':4,
               'min_horizontal_aspect':1.25,'max_detections':10000}


def sample_boxes(polygons,size):
    if len(polygons)>SAMPLE_POLICY['max_detections']:raise ValueError('Excessive detections')
    w,h=size;eligible=[]
    for i,p in enumerate(polygons):
        if len(p)!=4 or any(len(v)!=2 or not all(math.isfinite(x) for x in v) for v in p):
            raise ValueError('Invalid polygon')
        x0=max(0,math.floor(min(x for x,y in p)));x1=min(w,math.ceil(max(x for x,y in p)))
        y0=max(0,math.floor(min(y for x,y in p)));y1=min(h,math.ceil(max(y for x,y in p)))
        if y1-y0<SAMPLE_POLICY['min_height'] or x1-x0<(y1-y0)*SAMPLE_POLICY['min_horizontal_aspect']:continue
        # Only a prefix for direction evidence, NOT the final extracted content.
        x1=min(x1,x0+(y1-y0)*SAMPLE_POLICY['max_prefix_aspect'])
        eligible.append({'detection_id':i,'bbox':[x0,y0,x1,y1]})
    eligible.sort(key=lambda b:(b['bbox'][1],b['bbox'][0],b['detection_id']))
    count=min(len(eligible),SAMPLE_POLICY['max_lines_per_angle'])
    ids=[round(j*(len(eligible)-1)/(count-1)) for j in range(count)] if count>1 else list(range(count))
    return [eligible[i] for i in ids]


def probe(crop,dest):
    import numpy as np
    from PIL import Image
    from paddleocr import TextDetection,TextRecognition
    opts=dict(device='cpu',cpu_threads=4,enable_mkldnn=False)
    detector=TextDetection(model_name='PP-OCRv5_server_det',model_dir=local_path(CACHE/'PP-OCRv5_server_det'),
                           limit_side_len=1280,limit_type='max',**opts)
    recognizer=TextRecognition(model_name='PP-OCRv5_server_rec',model_dir=local_path(CACHE/'PP-OCRv5_server_rec'),**opts)
    with Image.open(crop) as im:
        im=im.convert('RGB');size=list(im.size)
        if im.width*im.height>40_000_000:raise ValueError('Excessive crop')
        im.thumbnail((POLICY['max_probe_side'],)*2,Image.Resampling.LANCZOS)
        small=np.asarray(im)[:,:,::-1].copy()
    quality={};durations={}
    for angle in ANGLES:
        start=time.monotonic();arr=np.rot90(small,angle//90).copy()
        det=detector.predict(arr)
        if len(det)!=1:raise ValueError('Expected one detector result')
        raw=det[0].json
        if isinstance(raw,str):raw=json.loads(raw)
        write(dest/f'detection-{angle}.json',raw)
        selected=sample_boxes(raw['res']['dt_polys'],[arr.shape[1],arr.shape[0]])
        data={'rec_texts':[],'rec_scores':[],'rec_boxes':[]}
        for item in selected:
            x0,y0,x1,y1=item['bbox']
            rec=recognizer.predict(arr[y0:y1,x0:x1].copy())
            if len(rec)!=1:raise ValueError('Expected one recognizer result')
            r=rec[0].json
            if isinstance(r,str):r=json.loads(r)
            data['rec_texts'].append(r['res']['rec_text']);data['rec_scores'].append(r['res']['rec_score'])
            data['rec_boxes'].append(item['bbox'])
        quality[angle]=ocr_quality(data);durations[angle]=time.monotonic()-start
        write(dest/f'ocr-{angle}.json',{'res':data,'selected':selected,'prefix_only':True})
        print('bounded probe',angle,quality[angle],round(durations[angle],2),flush=True)
    decision=choose_orientation(quality)
    decision.update(original_size=size,probe_size=[small.shape[1],small.shape[0]],sample_policy=SAMPLE_POLICY,
                    per_angle_seconds=durations,coordinate_system='continuous pixel edges; counter-clockwise')
    if decision['angle_ccw']:
        with Image.open(crop) as im:
            Image.fromarray(np.rot90(np.asarray(im.convert('RGB')),decision['angle_ccw']//90).copy()).save(dest/'oriented.png')
        decision['oriented_sha256']=sha(dest/'oriented.png')
    write(dest/'decision.json',decision)
    return {'status':'completed','decision':decision}
