"""Frozen-capture v16 audit: no inference, no gold, no production promotion."""
import argparse
import base64
import html
import json
import math
from pathlib import Path

from audit_table_decoder import ROOT,CACHE,read,write,sha
from experiment_unseen_tables import verify
from table_candidate_diagnostics import diagnose_candidate

SOURCE=ROOT/'output/benchmarks/omnidocbench-table-records-validation-v15'


def graph_topk_nodes(graph):
    ops=graph['program']['regions'][0]['blocks'][0]['ops'];producers={}
    for op in ops:
        outputs=op.get('O',[])
        if isinstance(outputs,dict):outputs=[outputs]
        for value in outputs:
            if '%' in value:producers[value['%']]=op
    rows=[]
    for index,op in enumerate(ops):
        if not op.get('#','').endswith('.topk'):continue
        constant=producers.get(op['I'][1]['%'],{})
        attrs={a['N']:a['AT']['D'] for a in constant.get('A',[])}
        value=attrs.get('value') if constant.get('#','').endswith('.full') else None
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0 or value!=int(value):value=None
        rows.append({'op_index':index,'k':int(value) if value is not None else None,
            'constant_op':constant.get('#'),'constant_attributes':attrs,
            'output_types':[o.get('TT') for o in op.get('O',[])]})
    return rows


def same_artifact(a,b):
    return a.is_file()==b.is_file() and (not a.is_file() or sha(a)==sha(b))


def overlay(image_bytes,size,diagnostic,capture):
    """Unmodified source pixels with independent, switchable vector overlays."""
    width,height=size;grid=diagnostic['grid'];groups=[]
    if grid:
        boxes=capture['geometry_reprocessing']['detected_boxes']
        groups.append('<g class="detections" fill="none" stroke="#2563eb" stroke-width="1.4">')
        for i,(l,t,r,b) in enumerate(boxes):
            groups.append(f'<rect x="{l}" y="{t}" width="{r-l}" height="{b-t}"><title>Detection {i}</title></rect>')
        groups.append('</g><g class="axes" stroke="#059669" stroke-width="2" stroke-dasharray="8 5">')
        for x in grid['axes']['x']['boundaries']:groups.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{height}"/>')
        for y in grid['axes']['y']['boundaries']:groups.append(f'<line x1="0" y1="{y}" x2="{width}" y2="{y}"/>')
        groups.append('</g><g class="ocr" fill="none" stroke="#d97706" stroke-width="1">')
        for i,(l,t,r,b) in enumerate(capture['match']['ocr_boxes']):
            title=html.escape(f"OCR {i}: {capture['render']['texts'][i]}")
            groups.append(f'<rect x="{l}" y="{t}" width="{r-l}" height="{b-t}"><title>{title}</title></rect>')
        groups.append('</g><g class="ambiguous" fill="none" stroke="#dc2626" stroke-width="3">')
        for item in diagnostic['ambiguous_ocr']:
            l,t,r,b=item['bbox'];title=html.escape(f"Unassigned OCR {item['ocr_id']}: {item['text']}")
            groups.append(f'<rect x="{l}" y="{t}" width="{r-l}" height="{b-t}"><title>{title}</title></rect>')
        groups.append('</g>')
    compact={k:v for k,v in diagnostic.items() if k not in ('grid','normalization','ambiguous_ocr')}
    compact['normalization']={k:v for k,v in diagnostic['normalization'].items() if k!='html'}
    compact['gate']=grid['gate'] if grid else None
    compact['ambiguous_ocr']=diagnostic['ambiguous_ocr']
    return ''.join(['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">',
        '<title>Table geometry audit</title><style>body{font:15px system-ui;margin:24px}label{margin-right:20px}pre{white-space:pre-wrap}.canvas{max-width:1200px;border:1px solid #ddd}svg{width:100%;height:auto}',
        '#d:not(:checked)~.canvas .detections,#a:not(:checked)~.canvas .axes,#o:not(:checked)~.canvas .ocr,#u:not(:checked)~.canvas .ambiguous{display:none}</style>',
        '<h1>Source / geometry / OCR audit</h1><p>Blue: detector boxes. Green: inferred axes (NOT gold). Orange: OCR. Red: unassigned OCR. No source pixels edited.</p>',
        '<input id="d" type="checkbox"><label for="d">Detector</label><input id="a" type="checkbox" checked><label for="a">Axes</label>',
        '<input id="o" type="checkbox"><label for="o">OCR</label><input id="u" type="checkbox" checked><label for="u">Ambiguous OCR</label>',
        f'<div class="canvas"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"><image width="{width}" height="{height}" href="data:image/png;base64,',
        base64.b64encode(image_bytes).decode(), '"/>',*groups,'</svg></div><h2>Diagnostics</h2><pre>',
        html.escape(json.dumps(compact,ensure_ascii=False,indent=2)),'</pre>'])


