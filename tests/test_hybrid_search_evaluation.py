import unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch

from scripts.evaluate_hybrid_search import compare, validate_inputs
from tests.test_hybrid_search import document


def inputs():
    corpus = [document('a', 'semantic'), document('b', 'rarekey')]
    for hit in corpus:
        hit['metadata'].update(page_start=1, content_type='paragraph', section_path=[])
    dataset = dict(dataset_id='unit', collection_id='kb', annotation_status='human_verified',
        corpus=dict(paper_count=1, chunk_count=2), cases=[dict(id='Q1', question='rarekey', answerable=True,
        category='exact', gold_evidence_sets=[[dict(chunk_id='b', filename='paper.pdf', page_start=1)]])])
    baseline = dict(dataset_id='unit', collection_id='kb', top_k=10,
        corpus_validation=dict(document_count=1, chunk_count=2), results=[dict(id='Q1',
        answerable=True, hits=[dict(rank=1, chunk_id='a', filename='paper.pdf', page_start=1, score=.8)])])
    return dataset, baseline, corpus


class HybridEvaluationTests(unittest.TestCase):
    # AC-5106
    def test_network_free_comparison_and_paired_gain(self):
        dataset, baseline, corpus = inputs()
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            result = compare(dataset, baseline, corpus)
        self.assertEqual(result['summary']['dense']['strict_evidence_hit_rate'], 0)
        self.assertEqual(result['summary']['hybrid']['strict_evidence_hit_rate'], 1)
        self.assertEqual(result['paired_outcomes']['strict_evidence_hit']['wins'], 1)
        self.assertEqual(result['external_api_calls'], 0)

    def test_mismatched_dataset_collection_cases_counts_and_topk_rejected(self):
        for change in [lambda b: b.update(dataset_id='wrong'),
                       lambda b: b.update(collection_id='wrong'),
                       lambda b: b.update(top_k=20),
                       lambda b: b['corpus_validation'].update(chunk_count=3),
                       lambda b: b['results'].append(deepcopy(b['results'][0]))]:
            dataset, baseline, corpus = inputs()
            change(baseline)
            with self.assertRaises(ValueError):
                validate_inputs(dataset, baseline, corpus)

    def test_stale_gold_or_baseline_metadata_or_rank_rejected(self):
        for change in [lambda d,b: d['cases'][0]['gold_evidence_sets'][0][0].update(chunk_id='missing'),
                       lambda d,b: b['results'][0]['hits'][0].update(filename='wrong.pdf'),
                       lambda d,b: b['results'][0]['hits'][0].update(rank=2),
                       lambda d,b: b['results'][0]['hits'][0].update(score=float('nan'))]:
            dataset, baseline, corpus = inputs()
            change(dataset, baseline)
            with self.assertRaises(ValueError):
                validate_inputs(dataset, baseline, corpus)

    def test_no_answer_cases_not_in_recall_denominator(self):
        dataset, baseline, corpus = inputs()
        dataset['cases'].append(dict(id='Q2', question='unseen', answerable=False, gold_evidence_sets=[]))
        baseline['results'].append(dict(id='Q2', answerable=False, hits=[]))
        result = compare(dataset, baseline, corpus)
        self.assertEqual(result['answerable_cases'], 1)
        self.assertEqual(result['unanswerable_cases'], 1)
        self.assertIsNone(result['results'][-1]['hybrid']['strict_evidence_hit'])

    def test_harness_replay_uses_only_saved_artifacts(self):
        from harness.config import load_config
        root = Path(__file__).resolve().parents[1]
        config = load_config(root / 'harness/configs/hybrid-search-ab-replay-v1.json')
        self.assertEqual(len(config.stages), 2)
        self.assertTrue(all(stage.source.kind == 'artifact' for stage in config.stages))


if __name__ == '__main__':
    unittest.main()
