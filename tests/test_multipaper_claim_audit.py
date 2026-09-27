import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
from tests.integration.evaluate_multipaper_claims import (
    build_case, build_prompt, score_judgment, summarize, save_new, verify_hashes, judge_once,
)


def fixture():
    return {'query': 'What did A report?', 'response': {'success': True,
        'answer': 'The model uses [MASK] tokens [S1]. It beats B [S2].',
        'sources': [{'source_id': 'S1', 'chunk_text': 'Uses [MASK] tokens.'},
                    {'source_id': 'S2', 'chunk_text': 'UNRELATED_SECOND_SOURCE'},
                    {'source_id': 'S3', 'chunk_text': 'SECRET_UNCITED_CORRECT_EVIDENCE'}]}}


class MultiPaperClaimAuditTests(unittest.TestCase):
    def test_case_preserves_claim_text_and_scoped_evidence(self):
        case = build_case('A01', fixture(), True, 'What did A report?')
        self.assertEqual(case['units'][0]['claim_text'], 'The model uses [MASK] tokens .')
        self.assertEqual([s['source_id'] for s in case['units'][0]['evidence']], ['S1'])
        self.assertEqual([s['source_id'] for s in case['units'][1]['evidence']], ['S2'])
        prompt = build_prompt(case)
        self.assertNotIn('SECRET_UNCITED_CORRECT_EVIDENCE', prompt)
        self.assertIn('all assertions', prompt)
        self.assertIn('never borrow', prompt)
        self.assertNotIn('expected_answer', prompt)

    def test_identity_and_misaligned_sources_fail_before_judging(self):
        for mutation in ('question', 'order', 'success', 'empty'):
            record = fixture()
            if mutation == 'question': record['query'] = 'other'
            if mutation == 'order': record['response']['sources'][0]['source_id'] = 'S3'
            if mutation == 'success': record['response']['success'] = False
            if mutation == 'empty': record['response']['answer'] = ''
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build_case('A01', record, True, 'What did A report?')

    def test_fixed_refusal_not_scored_as_unsupported_factual_claim(self):
        record = fixture()
        record['response']['answer'] = INSUFFICIENT_EVIDENCE
        record['response']['sources'] = None  # Empty-KB response uses optional null.
        case = build_case('N01', record, False, record['query'])
        self.assertTrue(case['refusal_correct'])
        self.assertEqual(case['units'], [])
        case2 = build_case('P01', record, True, record['query'])
        self.assertFalse(case2['refusal_correct'])
        self.assertFalse(summarize([case2], {})['review_complete'])
        self.assertIsNone(summarize([case], {})['support_rate_judged_units'])

    def test_judge_cannot_pass_missing_evidence_or_duplicate_ids(self):
        record = fixture()
        record['response']['answer'] = 'An uncited assertion. Another claim [S9].'
        case = build_case('A01', record, True, record['query'])
        raw = json.dumps({'concepts': [], 'claims': [{'id': 'A1', 'supported': True, 'reason': 'guessed'},
                                     {'id': 'A2', 'supported': True, 'reason': 'guessed'}]})
        scored = score_judgment(case, raw)
        self.assertEqual(scored['supported_claim_ids'], [])
        self.assertRaises(ValueError, score_judgment, case, '{"claims": []}')
        self.assertRaises(ValueError, score_judgment, case, '{"claims": [{"id":"A1","supported":"true","reason":"x"}]}')
        duplicate = json.loads(raw)
        duplicate['claims'][1]['id'] = 'A1'
        self.assertRaises(ValueError, score_judgment, case, json.dumps(duplicate))

    def test_failed_missing_judgments_remain_in_denominator(self):
        case = build_case('A01', fixture(), True, 'What did A report?')
        case2 = copy.deepcopy(case); case2['id'] = 'B01'
        raw = '{"concepts":[],"claims":[{"id":"A1","supported":true,"reason":"yes"},{"id":"A2","supported":false,"reason":"no"}]}'
        result = {'status': 'ok', 'judgment': score_judgment(case, raw)}
        summary = summarize([case, case2], {'A01': result, 'B01': {'status': 'error'}})
        self.assertEqual(summary['total_units'], 4)
        self.assertEqual(summary['judged_units'], 2)
        self.assertEqual(summary['supported_units'], 1)
        self.assertEqual(summary['unjudged_units'], 2)
        self.assertEqual(summary['judgment_coverage'], .5)
        self.assertEqual(summary['support_rate_judged_units'], .5)
        self.assertFalse(summary['review_complete'])

    def test_result_files_are_write_once_and_hash_changes_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_new(root / 'x.json', {'a': 1})
            self.assertRaises(FileExistsError, save_new, root / 'x.json', {'a': 2})
            self.assertRaises(ValueError, verify_hashes, root, {'x.json': 'wrong'})


class JudgeCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_bounded_call_no_retry_on_failure(self):
        client = AsyncMock()
        client.chat.completions.create.side_effect = TimeoutError('mock')
        case = build_case('A01', fixture(), True, 'What did A report?')
        with self.assertRaises(TimeoutError):
            await judge_once(client, 'fixture-model', case)
        client.chat.completions.create.assert_awaited_once()
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs['max_tokens'], 2400)
        self.assertEqual(kwargs['temperature'], 0)
        self.assertFalse(kwargs['stream'])


if __name__ == '__main__':
    unittest.main()
