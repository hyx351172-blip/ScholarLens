"""Offline SciFact dev adapter/scorer. No model calls or credential loading."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat.claim_bound_answer import build_catalog
from backend.chat.selected_claim_support import prepare_review, parse_decision
from tests.integration.run_selected_claim_support_live import request_for, value_hash, verify, write
from tests.integration.prepare_selected_claim_support import read, digest

DATA = ROOT / 'backend/data/benchmarks/scifact/extracted/data'
OUT = ROOT / 'output/scifact-verifier-v1'
HISTORY = ROOT / 'output/selected-claim-support-live-v1'
LABELS = ('SUPPORT', 'CONTRADICT', 'NOT_ENOUGH_INFO')
SEED = 'scholarlens-scifact-dev-smoke-v1'
QUESTION = 'Does the supplied abstract support the stated scientific claim?'
PROTOCOL = dict(version='scifact_verifier_v1', split='dev', evidence_mode='fixed_v1',
                context='complete_candidate_abstract', max_selected_anchors=8,
                sampling='sha256_rare_class_first_unique_claim_text_and_document', seed=SEED,
                model='qwen3-vl-plus', max_tokens=1000, temperature=0, max_retries=0,
                deadline_seconds=60, external_calls_authorized=False,
                official_scifact_score=False, retrieval_evaluated=False, rationale_selection_evaluated=False)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _positive_id(value):
    return type(value) is int and value > 0


def _normalize(text):
    return ' '.join(text.casefold().split())


def validate_data(claims, corpus):
    """Validate annotations before filtering for the existing transport contract."""
    docs, seen = {}, set()
    _require(isinstance(claims, list) and isinstance(corpus, list), 'invalid_dataset')
    for doc in corpus:
        _require(isinstance(doc, dict) and _positive_id(doc.get('doc_id')), 'invalid_doc_id')
        did = doc['doc_id']
        _require(did not in docs, 'duplicate_doc_id')
        abstract = doc.get('abstract')
        _require(isinstance(doc.get('title'), str) and isinstance(abstract, list) and abstract
                 and all(isinstance(s, str) and s.strip() for s in abstract), 'invalid_abstract')
        docs[did] = doc
    for claim in claims:
        _require(isinstance(claim, dict) and _positive_id(claim.get('id')), 'invalid_claim_id')
        _require(claim['id'] not in seen, 'duplicate_claim_id')
        seen.add(claim['id'])
        _require(isinstance(claim.get('claim'), str) and claim['claim'].strip(), 'invalid_claim_text')
        evidence, cited = claim.get('evidence'), claim.get('cited_doc_ids')
        _require(isinstance(evidence, dict), 'unlabeled_or_invalid_claim')
        _require(isinstance(cited, list) and cited and all(_positive_id(i) for i in cited)
                 and all(i in docs for i in cited), 'invalid_cited_docs')
        for did, rationales in evidence.items():
            _require(isinstance(did, str) and did.isdecimal() and str(int(did)) == did and int(did) in docs,
                     'missing_evidence_document')
            _require(isinstance(rationales, list) and rationales, 'invalid_rationales')
            labels = set()
            for rationale in rationales:
                _require(isinstance(rationale, dict) and rationale.get('label') in LABELS[:2], 'invalid_label')
                labels.add(rationale['label'])
                indices = rationale.get('sentences')
                _require(isinstance(indices, list) and indices
                         and all(type(i) is int and 0 <= i < len(docs[int(did)]['abstract']) for i in indices)
                         and len(indices) == len(set(indices)), 'invalid_rationale_indices')
            _require(len(labels) == 1, 'conflicting_document_labels')
    return docs


def _packet(claim, doc):
    text = '\n'.join(doc['abstract'])
    documents = [dict(source_id='S1', filename=f"scifact-{doc['doc_id']}.abstract", chunk_text=text)]
    if len(text) > 120000:
        return None, 'abstract_exceeds_eight_anchors'
    catalog = build_catalog(documents)
    if len(catalog) > 8:
        return None, 'abstract_exceeds_eight_anchors'
    raw = json.dumps(dict(status='answered', claims=[dict(text=claim['claim'],
                         evidence_ids=[a['anchor_id'] for a in catalog])]), ensure_ascii=False)
    plan = prepare_review(QUESTION, documents, raw, evidence_mode='fixed_v1')
    if plan['status'] != 'claim_bound_passed':
        return None, 'claim_contract_rejected'
    packet = plan['packets'][0]
    _require(''.join(a['text'] for a in packet['selected_anchors']) == text, 'abstract_truncated')
    _require(packet['claim'] == claim['claim'], 'claim_changed')
    return packet, None


def build_bundle(claims, corpus, *, per_class=10, seed=SEED):
    _require(type(per_class) is int and 1 <= per_class <= 100, 'invalid_sample_budget')
    _require(isinstance(seed, str) and seed, 'invalid_seed')
    docs = validate_data(claims, corpus)
    eligible, excluded, warnings, pair_counts = [], [], [], Counter()
    for claim in sorted(claims, key=lambda c: c['id']):
        evidence = claim['evidence']
        if len(claim['cited_doc_ids']) != len(set(claim['cited_doc_ids'])):
            warnings.append(dict(claim_id=claim['id'], reason='duplicate_cited_document_ids',
                                 original=claim['cited_doc_ids'], unique=sorted(set(claim['cited_doc_ids']))))
        # Unannotated neighbors of positive claims are deliberately not used as negatives.
        document_ids = sorted(int(i) for i in evidence) if evidence else sorted(set(claim['cited_doc_ids']))
        for did in document_ids:
            rationales = evidence.get(str(did), [])
            label = rationales[0]['label'] if rationales else 'NOT_ENOUGH_INFO'
            pair_counts[label] += 1
            packet, reason = _packet(claim, docs[did])
            identity = dict(key=f"SF-{claim['id']}-{did}", claim_id=claim['id'], doc_id=did, label=label)
            if reason:
                excluded.append(dict(identity, reason=reason))
                continue
            eligible.append(dict(identity, packet=packet, rationale_sets=[list(r['sentences']) for r in rationales],
                                 title=docs[did]['title']))

    def order(row, purpose):
        return hashlib.sha256(f"{seed}:{purpose}:{row['key']}".encode('utf-8')).hexdigest()

    counts = Counter(r['label'] for r in eligible)
    selected, used_claims, used_text, used_docs, skipped = [], set(), set(), set(), []
    for label in sorted(LABELS, key=lambda name: (counts[name], name)):
        group = sorted((r for r in eligible if r['label'] == label), key=lambda r: order(r, 'sample'))
        chosen = 0
        for row in group:
            if chosen == per_class:
                break
            text = _normalize(row['packet']['claim'])
            if row['claim_id'] in used_claims or row['doc_id'] in used_docs or text in used_text:
                skipped.append(dict(key=row['key'], reason='duplicate_claim_text_or_document'))
                continue
            selected.append(row)
            used_claims.add(row['claim_id']); used_docs.add(row['doc_id']); used_text.add(text)
            chosen += 1
        _require(chosen == per_class, f'insufficient_unique_eligible_pairs:{label}')
    selected.sort(key=lambda r: order(r, 'presentation'))
    entries, gold = [], []
    for row in selected:
        entries.append(dict(key=row['key'], packet=row['packet']))
        gold.append(dict(key=row['key'], claim_id=row['claim_id'], doc_id=row['doc_id'], label=row['label'],
                         title=row['title'], rationale_sets=row['rationale_sets'],
                         label_source='SciFact dev annotation; NEI inferred from empty evidence and cited candidate',
                         human_verdict=None, human_note=None))
    chosen_keys = {r['key'] for r in selected}
    summary = dict(experiment='scifact-verifier-v1', status='prepared_not_run', split='dev',
                   claims_in_split=len(claims), corpus_documents=len(corpus), selected_pairs=len(selected),
                   label_counts={label: per_class for label in LABELS},
                   unique_claims=len(used_claims), unique_documents=len(used_docs),
                   anchor_count_distribution=dict(sorted(Counter(len(e['packet']['selected_anchors']) for e in entries).items())),
                   selected_abstract_characters=sum(sum(len(a['text']) for a in e['packet']['selected_anchors']) for e in entries),
                   total_prompt_characters=sum(len(m['content']) for e in entries for m in request_for(e['packet'])['messages']),
                   provider_calls=0, accuracy=None, human_review_status='dataset_labels_not_project_reverified',
                   limitations=['balanced dev smoke subset', 'oracle candidate abstracts, no retrieval or PDF parsing',
                                'full abstract and fixed_v1 differ from previous sentence-selected claim experiment',
                                'long abstracts and incompatible claims excluded before sampling',
                                'public dataset may have appeared in model pretraining',
                                'not official rationale/abstract retrieval score or overall RAG accuracy'])
    return dict(entries=entries, gold=gold,
                audit=dict(candidate_pairs=sum(pair_counts.values()), candidate_label_counts=dict(sorted(pair_counts.items())),
                           eligible_pairs=len(eligible), eligible_label_counts=dict(sorted(counts.items())),
                           excluded_pairs=excluded, annotation_warnings=warnings, deduplication_skips=skipped,
                           eligible_not_selected=sorted(r['key'] for r in eligible if r['key'] not in chosen_keys)),
                summary=summary, protocol=dict(PROTOCOL, per_class=per_class, seed=seed, planned_calls=3 * per_class))


def verify_history():
    manifest, summary = read(HISTORY / 'manifest.json'), read(HISTORY / 'summary.json')
    checks = {}
    for root, hashes in ((ROOT, manifest['source_sha256']), (HISTORY, summary['artifacts_sha256'])):
        verify(root, hashes)
        checks.update({(root / name).relative_to(ROOT).as_posix(): expected for name, expected in hashes.items()})
    for name in ('manifest.json', 'summary.json'):
        checks[(HISTORY / name).relative_to(ROOT).as_posix()] = digest(HISTORY / name)
    return checks


def export_bundle(bundle, out, *, source_hashes):
    out = Path(out)
    _require(len(bundle['entries']) == bundle['protocol']['planned_calls'], 'planned_count_mismatch')
    out.mkdir(parents=True, exist_ok=False)
    for name in ('entries', 'gold', 'audit', 'summary'):
        write(out / f'{name}.json', bundle[name])
    for row in bundle['entries']:
        write(out / f"request-{row['key']}.json", request_for(row['packet']))
    write(out / 'manifest.json', dict(protocol=bundle['protocol'], planned_calls=len(bundle['entries']),
          keys=[r['key'] for r in bundle['entries']], source_sha256=source_hashes,
          artifacts_sha256={p.name: digest(p) for p in out.glob('*.json')}))


def verify_prepared(out=OUT):
    out = Path(out)
    manifest = read(out / 'manifest.json')
    verify(ROOT, manifest['source_sha256']); verify(out, manifest['artifacts_sha256'])
    protocol = manifest['protocol']
    _require(all(protocol.get(k) == v for k, v in PROTOCOL.items() if k != 'seed'), 'protocol_drift')
    entries, gold = read(out / 'entries.json'), read(out / 'gold.json')
    keys = [r['key'] for r in entries]
    _require(keys == manifest['keys'] and len(set(keys)) == len(keys)
             and len(keys) == manifest['planned_calls'] == protocol['planned_calls']
             and len(keys) == 3 * protocol['per_class'], 'identity_drift')
    _require([r['key'] for r in gold] == keys and Counter(r['label'] for r in gold) ==
             Counter(dict.fromkeys(LABELS, protocol['per_class'])), 'gold_drift')
    for entry in entries:
        _require(read(out / f"request-{entry['key']}.json") == request_for(entry['packet']), 'request_drift')
    return manifest


def prepare(out=OUT):
    if Path(out).exists():
        raise FileExistsError('experiment_already_exists')
    frozen = verify_history()
    files = [DATA / 'claims_dev.jsonl', DATA / 'corpus.jsonl']
    own = ['tests/integration/prepare_scifact_verifier.py', 'tests/test_scifact_verifier.py',
           'docs/specs/scifact_verifier/acceptance.md', 'tests/traceability/scifact_verifier/coverage.py']
    for path in files + [ROOT / name for name in own]:
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    def rows(path):
        with path.open(encoding='utf-8') as handle:
            return [json.loads(line) for line in handle if line.strip()]
    bundle = build_bundle(rows(files[0]), rows(files[1]))
    verify(ROOT, frozen)  # Detect concurrent changes before writing the final selection.
    export_bundle(bundle, out, source_hashes=frozen)
    verify_prepared(out)
    return bundle['summary']


def score(entries, gold, results):
    """Project-specific three-way classification, NOT official SciFact scoring."""
    lookup = {r['key']: r for r in entries}
    labels = {r['key']: r['label'] for r in gold}
    _require(lookup and len(lookup) == len(entries) and len(labels) == len(gold)
             and set(labels) == set(lookup) and all(v in LABELS for v in labels.values()), 'invalid_scoring_inputs')
    outcomes = dict.fromkeys(lookup, 'MISSING')
    seen = set()
    mapping = {('supported', 'entailed'): 'SUPPORT', ('unsupported', 'contradicted'): 'CONTRADICT',
               ('unsupported', 'not_in_evidence'): 'NOT_ENOUGH_INFO'}
    for result in results:
        key = result.get('key')
        _require(key in lookup and key not in seen, 'unknown_or_duplicate_result')
        seen.add(key)
        packet = lookup[key]['packet']
        _require(result.get('request_sha256') == value_hash(request_for(packet)), 'result_request_drift')
        _require(result.get('status') in ('ok', 'error'), 'invalid_result_status')
        outcomes[key] = 'ERROR'
        if result['status'] != 'ok' or result.get('finish_reason') != 'stop' or result.get('provider_refusal'):
            continue
        try:
            decision = parse_decision(result.get('raw_content'), packet)
        except ValueError:
            continue
        outcomes[key] = mapping.get((decision['verdict'], decision['reason_code']), 'UNCERTAIN')
    columns = LABELS + ('UNCERTAIN', 'ERROR', 'MISSING')
    confusion = {label: dict.fromkeys(columns, 0) for label in LABELS}
    for key, predicted in outcomes.items():
        confusion[labels[key]][predicted] += 1
    total, counts = len(labels), Counter(outcomes.values())
    correct = sum(confusion[label][label] for label in LABELS)
    per_class = {}
    for label in LABELS:
        tp = confusion[label][label]
        actual, predicted = sum(confusion[label].values()), counts[label]
        precision, recall = tp / predicted if predicted else 0, tp / actual if actual else 0
        per_class[label] = dict(support=actual, precision=precision if results else None,
                               recall=recall if results else None,
                               f1=2 * precision * recall / (precision + recall) if precision + recall else 0 if results else None)
    negative = sum(labels[k] != 'SUPPORT' for k in labels)
    positives = total - negative
    false_accept = sum(labels[k] != 'SUPPORT' and outcomes[k] == 'SUPPORT' for k in labels)
    positive_block = sum(labels[k] == 'SUPPORT' and outcomes[k] != 'SUPPORT' for k in labels)
    negative_verdict = sum(labels[k] == 'SUPPORT' and outcomes[k] in LABELS[1:] for k in labels)
    return dict(total=total, received=len(results), complete=len(results) == total,
                classified=sum(counts[label] for label in LABELS), uncertain=counts['UNCERTAIN'],
                errors=counts['ERROR'], missing=counts['MISSING'], correct=correct,
                accuracy_full_denominator=correct / total if results else None,
                macro_f1=sum(v['f1'] for v in per_class.values()) / 3 if results else None,
                per_class=per_class, confusion=confusion,
                false_accept_count=false_accept, false_accept_denominator=negative,
                false_accept_rate=false_accept / negative if negative and results else None,
                positive_block_count=positive_block, positive_block_denominator=positives,
                positive_block_rate=positive_block / positives if positives and results else None,
                positive_negative_verdict_count=negative_verdict,
                official_scifact_score=False, project_human_verified=False,
                cases=[dict(key=k, gold=labels[k], predicted=outcomes[k], correct=labels[k] == outcomes[k]) for k in labels])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'verify', 'score'))
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--results', type=Path, help='Saved result JSON list; never causes a model call')
    args = parser.parse_args()
    if args.stage == 'prepare':
        result = prepare(args.out)
    elif args.stage == 'verify':
        manifest = verify_prepared(args.out)
        result = dict(status='verified', planned_calls=manifest['planned_calls'], provider_calls=0)
    else:
        if args.results is None:
            parser.error('--results is required for offline scoring')
        verify_prepared(args.out)
        result = score(read(args.out / 'entries.json'), read(args.out / 'gold.json'), read(args.results))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
