"""No-gold upstream diagnostics and one lossless model-wrapper correction.

This module never admits a candidate, edits OCR, or relaxes geometric checks.
"""
from html.parser import HTMLParser
import re

from audit_table_decoder import parse_html_table
from table_grid_binding import bind_grid


class _Tags(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=False)
        self.offsets=[0]
        for m in re.finditer('\n',raw):self.offsets.append(m.end())
        self.tags=[]

    def remember(self,kind,tag):
        line,col=self.getpos();self.tags.append((kind,tag,self.offsets[line-1]+col))

    def handle_starttag(self,tag,attrs):self.remember('start',tag)
    def handle_endtag(self,tag):self.remember('end',tag)
    def handle_startendtag(self,tag,attrs):self.remember('self',tag)


def normalize_wrapper(raw):
    out={'status':'rejected','html':None,'edits':[],'reason':None,
         'policy':'syntax only; strict topology and downstream geometry still required'}
    if not isinstance(raw,str) or not raw or len(raw)>1_000_000:
        out['reason']='missing_or_excessive_html';return out
    try:
        parse_html_table(raw);out.update(status='unchanged',html=raw);return out
    except ValueError as exc:out['original_error']=str(exc)
    parser=_Tags(raw)
    try:parser.feed(raw);parser.close()
    except (ValueError,AssertionError) as exc:
        out['reason']='tokenization_failed: '+str(exc);return out
    groups=[(i,t) for i,t in enumerate(parser.tags) if t[1] in ('thead','tbody','tfoot')]
    if len(groups)!=1 or groups[0][1][:2]!=('end','tbody'):
        out['reason']='not_single_orphan_tbody';return out
    i,(_,_,start)=groups[0]
    if (i==0 or i+1>=len(parser.tags) or parser.tags[i-1][:2]!=('end','tr') or
            parser.tags[i+1][:2]!=('end','table')):
        out['reason']='orphan_not_after_final_row';return out
    match=re.match(r'</tbody\s*>',raw[start:],re.I)
    prev=parser.tags[i-1][2]
    if not match or not re.fullmatch(r'</tr\s*>\s*',raw[prev:start],re.I):
        out['reason']='unexpected_row_suffix';return out
    end=start+match.end()
    if raw[end:parser.tags[i+1][2]].strip():
        out['reason']='unexpected_table_suffix';return out
    candidate=raw[:start]+raw[end:]
    try:parse_html_table(candidate)
    except ValueError as exc:
        out['reason']='strict_validation_failed: '+str(exc);return out
    out.update(status='repaired',html=candidate,reason=None,
        edits=[{'operation':'remove_orphan_tbody_end','start':start,'end':end,'removed':raw[start:end]}])
    return out


def axis_diagnosis(axis):
    actual=len(axis['boundaries']);expected=axis['expected_boundaries'];delta=actual-expected
    return {'expected_boundaries':expected,'detected_boundaries':actual,'difference':delta,
        'relation':'equal_counts' if delta==0 else ('fewer_detected_boundaries' if delta<0 else 'more_detected_boundaries'),
        'stable':axis['stable'],'all_cluster_count':len(axis['all_clusters']),
        'unselected_cluster_count':len(axis['all_clusters'])-len(axis['selected_edges']),
        'tolerance_trial_counts':[len(b) for b in axis['stability_boundaries']],
        'interpretation':'relative count only; neither decoder nor detector is ground truth'}


def diagnose_candidate(raw,captured,crop_size,detector_capacity=None):
    norm=normalize_wrapper(raw)
    out={'normalization':norm,'status':'invalid_html','grid':None,'ambiguous_ocr':[],
         'model_calls':0,'paid_api_calls':0,'gold_access':False,'production_applied':False}
    if norm['html'] is None:return out
    try:
        structure=parse_html_table(norm['html'])[0]
        grid=bind_grid(norm['html'],captured,crop_size)
    except (KeyError,ValueError,TypeError,IndexError) as exc:
        out.update(status='invalid_capture',error=str(exc));return out
    out.update(status='diagnosed',grid=grid,
        structure_shape=[structure['num_rows'],structure['num_cols']],
        axes={a:axis_diagnosis(grid['axes'][a]) for a in ('x','y')},
        detector_capacity=detector_capacity,
        at_detector_capacity=detector_capacity is not None and grid['physical_boxes']==detector_capacity,
        detector_cells=grid['physical_boxes'],logical_cells=grid['logical_cells'])
    for a in grid['assignments']:
        if a['cell_id'] is not None:continue
        b=a['bbox']
        out['ambiguous_ocr'].append({**a,
            'crossed_x_boundaries':[x for x in grid['axes']['x']['boundaries'][1:-1] if b[0]<x<b[2]],
            'crossed_y_boundaries':[y for y in grid['axes']['y']['boundaries'][1:-1] if b[1]<y<b[3]]})
    return out