def run(output):
    if output.exists():raise ValueError('Fresh output required')
    import cv2
    import numpy as np
    from PIL import Image
    from table_header_reconstruction import repair_header
    from table_candidate_safety import guard_candidate
    from table_record_reconstruction import reconstruct_records
    protected=read(SOURCE/'frozen-inputs.json')
    previous=read(SOURCE/'validation/summary.json')
    protected.update({str(SOURCE/p):s for p,s in previous['artifact_sha256'].items()})
    paths=[SOURCE/'validation/summary.json',Path(__file__).resolve(),ROOT/'scripts/table_candidate_diagnostics.py']
    graphs={}
    for kind in ('wired','wireless'):
        path=CACHE/f'RT-DETR-L_{kind}_table_cell_det/inference.json';paths.append(path)
        graphs[kind]={'path':str(path),'sha256':sha(path),'topk_nodes':graph_topk_nodes(read(path))}
    limits=[n['k'] for g in graphs.values() for n in g['topk_nodes']]
    capacity=limits[0] if limits and all(n is not None and n==limits[0] for n in limits) else None
    protected.update({str(p):sha(p) for p in paths});verify(protected)
    output.mkdir();write(output/'input-integrity.json',protected);write(output/'detector-graph-audit.json',graphs)
    rows=[]
    for item in read(SOURCE/'prepared/manifest.json')['cases']:
        case=item['id'];dest=output/case;dest.mkdir();src=SOURCE/'paddle'/case
        raw=(src/'structure.html').read_text(encoding='utf-8');capture=read(src/'binding-capture.json')
        crop=SOURCE/'prepared'/item['crop'];image_bytes=crop.read_bytes()
        with Image.open(crop) as image:size=list(image.size)
        diagnosis=diagnose_candidate(raw,capture,size,capacity);normalized=diagnosis['normalization']['html']
        write(dest/'diagnostics.json',diagnosis)
        if normalized is not None:(dest/'normalized-structure.html').write_text(normalized,encoding='utf-8')
        (dest/'overlay.html').write_text(overlay(image_bytes,size,diagnosis,capture),encoding='utf-8')
        if normalized is None:trace={'gate':{'passed':False,'reasons':['invalid_structure_html']}}
        else:
            gray=cv2.imdecode(np.frombuffer(image_bytes,dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
            trace=reconstruct_records(guard_candidate(repair_header(normalized,capture,gray)))
        write(dest/'downstream-trace.json',trace)
        previous_path=SOURCE/'validation'/case/'v14.html'
        previous_html=previous_path.read_text(encoding='utf-8') if previous_path.is_file() else None
        effective=trace.get('html') if trace['gate']['passed'] else previous_html
        if trace['gate']['passed'] and not effective:raise ValueError('Passing without output')
        if effective is not None:(dest/'effective.html').write_text(effective,encoding='utf-8')
        row={'id':case,'page':item['page'],'normalization':diagnosis['normalization']['status'],
            'shape':diagnosis.get('structure_shape'),'axes':diagnosis.get('axes'),
            'detector_cells':diagnosis.get('detector_cells'),'at_detector_capacity':diagnosis.get('at_detector_capacity'),
            'grid_gate':diagnosis['grid']['gate'] if diagnosis['grid'] else None,
            'ambiguous_ocr_count':len(diagnosis['ambiguous_ocr']),'downstream_gate':trace['gate'],
            'effective_byte_identical':same_artifact(dest/'effective.html',previous_path),'missing_output':effective is None}
        rows.append(row);print(case,row['normalization'],row['grid_gate'],flush=True)
    verify(protected)
    artifact_hashes={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}
    write(output/'summary.json',{'experiment':'upstream-table-diagnostics-v16','source':str(SOURCE),
        'cohort':'v15 now inspected for diagnosis; development, not a new held-out',
        'results':rows,'detector_capacity':capacity,'model_calls':0,'paid_api_calls':0,
        'gold_access':False,'production_applied':False,'protected_inputs_unchanged':True,
        'artifact_sha256':artifact_hashes})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    run(p.parse_args().output.resolve())
