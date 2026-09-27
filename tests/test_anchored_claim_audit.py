import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from tests.integration.isolated_claim_audit import split_claims
from tests.integration.anchored_claim_audit import (
    prepare_units, make_anchors, judge_messages, parse_decision,
    local_decision, judge_one, run_units,
)


SOURCES = [
    dict(source_id='S1', chunk_text='W 0 is frozen. A and B are trainable.\n\nscale by α r .'),
    dict(source_id='S2', chunk_text='SECRET_OTHER: a classification head.'),
]


def units(answer, sources=SOURCES):
    return prepare_units(answer, split_claims(answer, sources))


def decision(unit, verdict='supported', reason_code='entailed', ids=None):
    return json.dumps(dict(claim_id=unit['id'], verdict=verdict,
        reason_code=reason_code, reason='test reason',
        evidence_ids=[unit['anchors'][0]['anchor_id']] if ids is None else ids))


def response(raw, finish='stop', refusal=None):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish,
        message=SimpleNamespace(content=raw, refusal=refusal))], usage=None)


class SubjectTests(unittest.TestCase):
    # AC-3201 / AC-3204
    def test_w0_hint_is_only_original_symbol_not_frozen_predicate(self):
        answer = r'该改写中，$ W_0 \in \mathbb{R}^{d \times k} $ 被冻结，不参与梯度更新 [S1]。'
        before = split_claims(answer, SOURCES)
        after = prepare_units(answer, before)
        target = after[1]
        self.assertEqual(target['text'], '不参与梯度更新')
        self.assertEqual(target['subject_context']['text'], 'W_0')
        hint = target['subject_context']
        self.assertEqual(answer[hint['start']:hint['end']], 'W_0')
        payload = json.loads(judge_messages('Which parameters?', target)[1]['content'])
        self.assertNotIn('被冻结', json.dumps(payload, ensure_ascii=False))
        self.assertEqual(before, split_claims(answer, SOURCES))
        for old, new in zip(before, after):
            for field in old:
                self.assertEqual(old[field], new[field])

    def test_encoder_then_decoder_changes_inherited_subject(self):
        answer = '编码器由六层构成，每层含两个子层；解码器同样为六层，并使用掩码 [S1]。'
        result = units(answer)
        self.assertEqual(result[1]['subject_context']['text'], '编码器')
        self.assertEqual(result[3]['subject_context']['text'], '解码器')

    def test_bert_classifier_claim_retains_subject_but_not_sibling_fact(self):
        answer = 'BERT 的预训练与微调均仅依赖编码器结构，且其下游任务适配时通常仅添加轻量级分类头，不引入解码器组件 [S1]。'
        target = units(answer)[1]
        self.assertEqual(target['subject_context']['text'], 'BERT')
        payload = json.dumps(judge_messages('Compare two models', target), ensure_ascii=False)
        self.assertNotIn('依赖编码器结构', payload)
        self.assertNotIn('不引入解码器组件', payload)
        self.assertNotIn('SECRET_OTHER', payload)

    def test_no_cross_sentence_or_newline_subject_borrowing(self):
        for separator in ('。', '\n'):
            with self.subTest(separator=separator):
                target = units('BERT使用编码器 [S1]' + separator + '不包含解码器 [S1]。')[-1]
                self.assertIsNone(target['subject_context'])
                self.assertEqual(target['subject_status'], 'unresolved')

    def test_explicit_model_switch_does_not_keep_bert(self):
        result = units('BERT采用编码器；LoRA冻结原参数，且仅训练低秩矩阵 [S1]。')
        self.assertEqual(result[-1]['subject_context']['text'], 'LoRA')

    def test_paper_introducing_model_does_not_make_paper_the_model_subject(self):
        result = units('论文《An Example》提出了 **NewNet 模型**，其采用注意力，不含循环 [S1]。')
        self.assertEqual(result[-1]['subject_context']['text'], 'NewNet 模型')

    def test_greek_symbol_and_intro_comma_are_explicit(self):
        self.assertEqual(units(r'其中 $ \alpha $ 为常量 [S1]。')[0]['detected_subject']['text'], r'\alpha')
        self.assertEqual(units('其中，NewNet使用注意力 [S1]。')[0]['detected_subject']['text'], 'NewNet')

    def test_unknown_new_subject_clears_old_hint(self):
        result = units('BERT使用编码器；新组件被重新初始化，且不更新参数 [S1]。')
        self.assertIsNone(result[-1]['subject_context'])

    def test_subject_hint_does_not_import_antecedent_evidence(self):
        target = units('BERT使用编码器 [S2]，且不包含解码器 [S1]。')[-1]
        payload = json.dumps(judge_messages('q', target), ensure_ascii=False)
        self.assertEqual(target['subject_context']['text'], 'BERT')
        self.assertNotIn('SECRET_OTHER', payload)
        self.assertEqual({a['source_id'] for a in target['anchors']}, {'S1'})

    def test_unsafe_offsets_and_duplicate_units_rejected(self):
        answer = 'BERT使用编码器 [S1]。'
        original = split_claims(answer, SOURCES)
        bad = copy.deepcopy(original); bad[0]['start'] += 1
        with self.assertRaises(ValueError): prepare_units(answer, bad)
        with self.assertRaises(ValueError): prepare_units(answer, original + original)


