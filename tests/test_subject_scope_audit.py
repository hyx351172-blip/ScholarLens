import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from tests.integration.isolated_claim_audit import split_claims
from tests.integration.anchored_claim_audit import (
    prepare_units as prepare_v3, judge_messages, run_units,
)
from tests.integration.subject_scope_audit import prepare_units


SOURCES = [dict(source_id='S1', chunk_text='The cited evidence for this claim.'),
           dict(source_id='S2', chunk_text='UNRELATED_PREVIOUS_EVIDENCE')]


def make(answer):
    return prepare_units(answer, split_claims(answer, SOURCES))


class AntecedentTests(unittest.TestCase):
    # AC-3301 / AC-3303
    def test_introduced_object_becomes_property_antecedent_not_model(self):
        answer='由于需要位置信息，模型加入正弦函数构成的位置编码（positional encoding），其维度与嵌入相同 [S1]。'
        unit=make(answer)[-1]
        self.assertEqual(unit['subject_context']['text'],'位置编码')
        self.assertEqual(unit['subject_status'],'inherited')
        h=unit['subject_context']; self.assertEqual(answer[h['start']:h['end']],'位置编码')

    def test_unseen_object_and_property_not_paper_specific(self):
        answer='为表示图结构，系统生成节点表示向量，其形状为一维 [S1]。'
        unit=make(answer)[-1]
        self.assertEqual(unit['subject_context']['text'],'节点表示向量')
        self.assertEqual(unit['subject_resolution']['rule'],'introduced_object_property')

    def test_multiple_objects_stay_unresolved(self):
        for objects in ('位置编码和词嵌入','固定的位置编码与可学习的词嵌入','位置编码或节点表示'):
            with self.subTest(objects=objects):
                unit=make('由于需要上下文，系统引入'+objects+'，其维度相同 [S1]。')[-1]
                self.assertIsNone(unit['subject_context'])
                self.assertEqual(unit['subject_status'],'unresolved')

    def test_no_object_hint_for_unrelated_predicate(self):
        unit=make('为建模序列，系统生成上下文向量，其训练使用大量数据 [S1]。')[-1]
        self.assertIsNone(unit['subject_context'])

    def test_task_label_without_borrowing_task_details(self):
        answer='1. 掩码语言模型（Masked Language Model, MLM）：遮蔽若干词，并预测被遮蔽内容 [S1]。'
        unit=make(answer)[-1]
        self.assertEqual(unit['subject_context']['text'],'掩码语言模型')
        request=json.dumps(judge_messages('q',unit),ensure_ascii=False)
        self.assertNotIn('遮蔽若干词',request)

    def test_unseen_task_labels_with_and_without_parentheses(self):
        for label in ('图像重建任务','对比学习（Contrastive Learning）','目标检测任务(Object Detection)'):
            with self.subTest(label=label):
                unit=make(label+'：遮蔽输入，并恢复目标 [S1]。')[-1]
                self.assertEqual(unit['subject_context']['text'],label.split('（')[0].split('(')[0])

    def test_non_task_colon_prefix_is_not_assumed_to_be_task(self):
        unit=make('实验结果如下：误差有所下降，并达到新水平 [S1]。')[-1]
        self.assertIsNone(unit['subject_context'])

    def test_multiple_task_labels_do_not_become_single_hint(self):
        unit=make('图像重建任务和目标检测任务：共享编码器，并预测输出 [S1]。')[-1]
        self.assertIsNone(unit['subject_context'])

    def test_task_label_cannot_cross_list_item(self):
        unit=make('1. 图像重建任务：修复像素 [S1]；\n2. 并预测其他内容 [S1]。')[-1]
        self.assertIsNone(unit['subject_context'])

    def test_retrieved_evidence_scope_is_not_whole_paper(self):
        answer='当前检索证据未说明两个方法能否结合；仅分别描述两种通用机制 [S1]。'
        unit=make(answer)[-1]
        self.assertEqual(unit['subject_context']['text'],'当前检索证据')
        request=json.dumps(judge_messages('q',unit),ensure_ascii=False)
        self.assertNotIn('未说明两个方法能否结合',request)

    def test_alternate_evidence_scope_and_mixed_scope_negative(self):
        self.assertEqual(make('本次召回的片段仅涵盖实验；仅描述设置 [S1]。')[-1]['subject_context']['text'],'本次召回的片段')
        for prefix in ('论文未说明结合方法','当前检索证据和完整论文未说明结合方法'):
            with self.subTest(prefix=prefix):
                self.assertIsNone(make(prefix+'；仅描述设置 [S1]。')[-1]['subject_context'])

    def test_sentence_newline_and_intervening_subject_block_inheritance(self):
        for text in ('图像重建任务：修复输入 [S1]。并预测输出 [S1]。',
                     '当前检索证据描述实验 [S1]\n仅描述设置 [S1]。',
                     '当前检索证据描述实验；新模型表示不同过程，且仅输出特征 [S1]。'):
            with self.subTest(text=text): self.assertIsNone(make(text)[-1]['subject_context'])

    def test_prior_sources_not_imported(self):
        unit=make('当前检索证据描述实验 [S2]；仅描述设置 [S1]。')[-1]
        self.assertEqual(unit['subject_context']['text'],'当前检索证据')
        self.assertEqual(unit['citation_ids'],['S1'])
        self.assertNotIn('UNRELATED_PREVIOUS_EVIDENCE',json.dumps(judge_messages('q',unit)))


