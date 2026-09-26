"""Explicit opt-in live API journey; never runs during unittest discovery.

Creates one isolated KB. Does not remove existing data or change application code.
Uses configured embedding/LLM APIs. Does not persist credentials or config response.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import requests

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/e2e-v1'
PDF=ROOT/'output/uploads/2026/09/24/file_20260924_587e8199_1706.03762_attention-is-all-you-need.pdf'
FILENAME='1706.03762_attention-is-all-you-need.pdf'
QUESTIONS=[
    ('method','这篇 Attention Is All You Need 论文提出了什么方法？'),
    ('table','Attention Is All You Need 的表 2 中，Transformer big 在 WMT 2014 英德和英法翻译上的 BLEU 分别是多少？'),
    ('conclusion','这篇 Attention Is All You Need 论文的结论是什么？'),
    ('unanswerable','Attention Is All You Need 论文报告的 GPT-4 在 MMLU 上的准确率是多少？没有证据请明确说明。'),
]


def save(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def api(port,path,method='get',**kwargs):
    r=requests.request(method,f'http://127.0.0.1:{port}{path}',timeout=kwargs.pop('timeout',30),**kwargs)
    r.raise_for_status();return r.json()


def check_ingestion(data,documents,details,pdf_match):
    stages={s:data.get(s,{}).get('status')=='completed' for s in ('extraction','chunking','storage')}
    counts=[data.get('chunking',{}).get('total_chunks'),documents.get('total_chunks'),details.get('total_chunks')]
    return {'stages':stages,'listed_documents':documents.get('total_documents'),
        'chunk_counts':counts,'pdf_bytes_match':pdf_match,
        'passed':all(stages.values()) and documents.get('total_documents')==1 and
            isinstance(counts[0],int) and counts[0]>0 and len(set(counts))==1 and pdf_match}


def check_answer(response,file_id,pages,answerable):
    sources=response.get('sources') or [];answer=response.get('answer','')
    ids=set(re.findall(r'\[(S\d+)\]',answer));known={s.get('source_id') for s in sources}
    malformed=[m for m in re.findall(r'\[S[^\]\n]*\]',answer) if not re.fullmatch(r'\[S\d+\]',m)]
    provenance=[]
    for s in sources:
        m=s.get('metadata') or {};start=m.get('page_start');end=m.get('page_end',start)
        provenance.append(s.get('file_id')==file_id and bool(s.get('chunk_text')) and
            isinstance(start,int) and isinstance(end,int) and 1<=start<=end<=pages)
    result={'success':response.get('success',False),'nonempty_answer':bool(answer.strip()),
        'cited_ids':sorted(ids),'unknown_citations':sorted(ids-known),
        'malformed_citations':malformed,
        'all_sources_target_file':all(s.get('file_id')==file_id for s in sources),
        'valid_source_provenance':all(provenance),'source_count':len(sources)}
    result['contract_passed']=bool(result['success'] and result['nonempty_answer'] and not malformed and not result['unknown_citations'] and
        result['valid_source_provenance'] and (not answerable or bool(sources) and bool(ids)))
    return result


def upload():
    if (OUT/'upload.json').exists() or (OUT/'collection.json').exists():raise ValueError('Refuse duplicate upload/run')
    health={str(p):api(p,'/health') for p in (8000,8001,8006,8501)};save('health.json',health)
    before=api(8000,'/knowledge_base/list');save('collections-before.json',before)
    kb=api(8000,'/knowledge_base/create','post',params={'display_name':'E2E-v1-20260925-isolated'})
    save('collection.json',kb)
    if kb.get('status')!='success':raise RuntimeError('KB creation failed')
    start=time.monotonic()
    with PDF.open('rb') as f:
        response=api(8006,'/api/v1/files/upload','post',timeout=900,
            files={'file':(FILENAME,f,'application/pdf')},data={
                'knowledge_base_id':kb['collection_id'],'auto_extract':'true',
                'extraction_mode':'docling','auto_chunk':'true','enable_vlm_repair':'false',
                'chunking_method':'header_recursive','chunk_size':'1500','chunk_overlap':'200','max_page_span':'3'})
    save('upload.json',{'response':response,'elapsed_seconds':time.monotonic()-start,
        'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest()})
    print(json.dumps(response,ensure_ascii=False),flush=True)


def verify_and_chat():
    upload= json.loads((OUT/'upload.json').read_text(encoding='utf-8'))['response']
    if not upload.get('success'):raise RuntimeError('Upload failed; refusing to claim downstream journey')
    data=upload['data'];file_id=data['file_id'];kb=json.loads((OUT/'collection.json').read_text(encoding='utf-8'))['collection_id']
    stages={s:data.get(s,{}).get('status')=='completed' for s in ('extraction','chunking','storage')}
    if not all(stages.values()):raise RuntimeError('Requested upload stage incomplete')
    documents=api(8000,f'/knowledge_base/{kb}/documents');save('documents.json',documents)
    details=api(8000,f'/document/{file_id}/details');save('details.json',details)
    pdf_response=requests.get(f'http://127.0.0.1:8000/document/{file_id}/pdf',timeout=30);pdf_response.raise_for_status()
    save('ingestion-checks.json',check_ingestion(data,documents,details,
        hashlib.sha256(pdf_response.content).hexdigest()==hashlib.sha256(PDF.read_bytes()).hexdigest()))
    # The existing local API returns credentials; consume only in memory.
    config=api(8501,'/config/default')['config']['llm']
    config.update(temperature=0,max_tokens=1000)
    for case,query in QUESTIONS:
        path=OUT/f'answer-{case}.json'
        if path.exists():continue
        started=time.monotonic()
        response=api(8501,'/chat','post',timeout=180,json={'query':query,'collection_name':kb,
            'llm_config':config,'top_k':10,'score_threshold':.1,'use_multi_query':True,
            'use_reranker':False,'stream':False,'return_source':True})
        checks=check_answer(response,file_id,data['extraction']['total_pages'],case!='unanswerable')
        save(path.name,{'query':query,'response':response,'checks':checks,'elapsed_seconds':time.monotonic()-started})
        print(case,json.dumps(checks,ensure_ascii=False),flush=True)


def audit_saved():
    """No new paid requests; strengthen checks against immutable responses."""
    def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
    upload=read('upload.json')['response']['data'];details=read('details.json')
    chunks={c['chunk_id']:c for c in details['chunks']};rows=[]
    for case,_ in QUESTIONS:
        raw=read(f'answer-{case}.json');response=raw['response']
        checks=check_answer(response,upload['file_id'],upload['extraction']['total_pages'],case!='unanswerable')
        joins=[]
        for s in response.get('sources') or []:
            c=chunks.get(s['metadata'].get('chunk_id'))
            # Actual API evidence contract is retrieval_text (includes title/section), not text.
            joins.append(bool(c and c['retrieval_text']==s['chunk_text'] and
                c['page_start']==s['metadata'].get('page_start') and c['page_end']==s['metadata'].get('page_end')))
        row={'case':case,'checks':checks,'source_chunk_exact_join':all(joins),'source_count':len(joins),
            'seconds':raw['elapsed_seconds']}
        if case=='table':
            row['expected_numbers_in_answer']=all(x in response['answer'] for x in ('28.4','41.8'))
            row['table_2_page_8_retrieved']=any(s['metadata'].get('table_identifier')=='2' and s['metadata'].get('page_start')==8 for s in response['sources'])
        if case=='unanswerable':
            row['answer_mentions_2023']='2023' in response['answer']
            row['retrieved_evidence_mentions_2023']=any('2023' in s['chunk_text'] for s in response['sources'])
            row['manual_review']='Declines numeric accuracy but adds unsupported release-date explanation; grounding FAIL.'
        rows.append(row)
    save('audit.json',{'ingestion':read('ingestion-checks.json'),'results':rows,
        'raw_artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('answer-*.json')},
        'raw_answers_unchanged':True,'additional_model_calls':0,
        'note':'Structural validity is not claim entailment; manual semantic review remains necessary.'})
    print(json.dumps(rows,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['upload','chat','audit']);args=p.parse_args()
    {'upload':upload,'chat':verify_and_chat,'audit':audit_saved}[args.stage]()
