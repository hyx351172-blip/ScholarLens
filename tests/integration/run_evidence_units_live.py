"""Five-call opt-in follow-up; frozen evidence, no paid judge or retrieval."""
import argparse
import asyncio
from collections import Counter
import copy
import json
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.chat.kb_chat import ChatRequest, ChatService
from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from backend.chat.evidence_units import build_catalog
from tests.integration.compare_answer_modes import (
    read, write, digest, value_hash, verify, Gateway, load_live_config,
    PROTOCOL as BASE_PROTOCOL,
)
from tests.integration.audit_evidence_units import candidate_packet

IDS=('B01','L01','L03','X02','A04','E01')
POSITIVE=IDS[:4]
PROTOCOL=dict(BASE_PROTOCOL, execution='sequential_candidate_only',
    answer_mode='claim_bound', claim_evidence_mode='sentence_v2', max_calls=5)
BASE=ROOT/'output/answer-mode-ab-v1'
AUDIT=ROOT/'output/evidence-units-v2'
OUT=ROOT/'output/evidence-units-live-v1'


def select_inputs(values):
    selected=[]
    for cid in IDS:
        matches=[c for c in values if c['id']==cid]
        if len(matches)!=1:
            raise ValueError('case_selection_mismatch')
        row=matches[0]
        if (cid=='E01') != (row['documents']==[]):
            raise ValueError('unexpected_evidence_presence')
        if not isinstance(row['query'],str) or any(
                d.get('source_id')!=f'S{i}' for i,d in enumerate(row['documents'],1)):
            raise ValueError('invalid_case')
        selected.append(copy.deepcopy({k:row[k] for k in ('id','query','documents')}))
    return selected


async def prepare(out=OUT):
    if out.exists():
        raise FileExistsError('experiment_already_exists')
    audit=read(AUDIT/'summary.json')
    verify(ROOT,audit['historical_sha256']);verify(ROOT,audit['current_code_sha256'])
    cases=select_inputs(read(BASE/'inputs.json'))
    packets={c['id']:await candidate_packet(c) for c in cases}
    for cid,request in packets.items():
        if request!=read(AUDIT/f'request-{cid}.json'):
            raise ValueError('audited_request_changed')
    frozen=dict(audit['historical_sha256'])
    paths=[p for p in AUDIT.rglob('*') if p.is_file()]
    paths+=list((ROOT/'backend/chat').glob('*.py'))
    paths+=list((ROOT/'tests/integration').glob('*.py'))
    paths+=[ROOT/'tests/test_evidence_units_live.py',ROOT/'backend/requirements.txt',
            ROOT/'docs/specs/evidence_units_live/acceptance.md',
            ROOT/'tests/traceability/evidence_units_live/coverage.py']
    frozen.update({p.relative_to(ROOT).as_posix():digest(p) for p in paths})
    out.mkdir(parents=True,exist_ok=False)
    write(out/'inputs.json',cases)
    write(out/'labels.json',[dict(id=c['id'],answerable=c['id'] in POSITIVE,human_verified=False) for c in cases])
    for cid,request in packets.items():
        write(out/f'request-{cid}.json',request)
    frozen.update({p.relative_to(ROOT).as_posix():digest(p) for p in out.iterdir() if p.is_file()})
    write(out/'manifest.json',dict(experiment='evidence-units-live-v1',cases=list(IDS),
        planned_calls=5,protocol=PROTOCOL,file_sha256=frozen,human_gold=False,
        scope='Candidate-only development follow-up; historical comparison is NOT paired A/B'))
    return dict(status='prepared_not_run',cases=6,planned_calls=5,frozen_files=len(frozen),
                total_prompt_characters=sum(len(m['content']) for p in packets.values() if p for m in p['messages']))


