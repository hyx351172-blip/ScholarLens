"""Write-once paired answer-generation experiment; no retrieval or paid judge."""
import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.chat.kb_chat import ChatRequest, ChatService
from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from backend.chat.claim_bound_answer import build_catalog

BASE = ROOT/'output/e2e-document-scope-v1'
OUT = ROOT/'output/answer-mode-ab-v1'
IDS = ('A01','A02','A03','A04','B01','B03','L01','L03','L04','X01','X02','E01')
MODES = ('legacy','claim_bound')
PROTOCOL = dict(model='qwen3-vl-plus', temperature=0, max_tokens=2000,
                max_retries=0, sdk_timeout_seconds=60, total_call_seconds=90,
                repeats=1, execution='sequential_counterbalanced', paid_judge=False)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    with path.open('x',encoding='utf-8') as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False)
        handle.write('\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()


def verify(root, hashes):
    for name, expected in hashes.items():
        path=(root/name).resolve()
        path.relative_to(root.resolve())
        if digest(path)!=expected:
            raise ValueError('frozen_input_or_code_changed')


def make_inputs(base):
    cases=[]
    for cid in IDS:
        record=read(base/f'answer-{cid}.json')
        response=record.get('response') or {}
        docs=response.get('sources') or []
        if response.get('success') is not True or not isinstance(record.get('query'),str):
            raise ValueError('invalid_baseline')
        if (cid=='E01') != (docs==[]):
            raise ValueError('unexpected_evidence_presence')
        if any(d.get('source_id')!=f'S{i}' for i,d in enumerate(docs,1)):
            raise ValueError('invalid_source_order')
        if docs: build_catalog(docs)
        cases.append(dict(id=cid,query=record['query'],documents=docs))
    return cases


def pair_order(cases):
    return [(case,mode) for i,case in enumerate(cases)
            for mode in (MODES if i%2==0 else MODES[::-1])]


class Gateway:
    """Capture actual production request kwargs; transport is the sole adapter."""
    def __init__(self, provider=None, expected=None):
        self.provider,self.expected=provider,expected
        self.request=None;self.calls=0;self.observation={}
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False

    async def create(self,**kwargs):
        self.request=kwargs
        if self.provider is None:
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
                message=SimpleNamespace(content='',refusal=None))])
        if kwargs!=self.expected:
            raise ValueError('request_drift')
        if self.calls:
            raise ValueError('second_call_forbidden')
        self.calls+=1
        try:
            response=await asyncio.wait_for(self.provider(**kwargs),timeout=PROTOCOL['total_call_seconds'])
        except Exception as exc:
            code=getattr(exc,'status_code',None)
            self.observation=dict(provider_error_type=type(exc).__name__,
                provider_status_code=code if type(code) is int else None)
            raise
        choice=response.choices[0] if response.choices else None
        usage=response.usage.model_dump() if response.usage else {}
        self.observation=dict(raw_content=choice.message.content if choice else None,
            finish_reason=choice.finish_reason if choice else None,
            provider_refusal=bool(getattr(choice.message,'refusal',None)) if choice else False,
            usage={k:usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens')})
        return response


async def _dispatch(case,mode,gateway):
    # Placeholder credentials exist only to satisfy production request validation.
    # Actual credentials belong exclusively to the outer real provider client.
    request=ChatRequest(query=case['query'],collection_name='frozen-no-retrieval',
        llm_config=dict(api_url='https://example.invalid/v1',api_key='offline-placeholder',
            model_name=PROTOCOL['model'],temperature=PROTOCOL['temperature'],max_tokens=PROTOCOL['max_tokens']),
        answer_mode=mode,stream=False,history=[])
    with patch('backend.chat.kb_chat.AsyncOpenAI',lambda **kwargs:gateway):
        return await ChatService().generate_answer(request,case['documents'],streaming=False)


async def packet(case,mode):
    if not case['documents']: return None
    gateway=Gateway()
    await _dispatch(case,mode,gateway)
    return gateway.request


async def generate(case,mode,expected,provider):
    if await packet(case,mode)!=expected:
        raise ValueError('frozen_request_drift')
    result=dict(id=case['id'],mode=mode,status='ok',input_sha256=value_hash(case),
                request_sha256=value_hash(expected),provider_calls=0,seconds=0,
                raw_content=None,finish_reason=None,usage={},binding=None)
    if not case['documents']:
        result.update(answer=INSUFFICIENT_EVIDENCE,guard_status='no_evidence')
    else:
        gateway=Gateway(provider,expected);start=time.monotonic()
        try:
            answer,status,binding=await _dispatch(case,mode,gateway)
            result.update(answer=answer,guard_status=status,binding=binding)
        except Exception as exc:
            # Never persist a provider exception's message, traceback or request.
            result.update(status='error',error_type=type(exc).__name__,answer=None,guard_status=None)
        result.update(gateway.observation,seconds=round(time.monotonic()-start,4),provider_calls=gateway.calls)
    cited=list(dict.fromkeys(re.findall(r'\[(S[1-9]\d*)\]',result.get('answer') or '')))
    known={d['source_id'] for d in case['documents']}
    result.update(citation_ids=cited,unknown_citations=[sid for sid in cited if sid not in known])
    return result


def preflight(out,root,approved,max_calls):
    manifest=read(out/'manifest.json')
    if approved is not True or type(max_calls) is not int or max_calls!=22:
        raise ValueError('explicit_22_call_approval_required')
    if manifest.get('protocol')!=PROTOCOL or manifest.get('planned_calls')!=22:
        raise ValueError('protocol_drift')
    verify(root,manifest['file_sha256'])
    for attempt in out.glob('attempt-*.json'):
        if not (out/attempt.name.replace('attempt-','result-',1)).exists():
            raise ValueError('unresolved_attempt_no_automatic_retry')
    if len(list(out.glob('attempt-*.json')))>22:
        raise ValueError('call_budget_exceeded')


async def prepare(out=OUT):
    if out.exists(): raise FileExistsError('experiment_directory_already_exists')
    cases=make_inputs(BASE)
    from tests.integration.run_multipaper_journey import CASES
    labels=[dict(id=c[0],answerable=c[4],targets=c[1],expected=c[3],human_verified=False)
            for c in CASES if c[0] in IDS]
    if sum(c['answerable'] for c in labels)!=9:
        raise ValueError('unexpected_label_counts')
    packets={(c['id'],m):await packet(c,m) for c,m in pair_order(cases)}
    historical={}
    for name in ('e2e-claim-audit-v2-final','e2e-claim-audit-v3','e2e-claim-audit-v3-1'):
        p=ROOT/'output'/name/'manifest.json';manifest=read(p)
        verify(ROOT,manifest['file_sha256']);historical.update(manifest['file_sha256'])
        historical[p.relative_to(ROOT).as_posix()]=digest(p)
    paths=[BASE/f'answer-{cid}.json' for cid in IDS]
    paths+=list((ROOT/'backend/chat').glob('*.py'))
    paths+=[Path(__file__),ROOT/'tests/test_answer_mode_ab.py',ROOT/'tests/integration/run_multipaper_journey.py',
        ROOT/'docs/specs/answer_mode_ab/acceptance.md',ROOT/'tests/traceability/answer_mode_ab/coverage.py']
    historical.update({p.relative_to(ROOT).as_posix():digest(p) for p in paths})
    out.mkdir(parents=True,exist_ok=False)
    write(out/'inputs.json',cases);write(out/'labels.json',labels)
    for (cid,mode),p in packets.items():write(out/f'request-{cid}-{mode}.json',p)
    historical.update({p.relative_to(ROOT).as_posix():digest(p) for p in out.iterdir() if p.is_file()})
    manifest=dict(experiment='answer-mode-ab-v1',split='development',prepared_only=True,
        cases=list(IDS),planned_calls=22,protocol=PROTOCOL,file_sha256=historical,
        inference_label_access=False,human_gold=False,
        scope='Frozen-evidence generation experiment, NOT live retrieval/E2E or held-out')
    write(out/'manifest.json',manifest)
    return dict(cases=len(cases),answerable=9,unanswerable_with_evidence=2,empty=1,
                planned_calls=22,frozen_files=len(historical))


def load_live_config():
    from tests.integration.run_multipaper_journey import api
    config=None
    for port in (8502,8501):
        try: config=api(port,'/config/default',timeout=5)['config']['llm']
        except Exception: continue
        break
    if config is None:
        # Use this checkout's existing config only; no service start or key output.
        from dotenv import dotenv_values
        env=dotenv_values(ROOT/'.env')
        config=dict(api_url=env.get('MODEL_URL',''),api_key=env.get('API_KEY',''),
                    model_name=env.get('MODEL_NAME',''))
    url=urlsplit(config.get('api_url',''))
    if (url.scheme!='https' or url.hostname not in (
        'dashscope.aliyuncs.com','dashscope-intl.aliyuncs.com','dashscope-us.aliyuncs.com')
        or config.get('model_name')!=PROTOCOL['model'] or not config.get('api_key')):
        raise ValueError('configured_provider_or_model_mismatch')
    return config


def summarize(labels,results):
    lookup={item['id']:item for item in labels};modes={}
    for mode in MODES:
        rows=[r for r in results if r['mode']==mode]
        answerable=[r for r in rows if lookup[r['id']]['answerable']]
        negative=[r for r in rows if not lookup[r['id']]['answerable']]
        generated=[r for r in rows if r['provider_calls']]
        times=[r['seconds'] for r in generated]
        modes[mode]=dict(cases=len(rows),errors=sum(r['status']=='error' for r in rows),
            answerable_cases=len(answerable),unanswerable_cases=len(negative),
            answerable_fixed_refusals=sum(r.get('answer')==INSUFFICIENT_EVIDENCE for r in answerable),
            unanswerable_fixed_refusals=sum(r.get('answer')==INSUFFICIENT_EVIDENCE for r in negative),
            answerable_with_valid_citation=sum(bool(r.get('citation_ids')) and not r.get('unknown_citations') for r in answerable),
            guard_status_counts=dict(Counter(r.get('guard_status') for r in rows)),
            finish_reason_counts=dict(Counter(r.get('finish_reason') for r in generated)),
            provider_calls=sum(r['provider_calls'] for r in rows),
            token_usage={k:sum((r.get('usage') or {}).get(k,0) or 0 for r in rows)
                         for k in ('prompt_tokens','completion_tokens','total_tokens')},
            generation_seconds=dict(count=len(times),mean=statistics.mean(times) if times else None,
                median=statistics.median(times) if times else None,max=max(times) if times else None))
    return dict(experiment='answer-mode-ab-v1',modes=modes,semantic_accuracy_available=False,
        human_review_status='pending',baseline_unchanged=True,
        scope='Paired development generation; structural counts are NOT semantic accuracy')


async def run(approved,max_calls,out=OUT):
    preflight(out,ROOT,approved,max_calls)
    cases=read(out/'inputs.json')
    if tuple(c['id'] for c in cases)!=IDS: raise ValueError('case_selection_drift')
    if (out/'summary.json').exists(): return read(out/'summary.json')
    # Precheck every frozen production prompt before loading credentials or calling.
    for case,mode in pair_order(cases):
        if await packet(case,mode)!=read(out/f"request-{case['id']}-{mode}.json"):
            raise ValueError('packet_drift')
    config=load_live_config()
    from openai import AsyncOpenAI
    rows=[]
    async with AsyncOpenAI(api_key=config['api_key'],base_url=config['api_url'],
                           max_retries=0,timeout=PROTOCOL['sdk_timeout_seconds']) as client:
        for case,mode in pair_order(cases):
            preflight(out,ROOT,approved,max_calls)
            name=f"{case['id']}-{mode}";path=out/f'result-{name}.json'
            expected=read(out/f'request-{name}.json')
            if path.exists():
                result=read(path)
                if (result['input_sha256']!=value_hash(case) or result['request_sha256']!=value_hash(expected)):
                    raise ValueError('completed_result_identity_drift')
                rows.append(result);continue
            if expected is not None:
                if len(list(out.glob('attempt-*.json')))>=max_calls: raise ValueError('budget_exhausted')
                write(out/f'attempt-{name}.json',dict(id=case['id'],mode=mode,started=time.time(),
                    request_sha256=value_hash(expected),max_output_tokens=PROTOCOL['max_tokens']))
            result=await generate(case,mode,expected,client.chat.completions.create)
            # Unlikely but explicit: never store a secret echoed by a remote error/model.
            serialized=json.dumps(result,ensure_ascii=False)
            if config['api_key'] in serialized:
                result=json.loads(serialized.replace(config['api_key'],'[REDACTED]'))
                result['secret_redacted']=True
            write(path,result);rows.append(result)
            print(name,result['status'],result['guard_status'],result['seconds'],flush=True)
            if result['status']=='error':
                # Stop on first transport/provider error; do not burn the budget.
                return dict(status='partial_provider_error',completed_pairs=len(rows),
                    failed_pair=name,provider_error_type=result.get('provider_error_type'),
                    provider_status_code=result.get('provider_status_code'),automatic_retry=False)
    preflight(out,ROOT,approved,max_calls)
    summary=summarize(read(out/'labels.json'),rows)
    write(out/'summary.json',summary)
    review=dict(status='PENDING_HUMAN_REVIEW_NOT_GOLD',items=[dict(id=c['id'],
        legacy_file=f"result-{c['id']}-legacy.json",claim_bound_file=f"result-{c['id']}-claim_bound.json",
        completeness=None,own_evidence_support=None,preferred_mode=None,reviewer='') for c in cases])
    write(out/'human-review.json',review)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('prepare','run','config-check'))
    p.add_argument('--approved',action='store_true');p.add_argument('--max-calls',type=int)
    args=p.parse_args()
    try:
        if args.stage=='prepare': result=asyncio.run(prepare())
        elif args.stage=='run': result=asyncio.run(run(args.approved,args.max_calls))
        else:
            cfg=load_live_config();result=dict(model=cfg['model_name'],host=urlsplit(cfg['api_url']).hostname,key_present=True)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as exc:
        # No traceback/provider message or credentials in terminal output.
        print(json.dumps(dict(status='error',error_type=type(exc).__name__)))
        raise SystemExit(1)
