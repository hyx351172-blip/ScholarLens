"""Frozen, no-gold header reconstruction v11. No model/network/API calls."""
import argparse
from pathlib import Path
import time
import cv2
import numpy as np

from audit_table_decoder import preflight, read, write, sha, parse_html_table
from experiment_table_grid_binding import fresh_output, verify_run, verify_hashes, png_size, FROZEN_MANIFEST, CAPTURES
from table_header_reconstruction import repair_header


def assert_previous_success(trace, previous_trace):
    if previous_trace['gate']['passed'] and (not trace['gate']['passed'] or trace['html'] != previous_trace['html']):
        raise ValueError('Previously passing output changed')


def load_crop(path):
    width,height=png_size(path)
    if not 0<width*height<=40_000_000 or max(width,height)>50000:
        raise ValueError('Crop exceeds pixel budget')
    gray=cv2.imdecode(np.frombuffer(path.read_bytes(),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
    if gray is None or gray.shape!=(height,width): raise ValueError('Crop decode/shape mismatch')
    return gray


def run(prepared,v8,v9,v10,output):
    prepared,v8,v9,v10,output=[p.resolve() for p in (prepared,v8,v9,v10,output)]
    fresh_output(output,[prepared,v8,v9,v10]); manifest=preflight(prepared,output)
    if sha(prepared/'manifest.json')!=FROZEN_MANIFEST: raise ValueError('Unknown frozen cohort')
    prior=read(v10/'summary.json'); verify_run(v10,prior)
    if prior['manifest_sha256']!=FROZEN_MANIFEST: raise ValueError('Prior cohort mismatch')
    hashes=dict(prior['protected_hashes'])
    paths=[v10/'summary.json',Path(__file__).resolve(),Path(__file__).with_name('table_header_reconstruction.py').resolve()]
    paths.extend(v10/relative for relative in prior['artifact_sha256'])
    for item in manifest['results']:
        case=item['id']; source=v8/'extended'/case/'structure.html'; paths.append(source)
        if case in CAPTURES:
            capture=v9/case/'binding-capture.json'; response=v9/case/'response.json'
            if sha(capture)!=CAPTURES[case]: raise ValueError('Capture changed')
            r=read(response)
            if r['structure_sha256']!=sha(source) or r['crop_sha256']!=item['crop_sha256']:
                raise ValueError('Structure/crop provenance mismatch')
            paths.extend([capture,response])
    hashes.update({str(p):sha(p) for p in paths}); verify_hashes(hashes)
    output.mkdir(parents=True); write(output/'input-integrity.json',hashes)
    summary={'experiment':'table-header-reconstruction-v11','gold_access_in_inference':False,'production_applied':False,
             'model_calls':0,'paid_api_calls':0,'manifest_sha256':FROZEN_MANIFEST,'protected_hashes':hashes,
             'versions':{'numpy':np.__version__,'opencv':cv2.__version__},'results':[]}
    for item in manifest['results']:
        case=item['id']; dest=output/case; dest.mkdir(); started=time.perf_counter()
        row={'id':case,'page':item['page'],'gate':{'passed':False,'reasons':[]}}
        raw=(v8/'extended'/case/'structure.html').read_text(encoding='utf-8')
        try: parse_html_table(raw)
        except ValueError as exc:
            row.update(status='invalid_v8_structure_baseline_retained',error=str(exc))
            row['gate']['reasons']=['invalid_v8_structure']
        else:
            if case not in CAPTURES: raise ValueError('Missing approved capture')
            trace=repair_header(raw,read(v9/case/'binding-capture.json'),load_crop(prepared/item['crop']))
            assert_previous_success(trace,read(v10/case/'grid-trace.json'))
            write(dest/'grid-trace.json',trace)
            if trace['html'] is not None: (dest/'raw-candidate.html').write_text(trace['html'],encoding='utf-8')
            if trace.get('repaired_structure_html'):
                (dest/'repaired-structure.html').write_text(trace['repaired_structure_html'],encoding='utf-8')
            row.update(status=trace['status'],gate=trace['gate'],ocr_count=len(trace['assignments']),
                       unassigned_ocr=len(trace['unassigned_ocr_ids']),logical_cells=len(trace['cells']))
            for name in ('header_rows_before','header_rows_after','body_topology_preserved'):
                if name in trace: row[name]=trace[name]
        row['replay_seconds']=time.perf_counter()-started; write(dest/'result.json',row)
        summary['results'].append(row); print(case,row['status'],row['gate']['reasons'],flush=True)
    verify_hashes(hashes); verify_run(v10,prior)
    summary['protected_inputs_unchanged']=True
    summary['artifact_sha256']={p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    write(output/'summary.json',summary)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','v8','v9','v10','output'): p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args(); run(a.prepared,a.v8,a.v9,a.v10,a.output)
