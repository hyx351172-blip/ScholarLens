"""Offline catalog audit. No old answer is rebound to new evidence IDs."""
import asyncio
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.chat import claim_bound_answer as old
from backend.chat import evidence_units as new
from backend.chat.kb_chat import ChatRequest, ChatService
from tests.integration.compare_answer_modes import (
    read, write, digest, value_hash, verify, packet, Gateway, PROTOCOL,
)
from tests.integration.replay_claim_output_v2 import verify_snapshot, replay_one

BASE = ROOT/'output/answer-mode-ab-v1'
PREVIOUS = ROOT/'output/claim-output-replay-v2'
OUT = ROOT/'output/evidence-units-v2'


def assert_coverage(documents, catalog):
    for index, doc in enumerate(documents, 1):
        source = f'S{index}'
        rows = [a for a in catalog if a['source_id'] == source]
        position = 0
        for row in rows:
            if row['start'] != position or row['end'] <= position:
                raise ValueError('noncontiguous_catalog')
            if row['text'] != doc['chunk_text'][position:row['end']]:
                raise ValueError('source_text_rewritten')
            position = row['end']
        if position != len(doc['chunk_text']):
            raise ValueError('incomplete_catalog_coverage')
    if len({a['anchor_id'] for a in catalog}) != len(catalog):
        raise ValueError('duplicate_anchor')


def inner_cuts(documents, catalog):
    """Heuristic diagnostic, not human Gold boundary accuracy."""
    cuts = []
    for index, doc in enumerate(documents, 1):
        source, text = f'S{index}', doc['chunk_text']
        spans = new.unit_spans(text)
        for row in (a for a in catalog if a['source_id'] == source):
            boundary = row['end']
            if any(start < boundary < end and text[start:boundary].strip() and text[boundary:end].strip()
                   for start, end in spans):
                cuts.append(dict(source_id=source, end=boundary, anchor_id=row['anchor_id']))
    return cuts


async def candidate_packet(case):
    if not case['documents']:
        return None
    request = ChatRequest(query=case['query'], collection_name='offline-catalog-audit',
        answer_mode='claim_bound', claim_evidence_mode='sentence_v2',
        llm_config=dict(api_url='https://example.invalid', api_key='offline-placeholder',
            model_name=PROTOCOL['model'], temperature=PROTOCOL['temperature'], max_tokens=PROTOCOL['max_tokens']))
    gateway = Gateway()  # No provider. Capture request, return an empty mock response.
    with patch('backend.chat.kb_chat.AsyncOpenAI', lambda **kwargs: gateway):
        await ChatService().generate_answer(request, case['documents'], streaming=False)
    if gateway.calls != 0 or gateway.request is None:
        raise ValueError('unexpected_gateway_state')
    return gateway.request


def known_excerpt(cases, cid, source_index, prefix, suffix):
    text = next(c for c in cases if c['id'] == cid)['documents'][source_index]['chunk_text']
    start = text.index(prefix)
    end = text.index(suffix, start)+len(suffix)
    data = [dict(chunk_text=text, filename='source.pdf')]
    before, after = old.build_catalog(data), new.build_catalog(data)
    old_hits = [a['anchor_id'] for a in before if a['start'] < end and a['end'] > start]
    new_hits = [a['anchor_id'] for a in after if a['start'] < end and a['end'] > start]
    if len(new_hits) != 1:
        raise ValueError('known_sentence_still_fragmented')
    return dict(case=cid, source_id=f'S{source_index+1}', start=start, end=end,
        excerpt=text[start:end], old_overlapping_anchors=len(old_hits),
        new_overlapping_anchors=len(new_hits), semantic_support_verified=False)


