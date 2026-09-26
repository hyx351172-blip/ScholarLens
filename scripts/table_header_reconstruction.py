"""Evidence-limited local header repair; no gold, model calls or label guessing.

The supported seam is a collapsed physical header band above an unchanged body,
with known top-level column groups. General borderless topology is not inferred.
"""
import copy
import math
from statistics import median

import cv2
import numpy as np

from audit_table_decoder import parse_html_table
from table_structure import render_table_html
from table_grid_binding import bind_grid
from table_ocr_binding import coverage, key, structure_signature


def header_depth(structure):
    """First row whose covering cells are all atomic, confirmed by two next rows."""
    cells = structure['table_cells']
    def regular(r):
        cover = [c for c in cells if key(c)[0] <= r < key(c)[0]+key(c)[2]]
        return len(cover) == structure['num_cols'] and all(key(c)[2:] == (1,1) for c in cover)
    for r in range(1,min(7,structure['num_rows']-2)):
        if all(regular(y) for y in (r,r+1,r+2)): return r
    return None


def _runs(values):
    padded = np.r_[False, values, False].astype(np.int8)
    edges = np.diff(padded)
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def ruling_evidence(gray, xs, top, bottom, body_height):
    mask = cv2.morphologyEx((gray < 180).astype(np.uint8), cv2.MORPH_OPEN,
                            np.ones((max(3,round(body_height*.75)),1),np.uint8))
    radius = max(2,math.ceil(median(b-a for a,b in zip(xs,xs[1:]))*.18))
    lo, hi = max(0,math.floor(top)), min(gray.shape[0],math.ceil(bottom))
    evidence=[]
    for index,x in enumerate(xs):
        x0,x1=max(0,round(x)-radius),min(gray.shape[1],round(x)+radius+1)
        candidates=[]
        for px in range(x0,x1):
            for a,b in _runs(mask[lo:hi,px]):
                if b >= hi-lo-2 and b-a >= body_height*.65:
                    candidates.append((int(b-a),-abs(px-x),px,int(a+lo),int(b+lo)))
        best=max(candidates) if candidates else None
        evidence.append({'boundary':index,'x':x,'pixel_x':best[2] if best else None,
                         'start':best[3] if best else None,'end':best[4] if best else None})
    return evidence


def _cell(r,c,rs=1,cs=1):
    return {'text':'','start_row_offset_idx':r,'end_row_offset_idx':r+rs,
            'start_col_offset_idx':c,'end_col_offset_idx':c+cs,'row_span':rs,'col_span':cs,
            'column_header':False,'row_header':False,'row_section':False,'bbox':None}


def _bind(structure, xs, ys, captured):
    cells=[]; text=captured['render']['texts']; boxes=captured['match']['ocr_boxes']
    for i,c in enumerate(structure['table_cells']):
        r,col,rs,cs=key(c)
        cells.append({'cell_id':i,'row':r,'col':col,'row_span':rs,'col_span':cs,
                      'bbox':[xs[col],ys[r],xs[col+cs],ys[r+rs]],'ocr_ids':[],'text':''})
    assignments=[]
    for i,b in enumerate(boxes):
        ranks=sorted(((coverage(c['bbox'],b),c['cell_id']) for c in cells),reverse=True)
        best,target=ranks[0]; second=ranks[1][0] if len(ranks)>1 else 0
        accepted=best>=.7 and best-second>=.4
        assignments.append({'ocr_id':i,'text':text[i],'bbox':b[:],
                            'cell_id':target if accepted else None,'coverage':best,'runner_up_coverage':second})
        if accepted: cells[target]['ocr_ids'].append(i)
    filled=copy.deepcopy(structure)
    for c,f in zip(cells,filled['table_cells']):
        c['ocr_ids'].sort(key=lambda i:(boxes[i][1],boxes[i][0],i))
        c['text']=' '.join(text[i] for i in c['ocr_ids']); f['text']=c['text']
        c['ocr']=[copy.deepcopy(assignments[i]) for i in c['ocr_ids']]
    raw=render_table_html(filled)
    if structure_signature(raw)!=[key(c) for c in structure['table_cells']]:
        raise ValueError('Header rendering changed topology')
    return raw,cells,assignments