class ExplicitObjectTests(unittest.TestCase):
    # AC-3302 / AC-3303
    def test_coordinated_dimensions_do_not_pick_one_subject(self):
        unit=make(r'其中 $B \in \mathbb{R}^{d \times r}$、$A \in \mathbb{R}^{r \times k}$ [S1]。')[0]
        self.assertEqual(unit['subject_status'],'explicit')
        self.assertIsNone(unit['subject_context'])
        self.assertEqual([s['text'] for s in unit['subject_resolution']['entity_spans']],['B','A'])

    def test_coordinated_math_keeps_w0_and_delta_w(self):
        unit=make(r'其中 $W_0$ 与 $\Delta W = BA$ 同时作用于 $x$ [S1]。')[0]
        self.assertEqual([s['text'] for s in unit['subject_resolution']['entity_spans']],['W_0',r'\Delta W'])

    def test_trainable_pair_does_not_inherit_frozen_parameter(self):
        unit=make(r'$W_0$被冻结；而 $U \in R^a$、$V \in R^b$ 为可训练参数 [S1]。')[-1]
        self.assertEqual(unit['subject_status'],'explicit')
        self.assertIsNone(unit['subject_context'])
        self.assertEqual([s['text'] for s in unit['subject_resolution']['entity_spans']],['U','V'])

    def test_rank_relation_with_alternate_symbol(self):
        for formula,symbol in ((r'r \ll \min(d,k)','r'),(r'q < m','q'),(r'\rho \leq n',r'\rho')):
            with self.subTest(formula=formula):
                unit=make('且秩 $'+formula+'$ [S1]。')[0]
                self.assertEqual(unit['subject_status'],'explicit')
                self.assertEqual(unit['subject_resolution']['entity_spans'][0]['text'],symbol)

    def test_operation_objects_not_grammatical_subject(self):
        unit=make(r'仅更新可训练参数 $P$ 和 $Q$ [S1]。')[0]
        self.assertEqual(unit['subject_status'],'explicit')
        self.assertEqual(unit['subject_resolution']['rule'],'explicit_operation_objects')
        self.assertEqual([s['text'] for s in unit['subject_resolution']['entity_spans']],['P','Q'])
        self.assertIn('仅更新',unit['text'])

    def test_ambiguous_or_malformed_math_stays_unresolved(self):
        for text in (r'其中 $A$ 或 $B$ 是参数 [S1]。',
                     r'且秩 $r ? k$ [S1]。', '仅更新这些参数 [S1]。',
                     '仅更新可训练参数 $P 和 Q [S1]。'):
            with self.subTest(text=text):
                unit=make(text)[0]
                self.assertIsNone(unit['subject_context'])
                self.assertEqual(unit['subject_status'],'unresolved')

    def test_explicit_classification_is_not_local_semantic_support(self):
        from tests.integration.anchored_claim_audit import local_decision
        unit=make(r'仅更新参数 $P$ 和 $Q$ [S1]。')[0]
        self.assertIsNone(local_decision(unit))
        self.assertNotIn('semantic_verdict',unit)

    def test_mixed_conjunction_alternative_does_not_select_subset(self):
        unit=make(r'其中 $A$ 与 $B$ 或 $C$ 是参数 [S1]。')[0]
        self.assertEqual(unit['subject_status'],'unresolved')

    def test_rejected_single_subject_cannot_leak_to_next_clause(self):
        unit=make(r'其中 $A$ 或 $B$ 是参数，且不更新梯度 [S1]。')[-1]
        self.assertIsNone(unit['subject_context'])
        self.assertEqual(unit['subject_status'],'unresolved')