def preflight(out,root,approved,max_calls):
    if approved is not True or type(max_calls) is not int or max_calls!=5:
        raise ValueError('explicit_five_call_approval_required')
    manifest=read(out/'manifest.json')
    if manifest.get('protocol')!=PROTOCOL or manifest.get('planned_calls')!=5 or manifest.get('cases')!=list(IDS):
        raise ValueError('protocol_drift')
    verify(root,manifest['file_sha256'])
    attempts=list(out.glob('attempt-*.json'))
    if len(attempts)>5:
        raise ValueError('call_budget_exceeded')
    for path in attempts:
        cid=path.stem.removeprefix('attempt-')
        if cid not in IDS[:-1]:
            raise ValueError('unexpected_attempt')
        if not (out/f'result-{cid}.json').exists():
            raise ValueError('unresolved_attempt_no_automatic_retry')
    if any(p.stem.removeprefix('result-') not in IDS for p in out.glob('result-*.json')):
        raise ValueError('unexpected_result')


async def dispatch(case,gateway):
    request=ChatRequest(query=case['query'],collection_name='frozen-follow-up',
        answer_mode='claim_bound',claim_evidence_mode='sentence_v2',stream=False,
        llm_config=dict(api_url='https://example.invalid',api_key='offline-placeholder',
            model_name=PROTOCOL['model'],temperature=0,max_tokens=2000))
    with patch('backend.chat.kb_chat.AsyncOpenAI',lambda **kwargs:gateway):
        return await ChatService().generate_answer(request,case['documents'],streaming=False)


async def generate(case,expected,provider):
    if await candidate_packet(case)!=expected:
        raise ValueError('frozen_request_drift')
    result=dict(id=case['id'],mode='sentence_v2',status='ok',input_sha256=value_hash(case),
        request_sha256=value_hash(expected),provider_calls=0,seconds=0,raw_content=None,
        finish_reason=None,usage={},binding=None)
    if not case['documents']:
        result.update(answer=INSUFFICIENT_EVIDENCE,guard_status='no_evidence')
        return result
    gateway=Gateway(provider,expected);started=time.monotonic()
    try:
        answer,status,binding=await dispatch(case,gateway)
        result.update(answer=answer,guard_status=status,binding=binding)
    except Exception as exc:
        result.update(status='error',error_type=type(exc).__name__,answer=None,guard_status=None)
    result.update(gateway.observation,seconds=round(time.monotonic()-started,4),provider_calls=gateway.calls)
    return result


def redact(result,key):
    serialized=json.dumps(result,ensure_ascii=False)
    if key and key in serialized:
        result=json.loads(serialized.replace(key,'[REDACTED]'))
        result['secret_redacted']=True
    return result


def summarize(results):
    generated=[r for r in results if r['provider_calls']]
    fields=('prompt_tokens','completion_tokens','total_tokens')
    measured=[r for r in generated if all(type((r.get('usage') or {}).get(k)) is int for k in fields)]
    return dict(experiment='evidence-units-live-v1',cases=len(results),planned_cases=6,
        errors=sum(r['status']=='error' for r in results),provider_calls=sum(r['provider_calls'] for r in results),
        answerable_cases=sum(r['id'] in POSITIVE for r in results),
        answerable_output_count=sum(r['id'] in POSITIVE and r['guard_status']=='claim_bound_passed' for r in results),
        negative_refusals=sum(r['id'] not in POSITIVE and r.get('answer')==INSUFFICIENT_EVIDENCE for r in results),
        guard_status_counts=dict(Counter(r['guard_status'] for r in results)),
        finish_reason_counts=dict(Counter(r.get('finish_reason') for r in generated)),
        usage_measured_calls=len(measured),usage_unknown_calls=len(generated)-len(measured),
        measured_token_totals={k:sum(r['usage'][k] for r in measured) if measured else None for k in fields},
        generation_seconds=dict(count=len(generated),mean=statistics.mean(r['seconds'] for r in generated) if generated else None),
        semantic_accuracy_available=False,human_review_status='pending',
        scope='Candidate-only development follow-up; historical comparison is NOT paired A/B')


