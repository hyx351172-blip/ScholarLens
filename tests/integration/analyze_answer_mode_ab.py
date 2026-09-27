"""Offline paired denominators and evidence-review packet; no semantic judge."""
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tests.integration.compare_answer_modes import OUT, MODES, read, write, digest, verify
from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from backend.chat.claim_bound_answer import build_catalog, render_claim_answer


def paired_metrics(labels,rows):
    by_id={(r['id'],r['mode']):r for r in rows}
    valid=[l for l in labels if all(by_id.get((l['id'],m),{}).get('status')=='ok' for m in MODES)]
    paired_live=[l for l in valid if all(by_id[l['id'],m]['provider_calls']==1 for m in MODES)]
    modes={}
    for mode in MODES:
        live=[by_id[l['id'],mode] for l in paired_live]
        positive=[by_id[l['id'],mode] for l in valid if l['answerable']]
        negative=[by_id[l['id'],mode] for l in valid if not l['answerable']]
        times=[r['seconds'] for r in live]
        modes[mode]=dict(answerable_cases=len(positive),unanswerable_cases=len(negative),
            answerable_fixed_refusals=sum(r.get('answer')==INSUFFICIENT_EVIDENCE for r in positive),
            answerable_nonrefusal_with_citations=sum(bool(r.get('answer')) and r['answer']!=INSUFFICIENT_EVIDENCE
                and bool(r['citation_ids']) and not r['unknown_citations'] for r in positive),
            unanswerable_fixed_refusals=sum(r.get('answer')==INSUFFICIENT_EVIDENCE for r in negative),
            mean_generation_seconds=statistics.mean(times) if times else None,
            median_generation_seconds=statistics.median(times) if times else None,
            tokens={k:sum((r.get('usage') or {}).get(k,0) or 0 for r in live)
                    for k in ('prompt_tokens','completion_tokens','total_tokens')})
    return dict(paired_cases=len(valid),paired_live_cases=len(paired_live),
        excluded_pairs=[l['id'] for l in labels if l not in valid],modes=modes,
        note='Structural response availability, NOT factual accuracy; failures retained separately.')


def rejected_claims(case,result):
    if result.get('guard_status')!='invalid_claim_structure':return []
    try:claims=json.loads(result['raw_content'])['claims']
    except (ValueError,KeyError,TypeError):return [dict(reason='invalid_json_or_envelope')]
    catalog=build_catalog(case['documents']);rows=[]
    for n,claim in enumerate(claims,1):
        _,binding=render_claim_answer(json.dumps(dict(status='answered',claims=[claim])),catalog)
        if binding['status']!='claim_bound_passed':
            rows.append(dict(claim_index=n,text=claim.get('text'),evidence_ids=claim.get('evidence_ids'),
                             reason=binding['status']))
    return rows


def main():
    manifest=read(OUT/'manifest.json');verify(ROOT,manifest['file_sha256'])
    cases=read(OUT/'inputs.json');labels=read(OUT/'labels.json')
    rows=[read(OUT/f"result-{c['id']}-{m}.json") for c in cases for m in MODES]
    paired=paired_metrics(labels,rows)
    rejected={c['id']:rejected_claims(c,read(OUT/f"result-{c['id']}-claim_bound.json")) for c in cases}
    bound_count=anchor_count=0;json_valid=0;lines=['# Answer-mode A/B evidence packet','',
        'AI inspection aid; NOT human Gold. No answers or original scores were rewritten.','']
    for case in cases:
        lines.extend([f"## {case['id']}",'',case['query'],''])
        catalog={a['anchor_id']:a for a in build_catalog(case['documents'])} if case['documents'] else {}
        for mode in MODES:
            result=read(OUT/f"result-{case['id']}-{mode}.json")
            lines.extend([f'### {mode}',f"Guard: {result.get('guard_status')}; status: {result['status']}",'',
                result.get('answer') or '(transport/provider error; no answer)',''])
            if mode=='claim_bound' and result.get('raw_content') is not None:
                try:json.loads(result['raw_content']);json_valid+=1
                except ValueError:pass
            for claim in (result.get('binding') or {}).get('claims',[]):
                bound_count+=1
                assert result['answer'][claim['answer_start']:claim['answer_end']]==claim['text']
                lines.extend([f"#### {claim['claim_id']}",claim['text'],''])
                for evidence in claim['evidence']:
                    anchor=catalog[evidence['anchor_id']];doc=case['documents'][int(anchor['source_id'][1:])-1]
                    assert evidence['start']==anchor['start'] and evidence['end']==anchor['end']
                    assert doc['chunk_text'][anchor['start']:anchor['end']]==anchor['text']
                    anchor_count+=1
                    lines.extend([f"{anchor['anchor_id']} · {anchor['filename']} · chars {anchor['start']}:{anchor['end']}",
                                  '',anchor['text'],''])
        for diagnostic in rejected[case['id']]:
            lines.extend(['### Rejection diagnostic (not repaired)',json.dumps(diagnostic,ensure_ascii=False),''])
    # Scan only approved local result files; report a boolean, never the value.
    from dotenv import dotenv_values
    env=dotenv_values(ROOT/'.env')
    secrets=[v for k,v in env.items() if 'KEY' in k.upper() and isinstance(v,str) and len(v)>12]
    paths=[p for p in OUT.iterdir() if p.is_file()]
    secret_free=all(not any(key in p.read_text(encoding='utf-8') for key in secrets) for p in paths)
    if not secret_free:raise ValueError('secret_scan_failed')
    paired.update(json_parseable_claim_bound_responses=json_valid,
        bound_claims=bound_count,exact_anchor_occurrences=anchor_count,
        rejection_diagnostics={k:v for k,v in rejected.items() if v},secrets_found=False,
        artifacts_sha256={p.name:digest(p) for p in paths},
        analysis_code_sha256=digest(Path(__file__)),analysis_test_sha256=digest(ROOT/'tests/test_answer_mode_ab_analysis.py'))
    write(OUT/'paired-analysis.json',paired)
    with (OUT/'comparison-review.md').open('x',encoding='utf-8') as handle:handle.write('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in paired.items() if k not in ('artifacts_sha256','rejection_diagnostics')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
