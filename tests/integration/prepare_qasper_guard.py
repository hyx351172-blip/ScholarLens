"""Freeze a dev diagnostic; no model calls and no production writes."""
import hashlib
import argparse
import json
from pathlib import Path
import re
import unicodedata
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'backend/data/benchmarks/qasper/extracted/qasper-dev-v0.3.json'
OUT = ROOT / 'output/qasper-guard-dev-v1'
SEED = 'scholarlens-qasper-guard-v1'


def normalize(text):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', text).casefold()))


def paragraphs(paper):
    result = [paper['abstract']] if paper.get('abstract') else []
    for section in paper.get('full_text', []):
        result.extend(section.get('paragraphs', []))
    return [p for p in result if p.strip()]


def eligibility(qa, texts):
    answers = [a['answer'] for a in qa.get('answers', [])]
    if not answers:
        return None, 'no_annotations'
    flags = [a['unanswerable'] for a in answers]
    if any(flags) and not all(flags):
        return None, 'annotation_disagreement'
    if all(flags):
        return 'unanswerable', None
    known = {normalize(p) for p in texts}
    for a in answers:
        if not a['evidence'] or any('FLOAT SELECTED' in e for e in a['evidence']):
            return None, 'missing_or_visual_evidence'
        if any(normalize(e) not in known for e in a['evidence']):
            return None, 'evidence_not_mapped'
    return 'answerable', None


def prior_questions(paths):
    questions = set()
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'question', 'query'} and isinstance(child, str):
                    questions.add(normalize(child))
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    for path in paths:
        visit(json.loads(path.read_text(encoding='utf-8')))
    return questions


def select(data, prior, targets=None, excluded_papers=None, seed=SEED):
    targets = targets or {'answerable': 15, 'unanswerable': 5}
    pools = {key: [] for key in targets}
    excluded = Counter()
    for paper_id, paper in data.items():
        if paper_id in (excluded_papers or set()):
            excluded['prior_paper_overlap'] += len(paper['qas'])
            continue
        texts = paragraphs(paper)
        context = '\n\n'.join(f'[S{i}] {text}' for i, text in enumerate(texts, 1))
        for qa in paper['qas']:
            if not texts or len(context) > 60000:
                excluded['empty_or_over_60000_chars'] += 1
                continue
            if normalize(qa['question']) in prior:
                excluded['prior_question_overlap'] += 1
                continue
            label, reason = eligibility(qa, texts)
            if reason:
                excluded[reason] += 1
                continue
            rank = hashlib.sha256(f"{seed}:{paper_id}:{qa['question_id']}".encode()).hexdigest()
            pools[label].append((rank, paper_id, qa, context, texts))
    selected = []
    seen_papers, seen_questions = set(), set()
    # Scarcer stratum first; one question per paper for broader coverage.
    for label in ('unanswerable', 'answerable'):
        count = 0
        for _, paper_id, qa, context, texts in sorted(pools[label]):
            question = normalize(qa['question'])
            if paper_id in seen_papers or question in seen_questions:
                continue
            selected.append((label, paper_id, qa, context, texts))
            seen_papers.add(paper_id)
            seen_questions.add(question)
            count += 1
            if count == targets[label]:
                break
        if count != targets[label]:
            raise ValueError(f'Insufficient eligible unique papers for {label}: {count}')
    return selected, dict(excluded), {key: len(value) for key, value in pools.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=ROOT/'output/qasper-guard-dev-v1')
    parser.add_argument('--exclude-batch', type=Path)
    parser.add_argument('--seed', default=SEED)
    args = parser.parse_args()
    OUT = args.output_dir.resolve()
    if OUT.exists():
        raise RuntimeError('Refuse to overwrite frozen run directory')
    paths = list((ROOT / 'docs/evaluation').glob('*.json'))
    for directory in ('output/e2e-v1', 'output/answer-guard-live-v1', 'harness/runs'):
        paths.extend((ROOT / directory).rglob('*.json'))
    prior = prior_questions(paths)
    excluded_papers = set()
    excluded_batch_hash = None
    if args.exclude_batch:
        previous = args.exclude_batch / 'inputs.json'
        old = json.loads(previous.read_text(encoding='utf-8'))
        excluded_papers = {x['paper_id'] for x in old}
        prior.update(normalize(x['question']) for x in old)
        excluded_batch_hash = hashlib.sha256(previous.read_bytes()).hexdigest()
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    selected, exclusions, eligible = select(data, prior, excluded_papers=excluded_papers, seed=args.seed)
    inputs, labels = [], []
    for label, paper_id, qa, context, texts in selected:
        inputs.append({'question_id': qa['question_id'], 'paper_id': paper_id,
                       'title': data[paper_id]['title'], 'question': qa['question'],
                       'context': context, 'source_count': len(texts)})
        labels.append({'question_id': qa['question_id'], 'paper_id': paper_id,
                       'label': label, 'references': [a['answer'] for a in qa['answers']]})
    OUT.mkdir(parents=True)
    for name, value in [('inputs.json', inputs), ('labels.json', labels)]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    manifest = {'split': 'dev', 'seed': args.seed, 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                'excluded_papers': sorted(excluded_papers), 'excluded_batch_input_sha256': excluded_batch_hash,
                'guard_sha256': hashlib.sha256((ROOT/'backend/chat/answer_guard.py').read_bytes()).hexdigest(),
                'selection': '15 answerable + 5 unanswerable; 20 distinct papers; no truncation',
                'eligible': eligible, 'exclusions': exclusions, 'prior_unique_questions': len(prior),
                'overlap_scope': [str(p.relative_to(ROOT)) for p in paths],
                'file_sha256': {name: hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('inputs.json','labels.json')},
                'selected': [{'question_id': x['question_id'], 'paper_id': x['paper_id'], 'context_chars': len(x['context'])} for x in inputs],
                'limits': 'Exact normalized question overlap only; not semantic/paper contamination proof. Full-text answer-layer diagnostic, not PDF/RAG end-to-end.'}
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('overlap_scope','selected')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