def review_case(case,result):
    catalog={a['anchor_id']:a for a in build_catalog(case['documents'])} if case['documents'] else {}
    cards=[]
    for claim in (result.get('binding') or {}).get('claims',[]):
        if result['answer'][claim['answer_start']:claim['answer_end']]!=claim['text']:
            raise ValueError('claim_span_mismatch')
        evidence=[]
        for ref in claim['evidence']:
            anchor=catalog[ref['anchor_id']]
            if any(ref[k]!=anchor[k] for k in ('source_id','start','end','unit_id','part','parts')):
                raise ValueError('citation_span_mismatch')
            evidence.append(dict(anchor))
        cards.append(dict(claim_id=claim['claim_id'],text=claim['text'],selected_evidence=evidence,
                          human_support_verdict=None,human_notes=None))
    return dict(id=case['id'],question=case['query'],claims=cards,human_answer_verdict=None,
                semantic_verified=False,review_status='PENDING_HUMAN_NOT_GOLD')


async def run(approved,max_calls,out=OUT):
    preflight(out,ROOT,approved,max_calls)
    cases=select_inputs(read(out/'inputs.json'))
    if (out/'summary.json').exists():
        completed=read(out/'summary.json')
        verify(out,completed['artifacts_sha256'])
        return completed
    # Check every prompt before loading a real credential or constructing a client.
    for case in cases:
        if await candidate_packet(case)!=read(out/f"request-{case['id']}.json"):
            raise ValueError('production_request_drift')
    saved={}
    for case in cases:
        path=out/f"result-{case['id']}.json"
        if not path.exists():continue
        result=read(path)
        if (result.get('id')!=case['id'] or result.get('mode')!='sentence_v2'
                or result['input_sha256']!=value_hash(case)
                or result['request_sha256']!=value_hash(read(out/f"request-{case['id']}.json"))):
            raise ValueError('completed_result_identity_drift')
        if case['documents'] and not (out/f"attempt-{case['id']}.json").exists():
            raise ValueError('completed_result_missing_attempt')
        if result['status']=='error':
            return dict(status='partial_provider_error',failed_case=case['id'],automatic_retry=False)
        saved[case['id']]=result
    config=load_live_config()
    from openai import AsyncOpenAI
    rows=[]
    async with AsyncOpenAI(api_key=config['api_key'],base_url=config['api_url'],
        max_retries=0,timeout=PROTOCOL['sdk_timeout_seconds']) as client:
        for case in cases:
            preflight(out,ROOT,approved,max_calls)
            cid=case['id'];expected=read(out/f'request-{cid}.json')
            if cid in saved:
                rows.append(saved[cid]);continue
            if expected is not None:
                if len(list(out.glob('attempt-*.json')))>=max_calls:
                    raise ValueError('budget_exhausted')
                write(out/f'attempt-{cid}.json',dict(id=cid,started=time.time(),
                    request_sha256=value_hash(expected),max_output_tokens=2000))
            result=redact(await generate(case,expected,client.chat.completions.create),config['api_key'])
            write(out/f'result-{cid}.json',result);rows.append(result)
            print(cid,result['status'],result['guard_status'],result['seconds'],flush=True)
            if result['status']=='error':
                return dict(status='partial_provider_error',failed_case=cid,automatic_retry=False,
                    completed_cases=len(rows),provider_error_type=result.get('provider_error_type'),
                    provider_status_code=result.get('provider_status_code'))
    preflight(out,ROOT,approved,max_calls)
    review=[review_case(c,r) for c,r in zip(cases,rows)]
    write(out/'human-review.json',review)
    summary=summarize(rows)
    summary['artifacts_sha256']={p.name:digest(p) for p in out.iterdir() if p.is_file()}
    write(out/'summary.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=('prepare','run'))
    parser.add_argument('--approved',action='store_true');parser.add_argument('--max-calls',type=int)
    args=parser.parse_args()
    try:
        result=asyncio.run(prepare() if args.stage=='prepare' else run(args.approved,args.max_calls))
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as exc:
        # Never print credentials, provider text or a raw traceback.
        print(json.dumps(dict(status='error',error_type=type(exc).__name__)))
        raise SystemExit(1)