class AnchorTests(unittest.TestCase):
    # AC-3202 / AC-3203
    def test_exact_partition_preserves_math_spaces_unicode_and_newlines(self):
        text = '标题\n\nd model = 512 , α r . [MASK] 28.4 ' + r'$\frac{a}{b}$' + '。尾部  '
        sources = [dict(source_id='S1', chunk_text=text)]
        anchors = make_anchors(sources, max_chars=40)
        self.assertEqual(''.join(a['text'] for a in anchors), text)
        self.assertEqual(anchors, make_anchors(sources, max_chars=40))
        for i, a in enumerate(anchors):
            self.assertEqual(a['text'], text[a['start']:a['end']])
            self.assertEqual(a['start'], anchors[i-1]['end'] if i else 0)
        self.assertEqual(len({a['anchor_id'] for a in anchors}), len(anchors))

    def test_long_literal_is_explicitly_marked_as_forced_split(self):
        anchors = make_anchors([dict(source_id='S1', chunk_text='$'+'x'*100+'$')], max_chars=32)
        self.assertTrue(any(a['forced_split'] for a in anchors))
        self.assertTrue(all(len(a['text']) <= 32 for a in anchors))

    def test_source_validation_and_size_limits(self):
        for sources in ([SOURCES[0], SOURCES[0]], [dict(source_id='../bad', chunk_text='x')],
                        [dict(source_id='S1', chunk_text='')]):
            with self.assertRaises(ValueError): make_anchors(sources)
        for limit in (0, -1, True, 1.5):
            with self.assertRaises(ValueError): make_anchors(SOURCES, max_chars=limit)

    def test_repeated_text_has_distinct_locations(self):
        anchors = make_anchors([dict(source_id='S1', chunk_text='repeat. '*30)], max_chars=40)
        self.assertGreater(len(anchors), 1)
        self.assertEqual(len(anchors), len({a['anchor_id'] for a in anchors}))

    def test_normal_math_literal_and_decimal_not_split_when_they_fit(self):
        text = 'Header. ' + r'$\frac{a}{b}$' + ' is 28.4. [MASK] remains.'
        anchors = make_anchors([dict(source_id='S1', chunk_text=text)], max_chars=32)
        self.assertTrue(any(r'$\frac{a}{b}$' in a['text'] for a in anchors))
        self.assertTrue(any('28.4' in a['text'] for a in anchors))
        self.assertTrue(any('[MASK]' in a['text'] for a in anchors))


