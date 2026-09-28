"""Offline diagnostics; scoring may read labels, generation must not."""
import importlib.util
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=ROOT/'output/qasper-guard-dev-v1')
    out = parser.parse_args().output_dir.resolve()
    inputs = json.loads((out/'inputs.json').read_text(encoding='utf-8'))
    labels = {x['question_id']:x for x in json.loads((out/'labels.json').read_text(encoding='utf-8'))}
    spec = importlib.util.spec_from_file_location('qasper_eval', ROOT/'backend/data/benchmarks/qasper/extracted/qasper_evaluator.py')
    official = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(official)
    rows = []
    for i,item in enumerate(inputs):
        path = out/f'prediction-{i:02d}.json'
        if not path.exists():
            raise ValueError(f'Missing prediction {i}; refuse partial aggregate')
        r = json.loads(path.read_text(encoding='utf-8'))
        assert r['question_id'] == item['question_id']
        label = labels[item['question_id']]
        refs = official.get_answers_and_evidence({'paper':{'qas':[{'question_id':r['question_id'],'answers':[{'answer':a} for a in label['references']]}]}}, True)[r['question_id']]
        scores = {}
        for variant in ('draft','answer'):
            text = r[variant]
            clean = 'Unanswerable' if text == INSUFFICIENT_EVIDENCE else re.sub(r'\[S[^\]]*\]','',text).strip()
            scores[variant+'_token_f1'] = max(official.token_f1_score(clean,ref['answer']) for ref in refs)
        rows.append({'question_id':r['question_id'],'paper_id':r['paper_id'],'label':label['label'],
                     'question':item['question'],'guard_status':r['guard_status'],
                     'changed':r['draft']!=r['answer'],'fixed_abstention':r['answer']==INSUFFICIENT_EVIDENCE,
                     'seconds':r['seconds'],'finish_reason':r['finish_reason'], **scores})
    answerable = [r for r in rows if r['label']=='answerable']
    unanswerable = [r for r in rows if r['label']=='unanswerable']
    summary = {'count':len(rows),'papers':len({r['paper_id'] for r in rows}),
               'answerable_count':len(answerable),'unanswerable_count':len(unanswerable),
               'answerable_fixed_abstentions':sum(r['fixed_abstention'] for r in answerable),
               'unanswerable_fixed_abstentions':sum(r['fixed_abstention'] for r in unanswerable),
               'mean_seconds':sum(r['seconds'] for r in rows)/len(rows),
               'truncated_generations':sum(r['finish_reason']=='length' for r in rows),
               'answerable_draft_token_f1':sum(r['draft_token_f1'] for r in answerable)/len(answerable),
               'answerable_guarded_token_f1':sum(r['answer_token_f1'] for r in answerable)/len(answerable),
               'note':'Fixed-abstention counts are NOT semantic refusal accuracy. Token F1 uses official function, not official full-split benchmark; citations stripped; no evidence F1/entailment evaluation.'}
    report = {'summary':summary,'rows':rows}
    (out/'scores.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    for r in rows:
        print(r['label'],r['guard_status'],r['question'])


if __name__ == '__main__':
    main()
