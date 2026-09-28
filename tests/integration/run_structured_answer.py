"""Frozen cached-plan experiment; 20 answer calls, no label access during inference."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.chat.structured_answer import POLICY, render_answer


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    import requests
    from openai import AsyncOpenAI
    base=ROOT/'output/qasper-evidence-plan-v1'
    out=ROOT/'output/qasper-structured-v1'
    inputs=json.loads((base/'inputs.json').read_text(encoding='utf-8'))
    assert len(inputs)==20
    code_hash=digest(ROOT/'backend/chat/structured_answer.py')
    files=['inputs.json','labels.json']+[f'prediction-{i:02d}.json' for i in range(20)]
    hashes={name:digest(base/name) for name in files}
    if not out.exists():
        out.mkdir()
        for name in ('inputs.json','labels.json'):
            (out/name).write_bytes((base/name).read_bytes())
        (out/'manifest.json').write_text(json.dumps({'code_sha256':code_hash,'cached_files':hashes,
            'scope':'Paired dev experiment with frozen cached plans; not held-out or E2E'},indent=2),encoding='utf-8')
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['cached_files']==hashes and manifest['code_sha256']==code_hash
    with requests.Session() as session:
        session.trust_env=False
        r=session.get('http://127.0.0.1:8501/config/default',timeout=10)
        r.raise_for_status()
        config=r.json()['config']['llm']
    async with AsyncOpenAI(api_key=config['api_key'],base_url=config['api_url'],max_retries=0,timeout=120) as client:
        for i,item in enumerate(inputs):
            path=out/f'prediction-{i:02d}.json'
            if path.exists():
                old=json.loads(path.read_text(encoding='utf-8'))
                assert old['question_id']==item['question_id'] and old['code_sha256']==code_hash
                continue
            cached=json.loads((base/f'prediction-{i:02d}.json').read_text(encoding='utf-8'))
            assert cached['question_id']==item['question_id']
            candidates=[dict(candidate_id=f'C{n}',**p) for n,p in enumerate(cached['planning']['validated'],1)]
            expected=[p['candidate_id'] for p in candidates] or ['C1']
            start=time.monotonic()
            response=await client.chat.completions.create(model=config['model_name'],temperature=0,max_tokens=2200,
                messages=[{'role':'system','content':POLICY},{'role':'user','content':
                    f"Question: {item['question']}\nCandidates: {json.dumps(candidates,ensure_ascii=False)}\nOriginal paper:\n{item['context']}"}])
            raw=response.choices[0].message.content or ''
            try:
                parsed=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip()))
            except ValueError:
                parsed=None
            sources=dict(re.findall(r'(?:^|\n\n)\[(S\d+)\] (.*?)(?=\n\n\[S\d+\] |\Z)',item['context'],re.S))
            answer,status=render_answer(parsed,sources,expected)
            result=dict(question_id=item['question_id'],paper_id=item['paper_id'],code_sha256=code_hash,
                structured_raw=raw,structured=parsed,answer=answer,draft=answer,guard_status=status,
                seconds=time.monotonic()-start,finish_reason=response.choices[0].finish_reason,
                model=config['model_name'],usage=response.usage.model_dump(),
                cached_planner_seconds_note='Not included; reused prior plan',candidates=candidates)
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(i+1,status,round(result['seconds'],2),flush=True)


if __name__=='__main__':
    asyncio.run(main())