async def main():
    if (OUT/'summary.json').exists():
        raise FileExistsError('completed_audit_exists')
    OUT.mkdir(parents=True, exist_ok=True)
    previous = read(PREVIOUS/'summary.json')
    verify(ROOT, previous['baseline_sha256'])
    prior_code = verify_snapshot(previous['current_code_sha256'], ROOT, OUT/'baseline-code',
                                 edited=('backend/chat/kb_chat.py',))
    original_manifest = verify_snapshot(read(BASE/'manifest.json')['file_sha256'],
        ROOT, PREVIOUS/'baseline-code')
    for name in ('e2e-claim-audit-v2-final','e2e-claim-audit-v3','e2e-claim-audit-v3-1'):
        verify(ROOT, read(ROOT/'output'/name/'manifest.json')['file_sha256'])
    historical = {p.relative_to(ROOT).as_posix():digest(p)
                  for directory in (BASE, PREVIOUS) for p in directory.rglob('*') if p.is_file()}
    cases = read(BASE/'inputs.json')
    rows, unique_sources, stale_rejected, artifacts = [], set(), 0, {}
    for case in cases:
        data = case['documents']
        before = old.build_catalog(data) if data else []
        after = new.build_catalog(data) if data else []
        assert_coverage(data, after)
        for mode in ('legacy','claim_bound'):
            if await packet(case, mode) != read(BASE/f"request-{case['id']}-{mode}.json"):
                raise ValueError('default_request_changed')
        cached = read(BASE/f"result-{case['id']}-claim_bound.json")
        replay = await replay_one(case, cached)
        if replay != read(PREVIOUS/f"replay-{case['id']}.json"):
            raise ValueError('previous_replay_changed')
        if data and replay['after_status'] == 'claim_bound_passed':
            _, binding = new.render_claim_answer(cached['raw_content'], after)
            if binding['status'] != 'invalid_claim_structure':
                raise ValueError('stale_anchor_silently_rebound')
            stale_rejected += 1
        request = await candidate_packet(case)
        if request is not None:
            import json
            if json.loads(request['messages'][1]['content'])['evidence'] != after:
                raise ValueError('production_catalog_mismatch')
        old_cuts, new_cuts = inner_cuts(data, before), inner_cuts(data, after)
        # Character count is only prompt-size diagnostics, NOT billable tokens.
        old_request = read(BASE/f"request-{case['id']}-claim_bound.json")
        prompt_chars = lambda p: sum(len(m['content']) for m in p['messages']) if p else 0
        row = dict(id=case['id'], source_count=len(data), exact_coverage=True,
            old_anchors=len(before), new_anchors=len(after),
            old_inner_unit_cuts=len(old_cuts), new_inner_unit_cuts=len(new_cuts),
            fragmented_units=len({a['unit_id'] for a in after if a['parts'] > 1}),
            old_prompt_chars=prompt_chars(old_request), new_prompt_chars=prompt_chars(request))
        artifacts[f"catalog-{case['id']}.json"] = dict(input_sha256=value_hash(case),
            catalog=after, baseline_inner_cuts=old_cuts, candidate_inner_cuts=new_cuts)
        artifacts[f"request-{case['id']}.json"] = request
        rows.append(row)
        unique_sources.update(value_hash((d['filename'], d['chunk_text'])) for d in data)
    checks = [known_excerpt(cases, 'B01', 7, 'Specifically, when choosing', 'NotNext ).'),
              known_excerpt(cases, 'L01', 0, 'This means that when applying LoRA', 'pre-trained weight matrices.')]
    verify(ROOT, historical)
    summary = dict(experiment='evidence-units-v2', live_calls=0, cases=len(rows), rows=rows,
        unique_source_texts=len(unique_sources), stale_old_answers_rejected=stale_rejected,
        all_default_requests_unchanged=True, all_previous_replays_unchanged=True,
        known_excerpt_checks=checks, semantic_accuracy_available=False,
        limitations=['Sentence boundaries are heuristics, not human Gold.',
            'No new answer, paid token or latency measurement.',
            'Old E selections are never mapped onto U spans.',
            'Dimension selection, flattened formulas and overgeneralization still need live review.'],
        prior_code_integrity=prior_code, original_manifest_integrity=original_manifest,
        historical_sha256=historical,
        current_code_sha256={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in (
            ROOT/'backend/chat/evidence_units.py', ROOT/'backend/chat/kb_chat.py',
            ROOT/'tests/test_evidence_units.py', Path(__file__))})
    if any((OUT/name).exists() for name in artifacts):
        raise FileExistsError('partial_audit_exists')
    for name, value in artifacts.items():
        write(OUT/name, value)
    write(OUT/'summary.json', summary)
    import json
    print(json.dumps({k:v for k,v in summary.items() if not k.endswith('sha256')}, ensure_ascii=False, indent=2))


if __name__ == '__main__': asyncio.run(main())
