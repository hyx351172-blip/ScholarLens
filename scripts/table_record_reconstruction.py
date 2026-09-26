"""Restricted, no-gold reconstruction of independently anchored table records.

OCR boxes/text are immutable evidence. Logical row geometry uses central vertical
cores to tolerate detector padding; original extents and overlap remain explicit.
"""
from copy import deepcopy
import re
from statistics import median
import unicodedata

from audit_table_decoder import parse_html_table
from table_structure import render_table_html
from table_candidate_safety import guard_candidate, line_bands
from table_ocr_binding import key, rectangle, coverage

POLICY={'min_records':3,'max_records':32,'min_support_columns':2,'max_target_rows':8,
        'start_alignment_height':.4,'continuation_indent_height':.35,
        'core_height_fraction':.4,'min_core_gap_height':.1,
        'max_cells':5000,'max_ocr':10000,'max_ocr_per_target_cell':128}
VETO='aligned_multiline_row_ambiguity'
WORD=r'[^\W\d_]+'
NUMERIC=re.compile(r'^[+-]?\d+(?:[.,]\d+)?(?:\s*('+WORD+r'(?:/'+WORD+r')?|%))?$')
PREFIX=re.compile(r'^('+WORD+r'(?:[ -]+'+WORD+r'){0,2})\s+[+-]?\d+(?:[.,]\d+)?(?:\s|$)')


def typed_start(text):
    t=' '.join(unicodedata.normalize('NFKC',text).split())
    if not t or len(t)>100:return None
    numeric=NUMERIC.fullmatch(t)
    if numeric:return ('number_unit',(numeric.group(1) or '').casefold())
    prefix=PREFIX.match(t)
    return ('prefix_number',prefix.group(1).casefold()) if prefix else None


def bands_for(cell):
    by={a['ocr_id']:a for a in cell['ocr']};bands=line_bands(cell)
    for band in bands:
        items=sorted((by[i] for i in band['ocr_ids']),key=lambda a:(a['bbox'][0],a['ocr_id']))
        band['ocr_ids']=[a['ocr_id'] for a in items]
        band['text']=' '.join(a['text'] for a in items)
        band['left']=min(a['bbox'][0] for a in items)
    return bands


def validate(trace):
    s=parse_html_table(trace['html'])[0];cells=trace['cells'];ids=set();cell_ids=set()
    if not cells or len(cells)>POLICY['max_cells'] or len(cells)!=len(s['table_cells']):
        raise ValueError('invalid_source_cell_count')
    mapped={};ocr={}
    for c in cells:
        for field in ('row','col','row_span','col_span','cell_id'):
            if type(c[field]) is not int or c[field]<(1 if field.endswith('span') else 0):
                raise ValueError('invalid_source_cell_coordinates')
        if c['cell_id'] in cell_ids:raise ValueError('duplicate_source_cell_id')
        cell_ids.add(c['cell_id']);rectangle(c['bbox'])
        pos=(c['row'],c['col'],c['row_span'],c['col_span'])
        if pos in mapped:raise ValueError('duplicate_source_cell_position')
        mapped[pos]=c
        if len(c['ocr'])!=len(c['ocr_ids']):raise ValueError('inconsistent_source_ocr_ids')
        for a,expected in zip(c['ocr'],c['ocr_ids']):
            i=a['ocr_id'];rectangle(a['bbox'])
            if type(i) is not int or i<0 or i in ids or expected!=i:raise ValueError('invalid_source_ocr_id')
            if a['cell_id']!=c['cell_id']:raise ValueError('source_ocr_cell_mismatch')
            if not isinstance(a['text'],str) or len(a['text'])>10000:raise ValueError('invalid_source_ocr_text')
            if coverage(c['bbox'],a['bbox'])<.7:raise ValueError('source_ocr_not_contained')
            ids.add(i);ocr[i]=a
        if c['text']!=' '.join(a['text'] for a in c['ocr']):raise ValueError('source_text_provenance_mismatch')
    if len(ids)>POLICY['max_ocr']:raise ValueError('excessive_source_ocr')
    for native in s['table_cells']:
        c=mapped.get(key(native))
        if c is None or native['text']!=c['text']:raise ValueError('source_html_cell_mismatch')
    if trace.get('unassigned_ocr_ids'):raise ValueError('source_has_unassigned_ocr')
    assignments=trace['assignments']
    if len(assignments)!=len(ids) or len({a['ocr_id'] for a in assignments})!=len(ids):
        raise ValueError('source_assignment_count_mismatch')
    for a in assignments:
        prior=ocr.get(a['ocr_id'])
        if prior is None or (a['text'],a['bbox'],a['cell_id'])!=(prior['text'],prior['bbox'],prior['cell_id']):
            raise ValueError('source_assignment_mismatch')
    return s,mapped


