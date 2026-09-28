"""Paired development comparison: preserve all examples, no selective scoring."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    base = ROOT/'output/qasper-guard-validation-v1'
    out = ROOT/'output/qasper-evidence-plan-v1'
    old = json.loads((base/'scores.json').read_text(encoding='utf-8'))
    new = json.loads((out/'scores.json').read_text(encoding='utf-8'))
    assert len(old['rows']) == len(new['rows']) == 20
    changes, totals = [], {'prompt_tokens':0, 'completion_tokens':0, 'total_tokens':0}
    empty_plans = truncated_plans = 0
    for i, (a, b) in enumerate(zip(old['rows'], new['rows'])):
        assert a['question_id'] == b['question_id']
        prediction = json.loads((out/f'prediction-{i:02d}.json').read_text(encoding='utf-8'))
        planning = prediction['planning']
        empty_plans += not bool(planning['validated'])
        truncated_plans += planning['finish_reason'] == 'length'
        for usage in (planning['usage'], prediction['usage']):
            for key in totals:
                totals[key] += usage[key]
        changes.append({'index':i, 'question':a['question'], 'label':a['label'],
                        'baseline_refusal':a['fixed_abstention'], 'planned_refusal':b['fixed_abstention'],
                        'baseline_f1':a['answer_token_f1'], 'planned_f1':b['answer_token_f1']})
    report = {'baseline': old['summary'], 'experiment': new['summary'], 'total_usage':totals,
              'empty_validated_plans': empty_plans, 'truncated_plans':truncated_plans, 'rows':changes}
    (out/'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'rows'}, ensure_ascii=False, indent=2))
    for row in changes:
        if row['baseline_refusal'] != row['planned_refusal']:
            print(json.dumps(row, ensure_ascii=False))


if __name__ == '__main__':
    main()