class DecisionTests(unittest.TestCase):
    # AC-3203 / AC-3204
    def setUp(self):
        self.unit = units('W0被冻住 [S1]。')[0]

    def test_anchor_resolution_reconstructs_exact_original(self):
        parsed = parse_decision(decision(self.unit), self.unit)
        quote = parsed['supporting_quotes'][0]
        self.assertEqual(quote['quote'], SOURCES[0]['chunk_text'][quote['start']:quote['end']])
        self.assertEqual(quote['source_id'], 'S1')
        self.assertEqual(parsed['evidence_ids'], [quote['anchor_id']])

    def test_unknown_foreign_duplicate_or_empty_support_anchors_fail(self):
        own = self.unit['anchors'][0]['anchor_id']
        for ids in ([], ['S2:E0001'], ['S1:E9999'], [own, own], [1]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                parse_decision(decision(self.unit, ids=ids), self.unit)

    def test_strict_json_schema_and_no_quote_repair(self):
        raw = decision(self.unit)
        for bad in (raw+'junk', '```json\n'+raw+'\n```', raw.replace('test reason', ''),
                    raw.replace('"reason":', '"quote":"changed text", "reason":'),
                    raw.replace('"verdict":', '"verdict":"uncertain", "verdict":'),
                    raw.replace('"C001"', '"C999"'), raw.replace('"reason": "test reason"', '"reason": NaN')):
            with self.subTest(bad=bad), self.assertRaises(ValueError): parse_decision(bad, self.unit)

    def test_ambiguity_cannot_be_reported_as_unsupported(self):
        for code in ('ambiguous_subject', 'ambiguous_evidence'):
            self.assertEqual(parse_decision(decision(self.unit, 'uncertain', code, []), self.unit)['verdict'], 'uncertain')
            with self.assertRaises(ValueError): parse_decision(decision(self.unit, 'unsupported', code, []), self.unit)

    def test_missing_support_not_converted_to_truth_error(self):
        parsed = parse_decision(decision(self.unit, 'unsupported', 'not_in_evidence', []), self.unit)
        self.assertEqual(parsed['reason_code'], 'not_in_evidence')

    def test_tampered_anchor_text_and_offsets_rejected(self):
        for field, value in (('text', 'fake'), ('end', 9999), ('source_id', 'S2')):
            bad = copy.deepcopy(self.unit); bad['anchors'][0][field] = value
            with self.assertRaises(ValueError): parse_decision(decision(self.unit), bad)

    def test_prompt_has_no_full_answer_or_other_evidence(self):
        payload = json.loads(judge_messages('q', self.unit)[1]['content'])
        self.assertEqual(set(payload), {'question','claim_id','claim','subject_context','subject_status','cited_anchors'})
        self.assertNotIn('SECRET_OTHER', json.dumps(payload))
        self.assertNotIn('supporting_quotes', judge_messages('q', self.unit)[0]['content'])

    def test_no_evidence_is_local_and_has_reason_code(self):
        unit = units('未引用结论。')[0]
        result = local_decision(unit)
        self.assertEqual(result['reason_code'], 'no_valid_citation')
        self.assertEqual(result['verdict'], 'unsupported')
        self.assertIsNone(local_decision(self.unit))


class CallTests(unittest.IsolatedAsyncioTestCase):
    # AC-3204 / AC-3205
    async def test_one_call_and_raw_output_preserved(self):
        unit = units('BERT冻结权重 [S1]。')[0]; client = AsyncMock()
        raw = decision(unit); client.chat.completions.create.return_value = response(raw)
        result = await judge_one(client, 'qwen3-vl-plus', 'q', unit)
        self.assertEqual(result['status'], 'ok'); self.assertEqual(result['raw_judge_text'], raw)
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs['response_format'], {'type':'json_object'})
        self.assertFalse(kwargs['extra_body']['enable_thinking'])
        client.chat.completions.create.assert_awaited_once()

    async def test_failure_and_truncation_not_retried(self):
        unit = units('BERT冻结权重 [S1]。')[0]
        for value in (response('{bad'), response(decision(unit), 'length'), response(decision(unit), refusal='no')):
            client = AsyncMock(); client.chat.completions.create.return_value = value
            result = await judge_one(client, 'm', 'q', unit)
            self.assertEqual(result['status'], 'error'); client.chat.completions.create.assert_awaited_once()

    async def test_budget_and_incomplete_attempt_preflight(self):
        unit = units('BERT冻结权重 [S1]。')[0]; client = AsyncMock()
        cases = [dict(id='A01', query='q', units=[unit])]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with self.assertRaises(ValueError): await run_units(client, 'm', cases, out, 0)
            (out/'attempt-A01-C001.json').write_text('{}', encoding='utf-8')
            with self.assertRaises(FileExistsError): await run_units(client, 'm', cases, out, 1)
            client.chat.completions.create.assert_not_awaited()

    async def test_cache_fingerprint_and_decision_are_checked_before_new_calls(self):
        unit = units('BERT冻结权重 [S1]。')[0]; client = AsyncMock()
        cases = [dict(id='A01', query='q', units=[unit])]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); client.chat.completions.create.return_value = response(decision(unit))
            await run_units(client, 'm', cases, out, 1)
            cached = await run_units(client, 'm', cases, out, 1)
            self.assertEqual(cached['A01/C001']['status'], 'ok')
            client.chat.completions.create.assert_awaited_once()
            changed = copy.deepcopy(cases); changed[0]['query'] = 'different'
            with self.assertRaises(ValueError): await run_units(client, 'm', changed, out, 1)
            path = out/'result-A01-C001.json'; data=json.loads(path.read_text(encoding='utf-8'))
            data['decision']['verdict']='unsupported'; path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError): await run_units(client, 'm', cases, out, 1)
            client.chat.completions.create.assert_awaited_once()

    async def test_cached_failure_is_not_retried(self):
        unit = units('BERT冻结权重 [S1]。')[0]; client = AsyncMock()
        cases = [dict(id='A01', query='q', units=[unit])]
        with tempfile.TemporaryDirectory() as tmp:
            client.chat.completions.create.return_value = response('{bad')
            for _ in range(2):
                results = await run_units(client, 'm', cases, Path(tmp), 1)
                self.assertEqual(results['A01/C001']['status'], 'error')
            client.chat.completions.create.assert_awaited_once()

    async def test_future_cached_mismatch_blocks_earlier_new_call(self):
        unit = units('BERT冻结权重 [S1]。')[0]; client = AsyncMock()
        cases = [dict(id='A01',query='q',units=[unit]), dict(id='A02',query='q',units=[unit])]
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            (out/'result-A02-C001.json').write_text('{"status":"ok","request_sha256":"wrong"}', encoding='utf-8')
            with self.assertRaises(ValueError): await run_units(client, 'm', cases, out, 2)
            client.chat.completions.create.assert_not_awaited()
            self.assertFalse((out/'attempt-A01-C001.json').exists())

    async def test_invalid_identity_and_bool_budget_make_no_call(self):
        unit = units('BERT冻结权重 [S1]。')[0]; client=AsyncMock()
        with tempfile.TemporaryDirectory() as tmp:
            cases=[dict(id='../escape',query='q',units=[unit])]
            with self.assertRaises(ValueError): await run_units(client,'m',cases,Path(tmp),1)
            cases[0]['id']='A01'
            with self.assertRaises(ValueError): await run_units(client,'m',cases,Path(tmp),True)
            client.chat.completions.create.assert_not_awaited()

    async def test_provider_exception_does_not_leak_message(self):
        unit = units('BERT冻结权重 [S1]。')[0]; client=AsyncMock()
        client.chat.completions.create.side_effect=RuntimeError('SECRET_CREDENTIAL')
        result=await judge_one(client,'m','q',unit)
        self.assertEqual(result['status'],'error')
        self.assertNotIn('SECRET_CREDENTIAL',json.dumps(result))


