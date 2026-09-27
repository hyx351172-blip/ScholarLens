"""Apply an explicit user exclusion to existing results, without new model calls."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
EXCLUDED={'Q02','Q06','Q08','Q17','Q20'}


def partition(cases, excluded):
    ids=[c['id'] for c in cases]
    if len(ids)!=len(set(ids)) or not excluded.issubset(ids):
        raise ValueError('Duplicate cases or unknown excluded ID')
    return ([c for c in cases if c['id'] not in excluded],
            [c for c in cases if c['id'] in excluded])


def summarize(rows):
    a=[r for r in rows if r['label']=='answerable']
    u=[r for r in rows if r['label']=='unanswerable']
    return dict(count=len(rows), answerable=len(a), unanswerable=len(u),
        answerable_fixed_refusals=sum(r['fixed_abstention'] for r in a),
        unanswerable_fixed_refusals=sum(r['fixed_abstention'] for r in u),
        answerable_token_f1=sum(r['answer_token_f1'] for r in a)/len(a) if a else None,
        format_failures=sum(r['guard_status']=='invalid_structure' for r in rows))


def main():
    folder=ROOT/'docs/evaluation/semantic-review-v1'
    source=folder/'review.json'
    cases=json.loads(source.read_text(encoding='utf-8'))['cases']
    active,excluded=partition(cases,EXCLUDED)
    kept={c['question_id'] for c in active}
    result={'scope':'User-requested post-hoc development subset; not gold or held-out',
        'review_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'authorization':'用户请求：先排除这几道题（Q02、Q06、Q08、Q17、Q20）',
        'active_ids':[c['id'] for c in active], 'active_question_ids':sorted(kept),
        'excluded':[{'id':c['id'],'question_id':c['question_id'],'reason':c['dispute']} for c in excluded],
        'runs':{}}
    for run in ('qasper-guard-validation-v1','qasper-evidence-plan-v1','qasper-structured-v1'):
        path=ROOT/'output'/run/'scores.json'
        rows=json.loads(path.read_text(encoding='utf-8'))['rows']
        if len(rows)!=len(cases) or {r['question_id'] for r in rows}!={c['question_id'] for c in cases}:
            raise ValueError('Run does not contain exactly the original questions')
        selected=[r for r in rows if r['question_id'] in kept]
        assert len(selected)==len(active)
        result['runs'][run]={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'full':summarize(rows),'filtered':summarize(selected),'rows':selected}
    out=folder/'selection-v1.json'
    with out.open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
        f.write('\n')
    lines=['# 排除争议题后的开发集汇总','',
        '按用户要求排除 Q02、Q06、Q08、Q17、Q20；原始20题、标签、报告均保留。',
        '剩余15题：11道原标签可回答、4道原标签无答案，仍待人工语义确认。',
        '这是看过实验结果后的事后筛选，不是独立测试成绩，不可用于宣称泛化提升。','',
        '| 版本 | 可回答题固定拒答 | 无答案题固定拒答 | 可回答题token F1 | 格式校验失败 |',
        '| --- | --- | --- | --- | --- |']
    for name,run in result['runs'].items():
        s=run['filtered']
        lines.append(f"| {name} | {s['answerable_fixed_refusals']}/{s['answerable']} | {s['unanswerable_fixed_refusals']}/{s['unanswerable']} | {s['answerable_token_f1']:.4f} | {s['format_failures']} |")
    lines += ['', '固定拒答不是语义正确率，token F1不是事实准确率。结构化版本的拒答可能仅由格式失败造成。',
        '未重新调用模型；从三版已保存scores逐题重算，源文件哈希记录在selection-v1.json。',
        '本选择仅对本汇总生效；原始评分脚本默认仍统计完整20题，后续使用此子集须显式使用active_question_ids。','',
        '## 保留题号','',', '.join(result['active_ids']),'', '## 排除原因','']
    lines += [f"- {c['id']}：{c['dispute']}" for c in excluded]
    (folder/'FILTERED.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))


if __name__=='__main__':
    main()
