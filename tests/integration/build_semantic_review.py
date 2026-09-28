"""Build a human-review DRAFT from frozen local artifacts; never auto-approve."""
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/evaluation/semantic-review-v1'
# AI-authored review suggestions, not adjudicated labels. Index is pinned by input hash.
RUBRICS=[
 ('universal sentence encoder','域外预训练数据来源','区分USE训练数据与GloVe词向量初始化数据；原文不明确时应说明缺失。','不能以Common Crawl词向量数据替代USE数据。'),
 ('AMR summarization method','方法性能','原标签无答案，但S1/S36/S44含性能描述；先人工裁决可回答范围。','不得为追求标签一致而删去原文实际结果；不要臆造绝对分数。'),
 ('CJFA/CJFS','与SOTA的比较','区分与VAE基线的比较和与完整SOTA的比较。','基线胜出不自动意味着超过所有SOTA。'),
 ('FacTweet model','网络总层数','只接受原文明确的层数；模块名称不足以推导总层数。','不要把LSTM、attention、dropout数量相加。'),
 ('DSL datasets','语言名称列表','回答需给出具体语言名称；若文本只有数量，应指出名称缺失。','14种语言、6组不是语言名称列表。'),
 ('created dataset（需消歧）','数据规模','参考为真实会话语料353段会话、40位说话者；应说明与模拟训练集不同。','不能只回答100k或评估集大小；不得静默假定created仅指模拟集。'),
 ('car-speak','与物理属性的关系','抽象描述可以关联物理属性，但无法确定fast具体指马力还是外形；应保留歧义。','不能把fast唯一映射为马力；也不能只泛泛说与属性相关。'),
 ('template-based synthesis model','realistic的实验含义','参考为Yes，但措辞模糊；可说明实验支持的有效性及边界，需人审是否满足题意。','不得擅自增加部署/规模化要求，也不得把ROUGE提高等同所有现实属性成立。'),
 ('Gaussian-masked directional attention','工作机制','说明邻近字符、依距离确定的高斯权重和局部性；参考允许解释query/key/value映射。','仅复述标准点积注意力不足。'),
 ('irony generation','建模困难','涵盖隐晦难理解；部分参考还包括缺少既有研究与基线。','保留不同参考范围，不强行要求某一句逐字匹配。'),
 ('concept map','定义','带标签的图；概念为节点，概念关系为边。','不能只称其为摘要或目录。'),
 ('GlossBERT','是否及如何使用WordNet','是：利用目标词WordNet义项的gloss构造context-gloss对。','不要与BERT本身的预训练来源混淆。'),
 ('NCEL','整体效果','在实验范围内超过多个基线，并具较好的泛化能力。','不可扩张为所有数据集/所有方法均最优。'),
 ('McGurk effect','定义','视觉口型影响对听觉语音的感知；音频不必改变。','不能描述成仅改变音频产生错觉。'),
 ('speaker role','类别数及名称','两类：Anchors和Punctual speakers。','不要把定义角色的两个统计指标当作另外的类别。'),
 ('Wav2Text encoder and decoder','两端架构','encoder含卷积、NIN、双向LSTM；decoder为单向LSTM，可补充attention。','必须同时覆盖编码器与解码器，不可互换方向。'),
 ('experimental corpora','语料名称及角色','参考提及CoNLL2009英/德部分和Europarl EN-DE；区分Europarl平行句对与CoNLL训练部分。','不能把两者不加区别地宣称为同种平行语料。'),
 ('stance targets','俱乐部名称','Galatasaray和Fenerbahçe，允许重音符号的合理变体。','需覆盖两个目标，不可只给出国家或体育类型。'),
 ('WinoGrande previous SOTA','论文当时的模型','RoBERTa或基于RoBERTa的方法；时间范围为该论文。','不要按今天排行榜替换论文中的历史描述。'),
 ('privacy QA comparison systems','其他基线','参考变体含NA、Word Count、Human；另一变体还含SVM，应区分任务范围。','不要硬性只接受一种列表，也不要将所有实验混为同一任务。'),
]
DISPUTES={1:'原始无答案标签与正文性能描述冲突',5:'created指代及参考答案范围需确认',
          7:'realistic含义宽泛，不能强制二值化',16:'平行语料与实验语料角色需区分',19:'不同标注者列举的基线范围不同'}


def norm(text):
    return ' '.join(re.findall(r'\w+',unicodedata.normalize('NFKC',text).casefold()))


def map_evidence(texts,sources):
    return [{'text':text,'source_ids':[sid for sid,value in sources.items() if norm(value)==norm(text)]}
            for text in dict.fromkeys(texts)]


