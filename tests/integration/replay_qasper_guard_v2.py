"""Offline paired replay; never overwrite v1 predictions or call a model."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.chat.answer_guard import guard_answer, INSUFFICIENT_EVIDENCE


def main():
    out = ROOT/'output/qasper-guard-dev-v1'
    target = out/'guard-v2-replay.json'
    if target.exists():
        raise RuntimeError('Refuse to overwrite replay')
    inputs = json.loads((out/'inputs.json').read_text(encoding='utf-8'))
    labels = {x['question_id']:x['label'] for x in json.loads((out/'labels.json').read_text(encoding='utf-8'))}
    rows = []
    for i, item in enumerate(inputs):
        p = out/f'prediction-{i:02d}.json'
        old = json.loads(p.read_text(encoding='utf-8'))
        assert old['question_id'] == item['question_id']
        answer, status = guard_answer(old['draft'], item['source_count'])
        rows.append({'question_id':item['question_id'],'label':labels[item['question_id']],
                     'v1_status':old['guard_status'],'v2_status':status,
                     'v1_abstention':old['answer']==INSUFFICIENT_EVIDENCE,
                     'v2_abstention':answer==INSUFFICIENT_EVIDENCE,'v2_answer':answer,
                     'original_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    summary = {label: {'count':sum(r['label']==label for r in rows),
                       'v1_fixed_abstentions':sum(r['label']==label and r['v1_abstention'] for r in rows),
                       'v2_fixed_abstentions':sum(r['label']==label and r['v2_abstention'] for r in rows)}
               for label in ('answerable','unanswerable')}
    target.write_text(json.dumps({'summary':summary,'rows':rows,'model_calls':0,
        'guard_sha256':hashlib.sha256((ROOT/'backend/chat/answer_guard.py').read_bytes()).hexdigest(),
        'note':'Development replay; fixed abstention is not semantic accuracy.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))
    for r in rows:
        print(r['label'],r['v1_status'],'->',r['v2_status'])


if __name__ == '__main__':
    main()
