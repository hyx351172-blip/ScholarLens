"""Frozen v14 no-model replay of v13 record-ambiguity failures."""
import argparse
from pathlib import Path
import time

from audit_table_decoder import ROOT,read,write,sha
from experiment_unseen_tables import verify
from table_record_reconstruction import reconstruct_records

SOURCE=ROOT/'output/benchmarks/omnidocbench-table-safety-v13-bounded'
OLD=ROOT/'output/benchmarks/omnidocbench-table-header-v11'


def optional(path):return path.read_text(encoding='utf-8') if path.is_file() else None


def select_effective(previous,candidate,gate):
    if gate['passed']:
        if not candidate:raise ValueError('Passing gate without candidate')
        return candidate
    return previous


def run(output):
    if output.exists():raise ValueError('Fresh output required')
    source=read(SOURCE/'summary.json');protected=read(SOURCE/'input-integrity.json')
    protected.update({str(SOURCE/p):v for p,v in source['artifact_sha256'].items()})
    paths=[p for p in SOURCE.rglob('*') if p.is_file()]+[p for p in OLD.rglob('*') if p.is_file()]
    paths += [ROOT/'scripts'/n for n in ('table_record_reconstruction.py','experiment_table_records.py')]
    protected.update({str(p):sha(p) for p in paths});verify(protected)
    output.mkdir(parents=True);write(output/'input-integrity.json',protected)
    controls=[]
    for oldrow in read(OLD/'summary.json')['results']:
        path=OLD/oldrow['id']/'grid-trace.json'
        if path.is_file():
            original=read(path);new=reconstruct_records(original)
            if new!=original:raise ValueError('Old control drift: '+oldrow['id'])
        controls.append({'id':oldrow['id'],'trace_unchanged':True})
    write(output/'older-controls.json',controls)
    results=[]
    for prior in source['results']:
        case=prior['id'];src=SOURCE/'final'/case;dest=output/'final'/case;dest.mkdir(parents=True)
        previous=optional(src/'effective.html');trace=read(src/'grid-trace.json')
        started=time.perf_counter();repaired=reconstruct_records(trace);duration=time.perf_counter()-started
        status=repaired.get('record_reconstruction',{}).get('status','unchanged')
        candidate=repaired.get('html');effective=select_effective(previous,candidate,repaired['gate'])
        if status=='reconstructed' and not repaired['gate']['passed']:raise ValueError('Inconsistent repair status')
        if status!='reconstructed' and effective!=previous:raise ValueError('Unrepaired effective drift')
        for name,text in [('previous-effective',previous),('candidate',candidate),('effective',effective)]:
            if text:(dest/f'{name}.html').write_text(text,encoding='utf-8')
        write(dest/'grid-trace.json',repaired)
        info={'id':case,'page':prior['page'],'status':status,'gate':repaired['gate'],'replay_seconds':duration,
              'effective_source':'v14_record_reconstruction' if status=='reconstructed' else prior['effective_source'],
              'previous_effective_source':prior['effective_source'],'angle_ccw':prior['angle_ccw']}
        write(dest/'result.json',info);results.append(info)
        print(case,status,repaired.get('record_reconstruction',{}).get('reasons',[]),flush=True)
    verify(protected)
    artifacts={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}
    write(output/'summary.json',{'experiment':'table-record-reconstruction-v14','source':str(SOURCE),
        'cohort':'development-regression','results':results,'older_controls':controls,'model_calls':0,
        'paid_api_calls':0,'production_applied':False,'gold_access_in_inference':False,
        'protected_inputs_unchanged':True,'artifact_sha256':artifacts})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    run(p.parse_args().output.resolve())