def assign_records(cell,anchors):
    bands=bands_for(cell);starts={};continuations=[]
    for band in bands:
        matches=[i for i,a in enumerate(anchors) if abs(band['y']-a['y'])<=
                 min(band['height'],a['height'])*POLICY['start_alignment_height']]
        if len(matches)>1:raise ValueError('ambiguous_record_start')
        if matches:
            i=matches[0]
            if i in starts:raise ValueError('multiple_starts_in_record')
            starts[i]=band
        else:continuations.append(band)
    if len(starts)!=len(anchors):raise ValueError('missing_record_start')
    signatures=[typed_start(starts[i]['text']) for i in range(len(anchors))]
    support=signatures[0] is not None and len(set(signatures))==1
    groups=[[starts[i]] for i in range(len(anchors))]
    for band in continuations:
        eligible=[i for i,a in enumerate(anchors) if band['y']>a['y']+
                  min(band['height'],a['height'])*POLICY['start_alignment_height']]
        if not eligible:raise ValueError('continuation_before_first_record')
        i=max(eligible)
        if (i+1<len(anchors) and band['y']>=anchors[i+1]['y']-
                min(band['height'],anchors[i+1]['height'])*POLICY['start_alignment_height']):
            raise ValueError('ambiguous_continuation_boundary')
        previous=groups[i][-1]
        indented=band['left']-starts[i]['left']>=band['height']*POLICY['continuation_indent_height']
        hyphenated=previous['text'].rstrip().endswith(('-', '\u00ad', '\u2010'))
        # Another typed record label cannot be silently consumed as a continuation.
        if typed_start(band['text']) is not None or not (indented or hyphenated):
            raise ValueError('unsupported_continuation')
        band['continuation_reason']='preceding_hyphen' if hyphenated else 'indentation'
        groups[i].append(band)
    return groups,support


def core(box):
    l,t,r,b=box;cy=(t+b)/2;half=(b-t)*POLICY['core_height_fraction']/2
    return [l,cy-half,r,cy+half]


def propose(row_cells):
    if any(len(c['ocr'])>POLICY['max_ocr_per_target_cell'] for c in row_cells):
        raise ValueError('excessive_target_ocr')
    proposals=[];failures=[]
    for anchor_cell in row_cells:
        anchors=bands_for(anchor_cell);sig=[typed_start(b['text']) for b in anchors]
        if not POLICY['min_records']<=len(anchors)<=POLICY['max_records']:continue
        if not sig or any(s is None or s[0]!='number_unit' for s in sig) or len(set(sig))!=1:continue
        try:
            groups={};supported=[]
            for c in row_cells:
                partition,valid=assign_records(c,anchors);groups[c['cell_id']]=partition
                if valid and c['cell_id']!=anchor_cell['cell_id']:supported.append(c['cell_id'])
            if len(supported)<POLICY['min_support_columns']:raise ValueError('insufficient_independent_record_labels')
            top=max(c['bbox'][1] for c in row_cells);bottom=min(c['bbox'][3] for c in row_cells)
            scale=median(a['bbox'][3]-a['bbox'][1] for c in row_cells for a in c['ocr'])
            cores=[[] for _ in anchors]
            for c in row_cells:
                by={a['ocr_id']:a for a in c['ocr']}
                for i,partition in enumerate(groups[c['cell_id']]):
                    cores[i].extend(core(by[j]['bbox']) for b in partition for j in b['ocr_ids'])
            if any(b[1]<top or b[3]>bottom for record in cores for b in record):
                raise ValueError('record_evidence_outside_source_row')
            boundaries=[top]
            for previous,following in zip(cores,cores[1:]):
                end=max(b[3] for b in previous);start=min(b[1] for b in following)
                if start-end<scale*POLICY['min_core_gap_height']:raise ValueError('overlapping_record_cores')
                boundaries.append((end+start)/2)
            boundaries.append(bottom)
            if any(b<=a for a,b in zip(boundaries,boundaries[1:])):raise ValueError('invalid_record_boundaries')
            signature=tuple((cid,tuple(tuple(i for b in record for i in b['ocr_ids']) for record in partitions))
                            for cid,partitions in sorted(groups.items()))
            proposals.append({'anchor_cell_id':anchor_cell['cell_id'],'support_cell_ids':supported,
                'record_count':len(anchors),'groups':groups,'boundaries':boundaries,'signature':signature})
        except ValueError as exc:failures.append(str(exc))
    if not proposals:raise ValueError('no_supported_record_partition'+(':'+','.join(sorted(set(failures))) if failures else ''))
    if len({p['signature'] for p in proposals})!=1:raise ValueError('conflicting_anchor_partitions')
    return min(proposals,key=lambda p:p['anchor_cell_id'])