def require_approved(cases):
    if not cases:
        raise ValueError('Empty review is not approved')
    for case in cases:
        r=case.get('review',{})
        if (r.get('status')!='approved' or not isinstance(r.get('reviewer'),str)
            or not r['reviewer'].strip() or r.get('decision') not in
            ('answerable','unanswerable','ambiguous','label_conflict')):
            raise ValueError('Pending/unattributed review cannot be gold')


def main():
    base=ROOT/'output/qasper-guard-validation-v1'
    manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((base/'inputs.json').read_bytes()).hexdigest()=='47267de5d902a1db606f408421edab3ad11b6323c497a3e297fe3e0425cd399c'
    for name,digest in manifest['file_sha256'].items():
        assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest
    inputs=json.loads((base/'inputs.json').read_text(encoding='utf-8'))
    labels=json.loads((base/'labels.json').read_text(encoding='utf-8'))
    assert len(inputs)==len(labels)==len(RUBRICS)==20
    cases=[]
    runs=('qasper-guard-validation-v1','qasper-evidence-plan-v1','qasper-structured-v1')
    provenance={str((base/n).relative_to(ROOT)):hashlib.sha256((base/n).read_bytes()).hexdigest() for n in ('inputs.json','labels.json')}
    for i,(item,label,rubric) in enumerate(zip(inputs,labels,RUBRICS)):
        assert item['question_id']==label['question_id']
        sources=dict(re.findall(r'(?:^|\n\n)\[(S\d+)\] (.*?)(?=\n\n\[S\d+\] |\Z)',item['context'],re.S))
        outputs=[]
        evidence=map_evidence([e for r in label['references'] for e in r['evidence']],sources)
        # No evidence in a negative label is not proof of absence; provide full context link.
        for run in runs:
            path=ROOT/'output'/run/f'prediction-{i:02d}.json'
            p=json.loads(path.read_text(encoding='utf-8'))
            assert p['question_id']==item['question_id']
            provenance[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
            outputs.append({'run':run,'answer':p['answer'],'system_status':p['guard_status'],
                'judgment':{'target_correct':None,'attribute_answered':None,'evidence_supports':None,
                            'complete_enough':None,'refusal_appropriate':None,'error_tags':[],'notes':''}})
        cases.append({'id':f'Q{i+1:02d}','question_id':item['question_id'],'paper_id':item['paper_id'],
            'title':item['title'],'question':item['question'],'original_label':label['label'],
            'original_references':label['references'],'reference_evidence':evidence,
            'draft_rubric':dict(zip(('target','attribute','acceptable_answer','pitfalls'),rubric)),
            'dispute':DISPUTES.get(i),'context_file':f'contexts/Q{i+1:02d}.md',
            'review':{'status':'pending','reviewer':'','decision':None,'notes':''},'outputs':outputs})
    OUT.mkdir() # Never overwrite human edits.
    (OUT/'contexts').mkdir()
    for case,item in zip(cases,inputs):
        (OUT/case['context_file']).write_text('# '+item['title']+'\n\n'+item['context']+'\n',encoding='utf-8')
    (OUT/'review.json').write_text(json.dumps({'status':'AI_DRAFT_NOT_GOLD','cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    lines=['# 20题人工语义复核清单（AI草稿，尚未确认）','',
        '这是开发集，不是独立测试集。原始标签未改写；所有语义判断待你确认。',
        '先看题目、验收建议和原文，再展开三版回答；请在 review.json 填 review 和各输出的 judgment。',
        'priority：先复核 Q02、Q06、Q08、Q17、Q20 的争议；另重点看 Q01、Q05 的答非所问。','']
    for c in cases:
        r=c['draft_rubric']
        lines += [f"## {c['id']} · {c['question']}",'',f"论文：{c['title']}；原标签：{c['original_label']}",
            f"[完整上下文]({c['context_file']})",'',f"- 对象：{r['target']}",f"- 属性：{r['attribute']}",
            f"- 建议验收：{r['acceptable_answer']}",f"- 易错点：{r['pitfalls']}",
            f"- 争议：{c['dispute'] or '未预标；仍需独立检查'}",'- 人工确认：待复核','',
            '<details><summary>原始标注证据（无答案题没有证据，不代表全文已核查）</summary>','']
        for e in c['reference_evidence']:
            lines += [f"来源：{', '.join(e['source_ids']) or '未匹配'}",'',e['text'],'']
        lines += ['</details>','','<details><summary>三版回答（独立看完原文后再展开）</summary>','']
        for o in c['outputs']:
            lines += [f"### {o['run']}",'',f"程序状态：{o['system_status']}（不是正确性判定）",'',o['answer'],'']
        lines += ['</details>','']
    (OUT/'REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'Created {len(cases)} pending cases, {len(cases)*3} ungraded answers; {len(DISPUTES)} draft disputes. {OUT}')


if __name__=='__main__':
    main()
