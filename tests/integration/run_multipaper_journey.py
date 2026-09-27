"""Opt-in real upload->index->retrieve->answer->source audit, isolated test KBs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import requests

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/e2e-multipaper-v1'
PAPERS={'attention':'1706.03762_attention-is-all-you-need.pdf','bert':'1810.04805_bert.pdf','lora':'2106.09685_lora.pdf'}
CASES=[
 ('A01',['attention'],'Attention Is All You Need 论文提出什么模型？其核心架构是什么？','Transformer; encoder-decoder; attention replacing recurrence/convolution',True),
 ('A02',['attention'],'Attention Is All You Need 表2中 Transformer big 的 EN-DE 和 EN-FR BLEU 分别是多少？','table 2 p8: 28.4 / 41.8 (not prose 41.0)',True),
 ('A03',['attention'],'Attention Is All You Need 的缩放点积注意力公式是什么，为什么要除以根号 d_k？','softmax(QK^T/sqrt(d_k))V; large dot products drive softmax small gradients; pp4-5',True),
 ('A04',['attention'],'仅依据 Attention Is All You Need：论文报告的 GPT-4 在 MMLU 上的准确率是多少？','no evidence; no external background additions',False),
 ('B01',['bert'],'BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding 使用哪两个预训练任务？','masked LM and next sentence prediction; p4',True),
 ('B02',['bert'],'BERT 论文中的 BERT BASE 和 BERT LARGE 的层数、隐藏维度、注意力头数和参数量分别是多少？','BASE 12/768/12/110M; LARGE 24/1024/16/340M; p3',True),
 ('B03',['bert'],'BERT 的 MLM 选取多少比例的 token？选中后 MASK、随机替换、保持不变各占多少？','15%; conditional 80%/10%/10%; p4',True),
 ('B04',['bert'],'仅依据 BERT 论文：BERT 在 GPT-4 发布后的 MMLU 对比实验中取得多少分？','no evidence; do not infer scores or release dates',False),
 ('L01',['lora'],'LoRA: Low-Rank Adaptation of Large Language Models 的核心方法是什么？冻结与训练哪些参数？','freeze pretrained weights; train low-rank A and B; pp1,4',True),
 ('L02',['lora'],'LoRA 摘要中，相比使用 Adam 全量微调 GPT-3 175B，可训练参数量和 GPU 显存需求分别减少多少倍？','10000 times trainable parameters; 3 times GPU memory; p1',True),
 ('L03',['lora'],'LoRA 论文式(3)如何改写前向传播？A、B如何初始化？','h=W0x+BAx; A Gaussian, B zero; p4',True),
 ('L04',['lora'],'仅依据 LoRA 论文：其在 Llama 3 70B 上的 MMLU 分数是多少？','not reported; no invented number',False),
 ('X01',['attention','bert'],'比较 Attention Is All You Need 与 BERT 的模型架构：前者是否包含编码器和解码器，后者采用什么结构？','Attention encoder-decoder vs BERT bidirectional encoder; cite both',True),
 ('X02',['bert','lora'],'比较 BERT 与 LoRA：下游任务适配时，哪些参数更新，哪些参数冻结？请分别引用两篇论文。','BERT fine-tunes all parameters; LoRA freezes W0, trains A/B; cite both',True),
 ('H01',['lora'],'现在切换到 LoRA 论文：低秩更新中的 A、B 分别如何初始化？不要回答上一轮 BERT 的配置。','A Gaussian B zero; history from B02 must not contaminate',True),
 ('E01',[],'请总结这个知识库里论文的主要方法。','empty KB must abstain with no sources',False),
]


def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))


def save(name,value):
    with (OUT/name).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')


def api(port,path,method='GET',**kwargs):
    with requests.Session() as session:
        session.trust_env=False
        r=session.request(method,f'http://127.0.0.1:{port}{path}',timeout=kwargs.pop('timeout',30),**kwargs)
        r.raise_for_status()
        return r if kwargs.get('stream') else r.json()


def check_response(response,details,allowed,answerable):
    answer=response.get('answer') or '';sources=response.get('sources') or []
    ids=set(re.findall(r'\[(S[1-9]\d*)\]',answer))
    known={s.get('source_id') for s in sources}
    residue=re.sub(r'\[S[1-9]\d*\]','',answer)
    malformed=bool(re.search(r'[\[［【]\s*[SsＳｓ]',residue))
    joins=[]
    for s in sources:
        meta=s.get('metadata') or {};d=details.get(s.get('file_id'),{})
        c=d.get('chunks',{}).get(meta.get('chunk_id'));start=meta.get('page_start');end=meta.get('page_end')
        joins.append(bool(c and s.get('file_id') in allowed and c.get('retrieval_text')==s.get('chunk_text')
            and c.get('page_start')==start and c.get('page_end')==end
            and isinstance(start,int) and isinstance(end,int) and 1<=start<=end<=d['pages']))
    cited_files={s.get('file_id') for s in sources if s.get('source_id') in ids}
    valid=bool(response.get('success') and answer.strip() and not malformed and not(ids-known) and all(joins)
        and (not answerable or bool(ids) and bool(sources)))
    return dict(contract_passed=valid,cited_ids=sorted(ids),unknown_citations=sorted(ids-known),
        malformed=malformed,source_count=len(sources),exact_source_joins=joins,cited_files=sorted(cited_files),
        cross_paper_coverage=(allowed<=cited_files) if answerable else None,
        fixed_refusal=answer=='当前检索证据不足，无法可靠回答该问题。请补充相关文献或缩小问题范围。')


def prepare():
    inventory=read('pdf-inventory.json')
    print('Checking service health',flush=True)
    health={str(p):api(p,'/health') for p in (8000,8001,8006,8502)}
    print('Recording existing KB inventory',flush=True)
    before=api(8000,'/knowledge_base/list')
    print('Hashing application code only',flush=True)
    names=subprocess.check_output(['git','ls-files','--','backend/**/*.py'],cwd=ROOT,text=True,timeout=30).splitlines()
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    save('manifest.json',dict(scope='multi-paper development E2E, not held-out',papers=inventory,cases=CASES,
         code_sha256=hashes,chat_port=8502,health=health,
         git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
         retrieval=dict(top_k=10,score_threshold=.1,use_multi_query=True,use_reranker=False),
         extraction=dict(mode='docling',enable_vlm_repair=False),model_call_limit='16 Chat requests, plus internal planner/embedding calls; no paid judge'))
    save('collections-before.json',before)
    for role in ('mixed','empty'):
        kb=api(8000,'/knowledge_base/create','POST',params={'display_name':f'E2E-multipaper-v1-{role}-20260926'})
        save(f'collection-{role}.json',kb)
        if kb.get('status')!='success':
            raise RuntimeError('KB creation failed')
    print('Prepared 3 papers, 16 cases, 2 isolated KBs',flush=True)


def upload():
    kb=read('collection-mixed.json')['collection_id']
    inventory={p['filename']:p for p in read('pdf-inventory.json')}
    for key,name in PAPERS.items():
        if (OUT/f'upload-{key}.json').exists():
            continue
        if (OUT/f'upload-attempt-{key}.json').exists():
            raise RuntimeError('Uncertain upload attempt: inspect server before retrying')
        p=inventory[name];path=Path(p['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==p['sha256']
        save(f'upload-attempt-{key}.json',dict(filename=name,collection=kb,started=time.time()))
        print('Uploading',key,flush=True);start=time.monotonic()
        with path.open('rb') as f:
            response=api(8006,'/api/v1/files/upload','POST',timeout=1200,
                files={'file':(name,f,'application/pdf')},data=dict(knowledge_base_id=kb,auto_extract='true',
                extraction_mode='docling',auto_chunk='true',enable_vlm_repair='false',
                chunking_method='header_recursive',chunk_size='1500',chunk_overlap='200',max_page_span='3'))
        save(f'upload-{key}.json',dict(response=response,seconds=time.monotonic()-start))
        data=response.get('data') or {}
        print(key,{s:data.get(s,{}).get('status') for s in ('extraction','chunking','storage')},flush=True)
    verify()


def verify():
    kb=read('collection-mixed.json')['collection_id'];documents=api(8000,f'/knowledge_base/{kb}/documents')
    save('documents.json',documents);rows=[]
    for key,name in PAPERS.items():
        p=next(p for p in read('pdf-inventory.json') if p['filename']==name)
        raw=read(f'upload-{key}.json');data=raw['response'].get('data') or {};fid=data.get('file_id')
        if not fid:
            rows.append(dict(paper=key,passed=False,reason='no file_id'));continue
        details=api(8000,f'/document/{fid}/details');save(f'details-{key}.json',details)
        with requests.Session() as session:
            session.trust_env=False
            r=session.get(f'http://127.0.0.1:8000/document/{fid}/pdf',timeout=30);r.raise_for_status()
        count=data.get('chunking',{}).get('total_chunks')
        checks=dict(stages=all(data.get(s,{}).get('status')=='completed' for s in ('extraction','chunking','storage')),
            pages_match=data.get('extraction',{}).get('total_pages')==p['pages'],
            counts_match=isinstance(count,int) and count>0 and count==data.get('storage',{}).get('inserted_count')==details.get('total_chunks')==len(details.get('chunks',[])),
            pdf_hash_match=hashlib.sha256(r.content).hexdigest()==p['sha256'])
        rows.append(dict(paper=key,file_id=fid,pages=p['pages'],chunks=count,checks=checks,passed=all(checks.values()),seconds=raw['seconds']))
    save('ingestion.json',dict(rows=rows,listed_documents=documents.get('total_documents'),listed_chunks=documents.get('total_chunks'),
        passed=all(r['passed'] for r in rows) and documents.get('total_documents')==3 and documents.get('total_chunks')==sum(r.get('chunks') or 0 for r in rows)))
    print(json.dumps(read('ingestion.json'),ensure_ascii=False),flush=True)


def chat():
    ingestion=read('ingestion.json')
    if not ingestion['passed']:
        raise RuntimeError('Ingestion failed; downstream run not claimed')
    details={};files={}
    for row in ingestion['rows']:
        files[row['paper']]=row['file_id']
        details[row['file_id']]={'pages':row['pages'],'chunks':{c['chunk_id']:c for c in read(f"details-{row['paper']}.json")['chunks']}}
    config=api(8502,'/config/default')['config']['llm'];config.update(temperature=0,max_tokens=1000)
    save('run-settings.json',dict(model=config['model_name'],temperature=0,max_tokens=1000))
    for cid,targets,query,expected,answerable in CASES:
        if (OUT/f'answer-{cid}.json').exists():
            continue
        if (OUT/f'chat-attempt-{cid}.json').exists():
            raise RuntimeError('Uncertain Chat attempt; no automatic repeat')
        kb=read('collection-empty.json' if cid=='E01' else 'collection-mixed.json')['collection_id']
        history=[]
        if cid=='H01':
            prior=read('answer-B02.json')
            history=[dict(role='user',content=prior['query']),dict(role='assistant',content=prior['response']['answer'])]
        save(f'chat-attempt-{cid}.json',dict(query=query,started=time.time()))
        start=time.monotonic()
        try:
            response=api(8502,'/chat','POST',timeout=240,json=dict(query=query,collection_name=kb,llm_config=config,
                top_k=10,score_threshold=.1,use_multi_query=True,use_reranker=False,stream=False,return_source=True,history=history))
            checks=check_response(response,details,{files[t] for t in targets},answerable)
            save(f'answer-{cid}.json',dict(query=query,response=response,checks=checks,seconds=time.monotonic()-start))
            print(cid,json.dumps(checks,ensure_ascii=False),flush=True)
        except requests.RequestException as exc:
            save(f'answer-{cid}.json',dict(query=query,error_type=type(exc).__name__,seconds=time.monotonic()-start))
            print(cid,type(exc).__name__,flush=True)
    save('collections-after.json',api(8000,'/knowledge_base/list'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','upload','chat']);args=p.parse_args()
    globals()[args.stage]()