class PreparationTests(unittest.TestCase):
    # AC-3205: offline, write-once preparation, same denominator, immutable inputs.
    def test_prepare_offline_preserves_inputs_and_blocks_overwrite_and_hash_drift(self):
        from tests.integration import evaluate_multipaper_claims_v3 as runner
        from tests.integration.evaluate_multipaper_claims import sha, verify_hashes
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); previous=root/'v2'; previous.mkdir()
            impl=root/'tests/integration'; impl.mkdir(parents=True)
            script=impl/'evaluate_multipaper_claims_v3.py'; script.write_text('# fixture',encoding='utf-8')
            (impl/'anchored_claim_audit.py').write_text('# fixture',encoding='utf-8')
            sentinel=root/'frozen.txt'; sentinel.write_text('unchanged',encoding='utf-8')
            answer='BERT使用编码器，且不含解码器 [S1]。'
            cases=[dict(id='A01',query='q',answer=answer,fixed_refusal=False,
                        refusal_correct=True,units=split_claims(answer,SOURCES))]
            (previous/'inputs.json').write_text(json.dumps(cases),encoding='utf-8')
            (previous/'manifest.json').write_text(json.dumps({'file_sha256':{'frozen.txt':sha(sentinel)}}),encoding='utf-8')
            original=(previous/'inputs.json').read_bytes(); out=root/'v3'
            with patch.object(runner,'ROOT',root), patch.object(runner,'__file__',str(script)), \
                 patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
                stats=runner.prepare(out,previous)
                self.assertEqual(stats['actual_provider_requests'],0)
                self.assertEqual(stats['total_units'],len(cases[0]['units']))
                self.assertFalse(stats['semantic_scores_available'])
                self.assertEqual((previous/'inputs.json').read_bytes(),original)
                manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
                verify_hashes(root,manifest['file_sha256'])
                with self.assertRaises(FileExistsError): runner.prepare(out,previous)
                sentinel.write_text('changed',encoding='utf-8')
                with self.assertRaises(ValueError): runner.prepare(root/'v3-again',previous)
                self.assertFalse((root/'v3-again').exists())


if __name__ == '__main__': unittest.main()
