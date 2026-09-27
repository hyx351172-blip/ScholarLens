import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from tests.integration.isolated_claim_audit import (
    split_claims, judge_messages, parse_decision, local_decision, summarize,
    judge_one, run_units,
)


SOURCES = [
    {'source_id': 'S1', 'chunk_text': 'BERT uses an encoder. Its score is 28.4.', 'filename': 'bert.pdf'},
    {'source_id': 'S2', 'chunk_text': 'SECRET_OTHER: A model uses a classification head.', 'filename': 'other.pdf'},
]


def decision(unit, verdict='supported', quotes=None):
    return json.dumps(dict(claim_id=unit['id'], verdict=verdict, reason='test reason',
        supporting_quotes=quotes if quotes is not None else [{'source_id': 'S1', 'quote': 'BERT uses an encoder.'}]))


def provider(raw, finish='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish,
        message=SimpleNamespace(content=raw, refusal=None))], usage=None)


class ClauseTests(unittest.TestCase):
    def test_chinese_no_space_and_local_citation_scope(self):
        answer = 'BERT采用编码器 [S1]。它只加分类头 [S2]。未引证的额外断言。'
        units = split_claims(answer, SOURCES)
        self.assertEqual(len(units), 3)
        self.assertEqual([u['citation_ids'] for u in units], [['S1'], ['S2'], []])
        for u in units:
            self.assertEqual(answer[u['start']:u['end']], u['text'])

    def test_semicolon_comma_children_inherit_only_trailing_group(self):
        answer = 'BERT采用编码器，且其下游仅添加分类头 [S1]；另一个模型训练全部参数 [S2]。'
        units = split_claims(answer, SOURCES)
        self.assertEqual(len(units), 3)
        self.assertEqual([u['citation_ids'] for u in units], [['S1'], ['S1'], ['S2']])
        self.assertIn('分类头', units[1]['text'])
        self.assertIn('context_dependent', units[1]['warnings'])

    def test_uncited_sentence_cannot_borrow_next_or_previous_sources(self):
        units = split_claims('模型有十层。另一个结论 [S1]。\n新增结论\n后续结论 [S2]。', SOURCES)
        self.assertEqual([u['citation_ids'] for u in units], [[], ['S1'], [], ['S2']])

    def test_math_decimal_abbreviation_and_special_token_preservation(self):
        answer = r'Use [MASK] with $f(x,y)=1.5x$ and Li et al. (2018) [S1]. Score is 28.4 [S1].'
        units = split_claims(answer, SOURCES)
        self.assertEqual(len(units), 2)
        self.assertIn('[MASK]', units[0]['text'])
        self.assertIn('$f(x,y)=1.5x$', units[0]['text'])
        self.assertIn('et al.', units[0]['text'])
        self.assertIn('28.4', units[1]['text'])

    def test_latex_brackets_and_code_do_not_create_citations(self):
        units = split_claims(r'Math $[S2]+1$ and `[S2]` are tokens [S1].', SOURCES)
        self.assertEqual(units[0]['citation_ids'], ['S1'])
        self.assertEqual(len(units[0]['evidence']), 1)

    def test_grouped_citations_and_invalid_ids_retained(self):
        units = split_claims('该方法成立 [S1, S2][S99]。', SOURCES)
        self.assertEqual(units[0]['citation_ids'], ['S1', 'S2', 'S99'])
        self.assertEqual(units[0]['invalid_citation_ids'], ['S99'])

    def test_only_structural_intro_is_skipped_not_bold_assertion(self):
        units = split_claims('具体而言：\n**模型有十层**。\n- 使用编码器 [S1]。', SOURCES)
        self.assertEqual(len(units), 2)
        self.assertIn('十层', units[0]['text'])
        self.assertEqual(units[0]['citation_ids'], [])

    def test_repeated_claims_get_distinct_stable_ids(self):
        answer = '相同结论 [S1]。相同结论 [S1]。'
        one = split_claims(answer, SOURCES)
        self.assertNotEqual(one[0]['id'], one[1]['id'])
        self.assertEqual(one, split_claims(answer, SOURCES))

    def test_numbered_list_markers_are_not_factual_claims(self):
        units = split_claims('1. BERT采用编码器 [S1]。\n2. 另一个事实 [S2]。', SOURCES)
        self.assertEqual(len(units), 2)
        self.assertEqual([u['citation_ids'] for u in units], [['S1'], ['S2']])

    def test_full_structural_intro_checked_before_comma_split(self):
        units = split_claims('对于被选中的 token，其后续处理按以下概率分布执行：\n- 80%替换为[MASK] [S1]。', SOURCES)
        self.assertEqual(len(units), 1)
        self.assertIn('[MASK]', units[0]['text'])

    def test_separate_initialization_assertions_and_protect_math_warning(self):
        units = split_claims('LoRA 的 A 使用高斯初始化，B 使用零初始化 [S1]。', SOURCES)
        self.assertEqual(len(units), 2)
        formula = split_claims(r'$f(x,y)=1.5x$ [S1].', SOURCES)[0]
        self.assertNotIn('may_remain_composite', formula['warnings'])

    def test_prior_real_classifier_head_failure_has_own_request(self):
        units = split_claims('BERT采用双向编码器 [S1]。BERT预训练与微调仅依赖编码器结构，且其下游任务适配时通常仅添加轻量级分类头，不引入解码器组件 [S1]。', SOURCES)
        head = next(u for u in units if '分类头' in u['text'])
        self.assertNotIn('BERT采用双向编码器', head['text'])
        request = json.dumps(judge_messages('比较两篇论文的结构', head), ensure_ascii=False)
        self.assertNotIn('SECRET_OTHER', request)
        self.assertNotIn('不引入解码器组件', request)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.unit = split_claims('BERT uses an encoder [S1].', SOURCES)[0]

    def test_request_physically_omits_other_claims_and_sources(self):
        payload = json.dumps(judge_messages('Describe BERT.', self.unit), ensure_ascii=False)
        self.assertIn('BERT uses an encoder.', payload)
        self.assertNotIn('SECRET_OTHER', payload)
        self.assertNotIn('classification head', payload)
        self.assertNotIn('other.pdf', payload)
        self.assertIn('JSON', payload)

    def test_valid_supported_and_uncertain(self):
        self.assertEqual(parse_decision(decision(self.unit), self.unit)['verdict'], 'supported')
        self.assertEqual(parse_decision(decision(self.unit, 'uncertain', []), self.unit)['verdict'], 'uncertain')

    def test_bad_schema_duplicate_keys_and_non_json_are_errors(self):
        valid = decision(self.unit)
        malformed = [valid+' trailing', '```json\n'+valid+'\n```', valid.replace('"supported"', 'true'),
                     valid.replace('test reason', ''), valid.replace('"claim_id":', '"extra": 1, "claim_id":'),
                     valid.replace('"verdict": "supported"', '"verdict":"unsupported","verdict":"supported"'),
                     valid.replace(self.unit['id'], 'WRONG'), '{"claim_id":"broken}']
        for raw in malformed:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_decision(raw, self.unit)

    def test_quotes_must_exist_in_this_units_evidence(self):
        for quotes in ([], [{'source_id': 'S2', 'quote': 'SECRET_OTHER'}],
                       [{'source_id': 'S1', 'quote': 'invented quotation'}]):
            with self.subTest(quotes=quotes), self.assertRaises(ValueError):
                parse_decision(decision(self.unit, quotes=quotes), self.unit)

    def test_no_evidence_is_local_unsupported(self):
        unit = split_claims('An assertion [S99].', SOURCES)[0]
        self.assertEqual(local_decision(unit)['verdict'], 'unsupported')
        self.assertIsNone(local_decision(self.unit))

    def test_errors_missing_and_uncertain_do_not_pass(self):
        units = split_claims('One [S1]. Two [S1]. Three [S1]. Four [S1].', SOURCES)
        case = {'id': 'case', 'units': units, 'fixed_refusal': False, 'refusal_correct': True}
        results = {'case/'+units[0]['id']: {'status': 'ok', 'decision': {'verdict': 'supported'}},
                   'case/'+units[1]['id']: {'status': 'ok', 'decision': {'verdict': 'uncertain'}},
                   'case/'+units[2]['id']: {'status': 'error'}}
        summary = summarize([case], results)
        self.assertEqual(summary['total_units'], 4)
        self.assertEqual(summary['supported_units'], 1)
        self.assertEqual(summary['uncertain_units'], 1)
        self.assertEqual(summary['error_units'], 1)
        self.assertEqual(summary['pending_units'], 1)
        self.assertEqual(summary['supported_fraction_all_units'], .25)
        self.assertFalse(summary['semantic_gate_passed'])


class CallTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_mode_non_thinking_one_unit(self):
        unit = split_claims('BERT uses an encoder [S1].', SOURCES)[0]
        client = AsyncMock()
        client.chat.completions.create.return_value = provider(decision(unit))
        result = await judge_one(client, 'qwen3-vl-plus', 'Question', unit)
        self.assertEqual(result['status'], 'ok')
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs['response_format'], {'type': 'json_object'})
        self.assertFalse(kwargs['extra_body']['enable_thinking'])
        client.chat.completions.create.assert_awaited_once()

    async def test_truncation_and_malformed_response_retained_as_errors(self):
        unit = split_claims('BERT uses an encoder [S1].', SOURCES)[0]
        for response in (provider(decision(unit), 'length'), provider('{bad json')):
            client = AsyncMock(); client.chat.completions.create.return_value = response
            result = await judge_one(client, 'model', 'Question', unit)
            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['raw_judge_text'], response.choices[0].message.content)
            client.chat.completions.create.assert_awaited_once()

    async def test_request_budget_and_uncertain_attempt_stop_calls(self):
        unit = split_claims('BERT uses an encoder [S1].', SOURCES)[0]
        cases = [{'id': 'case', 'query': 'q', 'units': [unit]}]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); client = AsyncMock()
            with self.assertRaises(ValueError):
                await run_units(client, 'model', cases, out, 0)
            self.assertFalse(client.chat.completions.create.called)
            (out/f"attempt-case-{unit['id']}.json").write_text('{}', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                await run_units(client, 'model', cases, out, 1)
            self.assertFalse(client.chat.completions.create.called)

    async def test_cached_wrong_claim_decision_cannot_be_reused(self):
        unit = split_claims('BERT uses an encoder [S1].', SOURCES)[0]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); client = AsyncMock()
            result = {'status': 'ok', 'decision': json.loads(decision(unit))}
            result['decision']['claim_id'] = 'FOREIGN'
            (out/f"result-case-{unit['id']}.json").write_text(json.dumps(result), encoding='utf-8')
            with self.assertRaises(ValueError):
                await run_units(client, 'model', [{'id':'case','query':'q','units':[unit]}], out, 1)
            self.assertFalse(client.chat.completions.create.called)


if __name__ == '__main__':
    unittest.main()
