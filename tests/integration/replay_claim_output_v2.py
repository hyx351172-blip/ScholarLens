"""Offline replay of frozen provider content; never regenerate or overwrite v1."""
import asyncio
from collections import Counter
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.chat import claim_bound_answer as v1
from backend.chat import claim_bound_output_v2 as v2
from backend.chat.kb_chat import ChatRequest, ChatService
from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from tests.integration.compare_answer_modes import read, write, digest, value_hash, preflight

BASE=ROOT/'output/answer-mode-ab-v1'
OUT=ROOT/'output/claim-output-replay-v2'
EDITED=('backend/chat/kb_chat.py','tests/test_answer_mode_ab.py')


def verify_snapshot(snapshot,root,archive,edited=EDITED):
    unchanged,archived=0,[]
    for name,expected in snapshot.items():
        live=(root/name).resolve();live.relative_to(root.resolve())
        if name in edited:
            before=(archive/name).resolve();before.relative_to(archive.resolve())
            if digest(before)!=expected:
                raise ValueError('archived_prechange_code_mismatch')
            archived.append(dict(path=name,before_sha256=expected,current_sha256=digest(live)))
        else:
            if digest(live)!=expected:raise ValueError('unexpected_frozen_data_drift')
            unchanged+=1
    return dict(unchanged_files=unchanged,archived_code=archived)


async def replay_one(case,record):
    if record['id']!=case['id'] or record['mode']!='claim_bound' or record['status']!='ok':
        raise ValueError('invalid_cached_response_identity')
    if record['input_sha256']!=value_hash(case):raise ValueError('cached_input_drift')
    if not case['documents']:
        if record['guard_status']!='no_evidence' or record['provider_calls']!=0:
            raise ValueError('invalid_empty_control')
        before=after=INSUFFICIENT_EVIDENCE;old_status=new_status='no_evidence';binding=None
    else:
        if record['finish_reason']!='stop':raise ValueError('incomplete_cached_response')
        catalog=v1.build_catalog(case['documents'])
        before,old_binding=v1.render_claim_answer(record['raw_content'],catalog)
        if old_binding!=record['binding']:raise ValueError('v1_binding_not_reproduced')
        old_status=old_binding['status']
        expected,new_binding=v2.render_claim_answer(record['raw_content'],catalog)
        svc=ChatService();svc.call_llm_claims=AsyncMock(return_value=record['raw_content'])
        request=ChatRequest(query=case['query'],collection_name='cached',answer_mode='claim_bound',
            llm_config=dict(api_url='https://example.invalid',api_key='offline-placeholder',model_name='unused'))
        with patch('backend.chat.kb_chat.AsyncOpenAI',side_effect=AssertionError('offline_only')):
            after,new_status,binding=await svc.generate_answer(request,case['documents'],streaming=False)
        if after!=expected or binding!=new_binding:raise ValueError('production_dispatch_mismatch')
        svc.call_llm_claims.assert_awaited_once()  # Cached stub, not a provider call.
        if new_status=='claim_bound_passed':
            rows=json.loads(record['raw_content'])['claims']
            if len(rows)!=len(binding['claims']):raise ValueError('dropped_claim')
            for source,bound in zip(rows,binding['claims']):
                if source['text']!=bound['text'] or source['evidence_ids']!=[a['anchor_id'] for a in bound['evidence']]:
                    raise ValueError('rewritten_text_or_evidence')
                if after[bound['answer_start']:bound['answer_end']]!=source['text']:
                    raise ValueError('incorrect_answer_span')
        if old_status=='claim_bound_passed' and (old_binding['claims']!=binding['claims'] or before!=after):
            raise ValueError('previously_valid_output_changed')
    if before!=record['answer'] or old_status!=record['guard_status']:
        raise ValueError('v1_result_not_reproduced')
    return dict(id=case['id'],before_status=old_status,after_status=new_status,
        answer_changed=before!=after,answer=after,binding=binding,live_calls=0,
        semantic_verified=False,raw_sha256=value_hash(record['raw_content']),
        note='Cached-response replay, NOT a new live answer or human judgment.')


async def main():
    if (OUT/'summary.json').exists():raise FileExistsError('completed_replay_exists')
    manifest=read(BASE/'manifest.json');original=read(BASE/'paired-analysis.json')
    integrity=verify_snapshot(manifest['file_sha256'],ROOT,OUT/'baseline-code')
    # Raw output records, labels and original summary stay unchanged.
    for name,expected in original['artifacts_sha256'].items():
        if digest(BASE/name)!=expected:raise ValueError('original_result_changed')
    baseline_files={p.relative_to(ROOT).as_posix():digest(p) for p in BASE.iterdir() if p.is_file()}
    for historical in ('e2e-claim-audit-v2-final','e2e-claim-audit-v3','e2e-claim-audit-v3-1'):
        from tests.integration.compare_answer_modes import verify
        frozen=read(ROOT/'output'/historical/'manifest.json');verify(ROOT,frozen['file_sha256'])
    try:preflight(BASE,ROOT,True,22)
    except ValueError as exc:
        if str(exc)!='frozen_input_or_code_changed':raise
        integrity['old_live_experiment_rejects_changed_checkout']=True
    else:raise ValueError('old_live_drift_gate_missing')
    rows=[]
    for case in read(BASE/'inputs.json'):
        row=await replay_one(case,read(BASE/f"result-{case['id']}-claim_bound.json"))
        write(OUT/f"replay-{case['id']}.json",row);rows.append(row)
    changed=[r['id'] for r in rows if r['answer_changed']]
    if changed!=['A02','A03']:raise ValueError('unexpected_answer_change_set')
    for name,expected in baseline_files.items():
        if digest(ROOT/name)!=expected:raise ValueError('baseline_mutated_during_replay')
    labels={r['id']:r for r in read(BASE/'labels.json')}
    positive=[r for r in rows if labels[r['id']]['answerable']]
    negative=[r for r in rows if not labels[r['id']]['answerable']]
    summary=dict(experiment='claim-output-replay-v2',live_calls=0,cases=len(rows),
        answerable_cases=len(positive),before_rendered=sum(r['before_status']=='claim_bound_passed' for r in positive),
        after_rendered=sum(r['after_status']=='claim_bound_passed' for r in positive),
        unanswerable_cases=len(negative),unanswerable_refusals=sum(r['answer']==INSUFFICIENT_EVIDENCE for r in negative),
        changed_answers=changed,unchanged_answers=sum(not r['answer_changed'] for r in rows),
        status_counts=dict(Counter(r['after_status'] for r in rows)),
        warning_claims=[dict(case=r['id'],**w) for r in rows for w in (r['binding'] or {}).get('warnings',[])],
        baseline_sha256=baseline_files,integrity=integrity,
        current_code_sha256={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in (
            ROOT/'backend/chat/kb_chat.py',ROOT/'backend/chat/claim_bound_answer.py',
            ROOT/'backend/chat/claim_bound_output_v2.py',Path(__file__),ROOT/'tests/test_claim_output_v2.py')},
        claim_text_and_selected_ids_unchanged=True,semantic_accuracy_available=False,
        no_new_token_or_latency_measurements=True)
    write(OUT/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if not k.endswith('sha256')},ensure_ascii=False,indent=2))


if __name__=='__main__':asyncio.run(main())