def reconstruct_records(trace):
    if trace.get('gate',{}).get('passed') or trace.get('gate',{}).get('reasons')!=[VETO]:
        return deepcopy(trace)
    out=deepcopy(trace)
    audit={'version':'v14','policy':deepcopy(POLICY),'status':'rejected','rows':[],
           'previous_gate':deepcopy(trace['gate']),'reasons':[]}
    out['record_reconstruction']=audit
    try:
        structure,mapped=validate(trace)
        replay=deepcopy(trace);replay['gate']={'passed':True,'reasons':[]}
        safety=guard_candidate(replay)
        if safety['gate']['reasons']!=[VETO]:raise ValueError('veto_not_reproduced')
        targets=sorted({p['row'] for p in safety['row_safety']['suspicions']})
        if not targets or len(targets)>POLICY['max_target_rows']:raise ValueError('unsupported_target_row_count')
        proposals={}
        for r in targets:
            if r==0:raise ValueError('unverified_body_row')
            cells=[c for c in trace['cells'] if c['row']<=r<c['row']+c['row_span']]
            if (len(cells)!=structure['num_cols'] or structure['num_cols']<3 or
                    any(c['row']!=r or c['row_span']!=1 or c['col_span']!=1 or c.get('is_header') for c in cells)):
                raise ValueError('target_row_contains_span_or_header')
            if (max(c['bbox'][1] for c in cells)-min(c['bbox'][1] for c in cells)>1e-6 or
                    max(c['bbox'][3] for c in cells)-min(c['bbox'][3] for c in cells)>1e-6):
                raise ValueError('inconsistent_source_row_geometry')
            natives=[c for c in structure['table_cells'] if key(c)[0]==r]
            if any(c.get('column_header') or c.get('row_header') or c.get('row_section') for c in natives):
                raise ValueError('target_row_contains_header')
            p=propose(sorted(cells,key=lambda c:c['col']));proposals[r]=p
            audit['rows'].append({'source_row':r,**{k:deepcopy(v) for k,v in p.items() if k not in ('groups','signature')}})
        new_rows=structure['num_rows']+sum(p['record_count']-1 for p in proposals.values())
        if new_rows*structure['num_cols']>POLICY['max_cells']:raise ValueError('excessive_rebuilt_grid')
        native_cells=[];bound_cells=[]
        for native in structure['table_cells']:
            source=mapped[key(native)];r=source['row'];offset=sum(p['record_count']-1 for y,p in proposals.items() if y<r)
            if r not in proposals:
                n=deepcopy(native);n['start_row_offset_idx']+=offset;n['end_row_offset_idx']+=offset
                c=deepcopy(source);c['row']+=offset
                c['origin_v14']={'operation':'row_offset' if offset else 'unchanged','source_cell_id':source['cell_id'],
                                  'source_coordinates':list(key(native))}
                native_cells.append(n);bound_cells.append(c);continue
            p=proposals[r];by={a['ocr_id']:a for a in source['ocr']}
            for i,bands in enumerate(p['groups'][source['cell_id']]):
                n=deepcopy(native);n.update(start_row_offset_idx=r+offset+i,end_row_offset_idx=r+offset+i+1,row_span=1)
                c=deepcopy(source);c['row']=r+offset+i
                c['bbox']=[source['bbox'][0],p['boundaries'][i],source['bbox'][2],p['boundaries'][i+1]]
                c['ocr_ids']=[j for b in bands for j in b['ocr_ids']];c['ocr']=[deepcopy(by[j]) for j in c['ocr_ids']]
                c['text']=' '.join(a['text'] for a in c['ocr']);n['text']=c['text']
                c['origin_v14']={'operation':'split_merged_record','source_cell_id':source['cell_id'],
                    'source_coordinates':list(key(native)),'record_index':i,'source_bbox':source['bbox'][:],
                    'continuations':[{'ocr_ids':b['ocr_ids'],'reason':b['continuation_reason']} for b in bands if 'continuation_reason' in b]}
                native_cells.append(n);bound_cells.append(c)
        ordered=sorted(zip(native_cells,bound_cells),key=lambda pair:key(pair[0]))
        native_cells=[n for n,c in ordered];bound_cells=[c for n,c in ordered]
        rebuilt=deepcopy(structure);rebuilt.update(num_rows=new_rows,table_cells=native_cells)
        raw=render_table_html(rebuilt)
        if raw is None:raise ValueError('invalid_rebuilt_html')
        parsed=parse_html_table(raw)[0]
        if [key(c) for c in parsed['table_cells']]!=[key(c) for c in native_cells]:raise ValueError('rebuilt_topology_drift')
        assignments=[]
        for i,c in enumerate(bound_cells):
            c['cell_id']=i
            for a in c['ocr']:
                old={k:deepcopy(a[k]) for k in ('cell_id','best_cell_id','coverage','runner_up_coverage','reason') if k in a}
                a['source_binding']=old;a['cell_id']=i;a['best_cell_id']=i
                a['coverage']=coverage(c['bbox'],a['bbox'])
                a.pop('runner_up_coverage',None)
                if c['origin_v14']['operation']=='split_merged_record':
                    a['vertical_core_bbox']=core(a['bbox']);a['core_coverage']=coverage(c['bbox'],a['vertical_core_bbox'])
                    if a['core_coverage']<.7:raise ValueError('rebuilt_core_not_contained')
                    a['reason']='record_anchor_or_verified_continuation'
                assignments.append(deepcopy(a))
        before={a['ocr_id']:(a['text'],a['bbox']) for c in trace['cells'] for a in c['ocr']}
        after={a['ocr_id']:(a['text'],a['bbox']) for a in assignments}
        if len(assignments)!=len(before) or before!=after:raise ValueError('loss_duplicate_or_text_geometry_mutation')
        # The old lattice refers to the unsplit rows and must not masquerade as current geometry.
        out['source_axes']=out.pop('axes',None)
        out['source_policy']=out.pop('policy',None)
        out['source_row_safety']=out.pop('row_safety',None)
        for stale in ('physical_boxes','unique_detections','unique_to_original_ids'):
            if stale in out:out['source_'+stale]=out.pop(stale)
        audit.update(status='reconstructed',ocr_preserved=True,rows_before=structure['num_rows'],rows_after=new_rows,
                     coordinates='original crop pixels; inferred logical cells, immutable padded OCR boxes')
        out.update(schema_version='record-reconstruction-v14',status='reconstructed_records_review_eligible',
            policy=deepcopy(POLICY),
            html=raw,cells=bound_cells,logical_cells=len(bound_cells),assignments=sorted(assignments,key=lambda a:a['ocr_id']),
            empty_cell_ids=[c['cell_id'] for c in bound_cells if not c['ocr_ids']],unassigned_ocr_ids=[],
            gate={'passed':True,'reasons':[],'policy':'Restricted record-anchor candidate; offline development only.'})
        return out
    except (KeyError,TypeError,ValueError,IndexError) as exc:
        audit['reasons'].append(str(exc));return out
