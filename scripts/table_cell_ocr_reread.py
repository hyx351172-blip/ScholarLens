"""Bounded, gold-blind cell-region OCR replacement; offline experiment only."""
from collections import Counter
from copy import deepcopy
import math
import re

from table_ocr_binding import coverage
from table_grid_binding import bind_grid
from table_candidate_safety import guard_candidate

POLICY={'max_cells':12,'padding':16,'minimum_confidence':.5}
NUMBER=re.compile(r'\d+(?:\.\d+)?')


def plan_reread(grid):
    no={'status':'ineligible','cells':[],'ambiguous_ids':[]}
    if (grid['gate']['passed'] or grid['gate']['reasons']!=['unassigned_or_ambiguous_ocr'] or
        not all(a['stable'] and a['count_matches'] for a in grid['axes'].values())):return no
    ambiguous=[a for a in grid['assignments'] if a['cell_id'] is None]
    if not ambiguous:return no
    selected=set()
    for a in ambiguous:
        touched=[c for c in grid['cells'] if coverage(c['bbox'],a['bbox'])>0]
        if (len(touched)<2 or len({c['row'] for c in touched})!=1 or
            any(c['row_span']!=1 or c['col_span']!=1 for c in touched) or
            sum(coverage(c['bbox'],a['bbox']) for c in touched)<.999):return no
        selected.update(c['cell_id'] for c in touched)
    if len(selected)>POLICY['max_cells']:return no
    cells=[]
    for c in grid['cells']:
        if c['cell_id'] not in selected:continue
        l,t,r,b=c['bbox'];crop=[math.ceil(l),math.ceil(t),math.floor(r),math.floor(b)]
        if crop[2]-crop[0]<16 or crop[3]-crop[1]<16:return no
        cells.append({'cell_id':c['cell_id'],'row':c['row'],'col':c['col'],'crop_bbox':crop})
    return {'status':'eligible','cells':cells,'ambiguous_ids':[a['ocr_id'] for a in ambiguous],
            'policy':deepcopy(POLICY)}


def apply_reread(structure,capture,grid,plan,results):
    # Validate all responses before replacing anything. Caller preserves fallback.
    rejected={'gate':{'passed':False,'reasons':['invalid_or_missing_reread']},'trace':None}
    if plan!=plan_reread(grid) or plan['status']!='eligible':return rejected
    selected={c['cell_id'] for c in plan['cells']}
    if set(results)!=selected:return rejected
    try:
        for c in plan['cells']:
            lines=results[c['cell_id']]['lines'];seen=set()
            if not 1<=len(lines)<=500:raise ValueError('Empty/excessive cell')
            for line in lines:
                text,score,box=line['text'],line['score'],line['bbox']
                if not isinstance(text,str) or not text.strip() or len(text)>10000:raise ValueError('Invalid text')
                if not isinstance(score,(int,float)) or not math.isfinite(score) or not .5<=score<=1:raise ValueError('Confidence')
                if len(box)!=4 or not all(math.isfinite(v) for v in box):raise ValueError('Coordinates')
                l,t,r,b=box;cl,ct,cr,cb=c['crop_bbox']
                if not cl<=l<r<=cr or not ct<=t<b<=cb:raise ValueError('Outside crop')
                identity=tuple(box)
                if identity in seen:raise ValueError('Duplicate OCR box')
                seen.add(identity)
    except (ValueError,TypeError,KeyError,OverflowError):return rejected
    kept=[];removed=[];provenance=[];boxes=[];texts=[]
    for a in grid['assignments']:
        if a['cell_id'] in selected or a['ocr_id'] in plan['ambiguous_ids']:
            removed.append(a['ocr_id']);continue
        kept.append(a['ocr_id']);boxes.append(a['bbox'][:]);texts.append(a['text'])
        provenance.append({'new_ocr_id':len(texts)-1,'source':'original','old_ocr_id':a['ocr_id']})
    losses=[]
    for c in plan['cells']:
        cid=c['cell_id'];lines=results[cid]['lines']
        old_numbers=Counter(NUMBER.findall(grid['cells'][cid]['text']))
        new_numbers=Counter(NUMBER.findall(' '.join(a['text'] for a in lines)))
        missing=old_numbers-new_numbers
        if missing:losses.append({'cell_id':cid,'missing':list(missing.elements())})
        for index,line in enumerate(lines):
            boxes.append(line['bbox'][:]);texts.append(line['text'])
            provenance.append({'new_ocr_id':len(texts)-1,'source':'cell_reread','cell_id':cid,'line_id':index})
    replaced=deepcopy(capture)
    replaced['match']['ocr_boxes']=boxes;replaced['render']['texts']=texts
    trace=guard_candidate(bind_grid(structure,replaced,grid['crop_size']))
    reasons=trace['gate']['reasons'][:]
    if losses:reasons.append('assigned_numeric_evidence_lost')
    return {'gate':{'passed':not reasons,'reasons':reasons},'trace':trace,
            'capture':replaced,'provenance':provenance,'removed_old_ids':removed,
            'retained_old_ids':kept,'numeric_losses':losses,
            'note':'New OCR evidence, not invariant original text. Candidate remains experimental.'}