class PreservationTests(unittest.TestCase):
    # AC-3303 / AC-3305
    def test_original_claims_sources_anchors_and_v3_inputs_unchanged(self):
        answer='当前检索证据未提及方法组合；仅描述两种方法 [S1]。'
        original=prepare_v3(answer,split_claims(answer,SOURCES)); frozen=copy.deepcopy(original)
        after=prepare_units(answer,original)
        self.assertEqual(original,frozen)
        for a,b in zip(original,after):
            for field in ('id','text','start','end','citation_ids','evidence','anchors','anchor_max_chars'):
                self.assertEqual(a[field],b[field])
        self.assertEqual(after[-1]['subject_resolution']['v3_status'],'unresolved')

    def test_old_resolved_cases_keep_identical_request(self):
        answer=r'$ W_0 \in R^{d \times k} $ 被冻结，不参与梯度更新 [S1]。'
        old=prepare_v3(answer,split_claims(answer,SOURCES)); new=prepare_units(answer,old)
        for a,b in zip(old,new): self.assertEqual(judge_messages('q',a),judge_messages('q',b))

    def test_preparation_is_deterministic_and_rejects_bad_offsets(self):
        answer='图像重建任务：恢复输入，并预测像素 [S1]。'
        old=split_claims(answer,SOURCES)
        self.assertEqual(prepare_units(answer,old),prepare_units(answer,old))
        bad=copy.deepcopy(old); bad[0]['start']+=1
        with self.assertRaises(ValueError): prepare_units(answer,bad)

    def test_all_new_spans_match_original_answer(self):
        answer=r'其中 $U \in R^m$、$V \in R^n$ [S1]。当前检索证据描述方法；仅描述实验 [S1]。'
        for u in make(answer):
            spans=u['subject_resolution']['entity_spans']
            if u['subject_context']: spans=spans+[u['subject_context']]
            for s in spans: self.assertEqual(answer[s['start']:s['end']],s['text'])


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    # AC-3305: refined input cannot reuse a different v3 request's cached result.
    async def test_refined_hints_change_cache_identity_and_budget_still_applies(self):
        answer='当前检索证据描述方法；仅描述实验 [S1]。'
        old=prepare_v3(answer,split_claims(answer,SOURCES))[-1]; new=make(answer)[-1]
        cases=lambda u:[dict(id='case',query='q',units=[u])]
        client=AsyncMock()
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with self.assertRaises(ValueError): await run_units(client,'m',cases(new),out,0)
            from tests.integration.anchored_claim_audit import _fingerprint
            self.assertNotEqual(_fingerprint('m','q',old),_fingerprint('m','q',new))
            (out/f"result-case-{old['id']}.json").write_text(json.dumps(dict(
                request_sha256=_fingerprint('m','q',old),status='error')),encoding='utf-8')
            with self.assertRaises(ValueError): await run_units(client,'m',cases(new),out,1)
            client.chat.completions.create.assert_not_awaited()