def header_hierarchy(cells, depth, columns):
    nodes=[]
    for c in cells:
        if c['row']>=depth or not c['text'].strip(): continue
        node={k:copy.deepcopy(c[k]) for k in ('cell_id','row','col','row_span','col_span','text','ocr_ids')}
        parents=[n for n in nodes if n['row']+n['row_span']<=c['row'] and
                 n['col']<=c['col'] and c['col']+c['col_span']<=n['col']+n['col_span']]
        parent=max(parents,key=lambda n:(n['row'],-n['col_span'])) if parents else None
        node['parent_id']=parent['cell_id'] if parent else None
        nodes.append(node)
    paths=[]
    for col in range(columns):
        chain=sorted([n for n in nodes if n['col']<=col<n['col']+n['col_span']],key=lambda n:n['row'])
        paths.append({'col':col,'cell_ids':[n['cell_id'] for n in chain],'texts':[n['text'] for n in chain]})
    return nodes,paths


def repair_header(structure_html,captured,gray):
    if (not isinstance(gray,np.ndarray) or gray.dtype!=np.uint8 or gray.ndim!=2 or
            not 0<gray.size<=40_000_000 or max(gray.shape)>50000):
        raise ValueError('Expected bounded uint8 grayscale crop')
    # Preserve v10 validation and successful behavior byte-for-byte.
    prior=bind_grid(structure_html,captured,[gray.shape[1],gray.shape[0]])
    if prior['gate']['passed']:
        return dict(prior,status='unchanged_v10_success')
    out={'schema_version':'header-reconstruction-v11','status':'header_rejected_baseline_retained',
         'html':None,'gate':{'passed':False,'reasons':[]},'prior_gate':prior['gate'],
         'cells':[],'assignments':[],'header_tree':[],'header_paths':[],
         'unassigned_ocr_ids':list(range(prior['ocr_count']))}
    def reject(reason):
        out['gate']['reasons'].append(reason); return out
    s=parse_html_table(structure_html)[0]; old_depth=header_depth(s)
    out['header_rows_before']=old_depth
    if old_depth is None or old_depth<2: return reject('unsupported_header_prefix')
    if not prior['axes']['x']['count_matches'] or not all(a['stable'] for a in prior['axes'].values()):
        return reject('unstable_or_inconsistent_axes')
    xs=prior['axes']['x']['boundaries']; physical_y=prior['axes']['y']['boundaries']
    if len(physical_y)<5 or len(physical_y)-2!=s['num_rows']-old_depth:
        return reject('body_row_count_conflict')
    height=median(b-a for a,b in zip(physical_y[1:],physical_y[2:])); top,bottom=physical_y[:2]
    if bottom-top<height*1.6 or bottom-top>height*8: return reject('no_collapsed_header_band')
    roots=[c for c in s['table_cells'] if key(c)[0]==0]
    groups=[c for c in roots if key(c)[2]==1 and key(c)[3]>1]
    anchors=[c for c in roots if key(c)[2]==old_depth]
    if len(groups)<2 or len(groups)+len(anchors)!=len(roots): return reject('unsupported_header_roots')
    # Every spanning standalone root needs a detector rectangle covering its band.
    for c in anchors:
        _,col,_,span=key(c); expected=[xs[col],top,xs[col+span],bottom]
        if not any(coverage(expected,b)>=.85 and coverage(b,expected)>=.85 for b in captured['geometry_reprocessing']['detected_boxes']):
            return reject('unverified_rowspan_anchor')
    lines=ruling_evidence(gray,xs,top,bottom,height); out['ruling_evidence']=lines
    starts=[]
    for gi,g in enumerate(groups):
        _,col,_,span=key(g)
        # Original group borders must really continue through the header.
        if any(lines[c]['start'] is None or lines[c]['start']>top+height*.25 for c in (col,col+span)):
            return reject('missing_parent_group_ruling')
        for c in range(col+1,col+span):
            start=lines[c]['start']
            if start is not None and start<=top+height*.25:
                return reject('ruling_conflicts_with_parent_span')
            if start is not None and top+height*.5<start<bottom-height*.5:
                starts.append((start,gi,c))
    clusters=[]
    for item in sorted(starts):
        if not clusters or item[0]-median(x[0] for x in clusters[-1])>height*.2: clusters.append([])
        clusters[-1].append(item)
    if not clusters or len(clusters)>5 or any(len({x[1] for x in cluster})<2 for cluster in clusters):
        return reject('header_levels_not_independently_supported')
    levels=[top]+[median(x[0] for x in cluster) for cluster in clusters]+[bottom]
    depth=len(levels)-1; out['header_rows_after']=depth; out['header_y']=levels
    if depth<old_depth or any(b-a<height*.5 for a,b in zip(levels,levels[1:])):
        return reject('implausible_header_levels')
    # OCR must independently populate every level in two distinct parent groups.
    ocr=captured['match']['ocr_boxes']; group_ocr={}; level_groups=[set() for _ in range(depth)]
    for i,b in enumerate(ocr):
        cx,cy=(b[0]+b[2])/2,(b[1]+b[3])/2
        if not top<=cy<bottom: continue
        for gi,g in enumerate(groups):
            _,col,_,span=key(g)
            if xs[col]<=cx<xs[col+span]:
                if coverage([xs[col],top,xs[col+span],bottom],b)<.7: return reject('ocr_crosses_parent_group')
                r=next(r for r in range(depth) if levels[r]<=cy<levels[r+1])
                group_ocr.setdefault((gi,r),[]).append(i); level_groups[r].add(gi)
    out['level_support']=[sorted(v) for v in level_groups]
    if any(len(v)<2 for v in level_groups): return reject('ocr_does_not_corroborate_levels')
    new_cells=[]
    for c in anchors:
        _,col,_,span=key(c); new_cells.append(_cell(0,col,depth,span))
    for gi,g in enumerate(groups):
        _,col,_,span=key(g); new_cells.append(_cell(0,col,1,span))
        for r in range(1,depth):
            mid=(levels[r]+levels[r+1])/2
            cuts=[col]+[c for c in range(col+1,col+span) if lines[c]['start'] is not None and lines[c]['start']<=levels[r]+height*.25 and lines[c]['end']>=mid]+[col+span]
            for left,right in zip(cuts,cuts[1:]):
                ids=[i for i in group_ocr.get((gi,r),[]) if xs[left]<=(ocr[i][0]+ocr[i][2])/2<xs[right]]
                if len(ids)>1: return reject('multiple_header_texts_in_unsplit_region')
                if ids:
                    if coverage([xs[left],levels[r],xs[right],levels[r+1]],ocr[ids[0]])<.7:
                        return reject('header_ocr_span_conflict')
                    new_cells.append(_cell(r,left,1,right-left))
                else:
                    # No semantic merge inferred solely from blank space.
                    new_cells.extend(_cell(r,c) for c in range(left,right))
    offset=depth-old_depth
    for c in s['table_cells']:
        if key(c)[0]<old_depth: continue
        n=copy.deepcopy(c); n['start_row_offset_idx']+=offset; n['end_row_offset_idx']+=offset; new_cells.append(n)
    new_cells.sort(key=key)
    new=dict(s,num_rows=s['num_rows']+offset,table_cells=new_cells)
    blank=render_table_html(new)
    if blank is None: return reject('invalid_rebuilt_topology')
    rebuilt=parse_html_table(blank)[0]
    before=[key(c) for c in s['table_cells'] if key(c)[0]>=old_depth]
    after=[(key(c)[0]-offset,*key(c)[1:]) for c in rebuilt['table_cells'] if key(c)[0]>=depth]
    out['body_topology_preserved']=before==after
    if before!=after: return reject('body_topology_changed')
    ys=levels[:-1]+physical_y[1:]
    raw,cells,assignments=_bind(rebuilt,xs,ys,captured)
    original_ids={key(c):i for i,c in enumerate(s['table_cells'])}
    for c in cells:
        r,col,rs,cs=c['row'],c['col'],c['row_span'],c['col_span']
        c['is_header']=r<depth
        if r>=depth:
            source=(r-offset,col,rs,cs); operation='body_row_offset'
        else:
            parent=next(g for g in roots if key(g)[1]<=col and col+cs<=key(g)[1]+key(g)[3])
            source=key(parent)
            operation=('extend_rowspan' if parent in anchors else 'preserve_parent' if r==0 else 'infer_child_span')
        c['origin']={'operation':operation,'source_structure_cell_id':original_ids[source],
                     'source_coordinates':list(source)}
    nodes,paths=header_hierarchy(cells,depth,s['num_cols'])
    out.update(html=raw,cells=cells,assignments=assignments,header_tree=nodes,header_paths=paths,
               repaired_structure_html=blank,axes={'x':xs,'y':ys},
               before_header_signature=[key(c) for c in s['table_cells'] if key(c)[0]<old_depth],
               after_header_signature=[key(c) for c in rebuilt['table_cells'] if key(c)[0]<depth],
               unassigned_ocr_ids=[a['ocr_id'] for a in assignments if a['cell_id'] is None])
    if out['unassigned_ocr_ids']: return reject('unassigned_or_ambiguous_ocr')
    out['gate']={'passed':True,'reasons':[],'policy':'Evidence-limited offline header candidate; OCR accuracy and generalization unproven.'}
    out['status']='repaired_header_review_eligible'
    return out