class PreparationTests(unittest.IsolatedAsyncioTestCase):
    # AC-3304 / AC-3305: no network, write-once packet and strict preflight.
    def fixture(self, root, runner):
        previous=root/'v3'; previous.mkdir()
        for name in runner.FREEZE_PATHS:
            path=root/name; path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('# fixture',encoding='utf-8')
        sentinel=root/'frozen.txt'; sentinel.write_text('unchanged',encoding='utf-8')
        answer='当前检索证据描述实验；仅描述设置 [S1]。'
        cases=[dict(id='A01',query='q',answer=answer,fixed_refusal=False,
                    refusal_correct=True,units=prepare_v3(answer,split_claims(answer,SOURCES)))]
        from tests.integration.evaluate_multipaper_claims import sha
        (previous/'inputs.json').write_text(json.dumps(cases),encoding='utf-8')
        (previous/'manifest.json').write_text(json.dumps({'experiment':'multipaper-claim-audit-v3',
            'file_sha256':{'frozen.txt':sha(sentinel),'v3/inputs.json':sha(previous/'inputs.json')}}),encoding='utf-8')
        return previous,cases,sentinel

    async def test_prepare_offline_write_once_and_all_human_decisions_pending(self):
        from tests.integration import evaluate_multipaper_claims_v31 as runner
        from tests.integration.evaluate_multipaper_claims import read,verify_hashes
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); previous,cases,sentinel=self.fixture(root,runner); out=root/'v31'
            original=(previous/'inputs.json').read_bytes()
            with patch.object(runner,'ROOT',root), patch('socket.socket.connect',side_effect=AssertionError('no network')):
                stats=runner.prepare(out,previous)
                self.assertEqual(stats['actual_provider_requests'],0)
                self.assertFalse(stats['semantic_scores_available'])
                self.assertEqual(stats['changed_requests'],1)
                self.assertEqual(stats['total_units'],len(cases[0]['units']))
                self.assertEqual(stats['anchor_occurrences'],sum(len(u['anchors']) for u in cases[0]['units']))
                self.assertEqual((previous/'inputs.json').read_bytes(),original)
                review=read(out/'subject-review.json')
                self.assertEqual(review['status'],'PENDING_NOT_GOLD')
                for row in review['items']:
                    self.assertIsNone(row['subject_approved']); self.assertIsNone(row['semantic_verdict'])
                manifest=read(out/'manifest.json'); verify_hashes(root,manifest['file_sha256'])
                self.assertIn('v31/subject-review.json',manifest['file_sha256'])
                self.assertFalse(list(out.glob('attempt-*.json')))
                with self.assertRaises(FileExistsError): runner.prepare(out,previous)
                sentinel.write_text('drift',encoding='utf-8')
                with self.assertRaises(ValueError): runner.prepare(root/'second',previous)
                self.assertFalse((root/'second').exists())

    async def test_run_requires_exact_budget_before_config_or_network(self):
        from tests.integration import evaluate_multipaper_claims_v31 as runner
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); previous,_,_=self.fixture(root,runner); out=root/'v31'
            with patch.object(runner,'ROOT',root):
                stats=runner.prepare(out,previous)
                with patch('tests.integration.run_multipaper_journey.api',side_effect=AssertionError('config forbidden')):
                    for budget in (None,True,0,stats['planned_provider_requests']+1):
                        with self.assertRaises(ValueError): await runner.run(budget,out)
                    (out/'summary.json').write_text('{}',encoding='utf-8')
                    with self.assertRaises(FileExistsError): await runner.run(stats['planned_provider_requests'],out)

    async def test_manifest_protocol_drift_and_input_drift_block_live_run(self):
        from tests.integration import evaluate_multipaper_claims_v31 as runner
        from tests.integration.evaluate_multipaper_claims import read
        for mutation in ('settings','input','experiment','budget'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); previous,_,_=self.fixture(root,runner); out=root/'v31'
                with patch.object(runner,'ROOT',root):
                    stats=runner.prepare(out,previous)
                    manifest=read(out/'manifest.json')
                    if mutation=='settings': manifest['max_retries']=1
                    elif mutation=='input': (out/'inputs.json').write_text('[]',encoding='utf-8')
                    elif mutation=='experiment': manifest['experiment']='wrong-version'
                    else: manifest['planned_provider_requests']=0
                    (out/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
                    with patch('tests.integration.run_multipaper_journey.api',side_effect=AssertionError('config forbidden')):
                        with self.assertRaises(ValueError): await runner.run(stats['planned_provider_requests'],out)


if __name__ == '__main__': unittest.main()
