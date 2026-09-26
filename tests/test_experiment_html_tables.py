import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from scripts.experiment_html_tables import PROMPT, StreamSettings, StreamingTableClient, collect_stream, run_ab
from scripts.experiment_vlm_tables import sha, write_json


HTML = '<table><tr><td>0.18</td></tr></table>'


def event(text=None, finish=None, usage=None):
    return NS(model='test-model', id='test-response', usage=usage, choices=[
        NS(index=0, delta=NS(content=text, refusal=None), finish_reason=finish)])


class FakeStream:
    def __init__(self, items, hang=False):
        self.items = items
        self.hang = hang
        self.closed = False

    async def __aiter__(self):
        for item in self.items:
            if isinstance(item, Exception):
                raise item
            yield item
        if self.hang:
            await asyncio.Event().wait()

    async def close(self):
        self.closed = True


class FakeSDK:
    def __init__(self, stream):
        self.stream, self.args = stream, None
        self.chat = NS(completions=self)

    async def create(self, **kwargs):
        self.args = kwargs
        return self.stream


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_sdk_uses_separate_timeouts_and_no_retries(self):
        """AC-HTML-903/904: ensure settings actually reach the SDK constructor."""
        from unittest.mock import patch
        import os
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / '.env'
            conf.write_text('API_KEY=local-not-real\nMODEL_URL=https://example.test/v1\nMODEL_NAME=qwen3-vl-plus\n')
            with patch.dict(os.environ, {}, clear=True), patch('openai.AsyncOpenAI') as sdk:
                client = StreamingTableClient(conf, 'ocr_html', StreamSettings())
                args = sdk.call_args.kwargs
                self.assertEqual(args['max_retries'], 0)
                self.assertEqual((args['timeout'].connect, args['timeout'].read,
                                  args['timeout'].write, args['timeout'].pool), (20, 60, 30, 10))
                self.assertEqual(client.model, 'qwen3.5-ocr')
                self.assertNotIn('local-not-real', json.dumps(client.metadata))

    async def test_sdk_contract_usage_and_timing(self):
        """AC-HTML-903: same HTML prompt, no JSON constraints, usage-only final event."""
        for ocr in (False, True):
            stream = FakeStream([event('<table>'), event('<tr><td>x</td></tr></table>', 'stop'),
                NS(choices=[], usage=NS(model_dump=lambda: {'total_tokens': 20}), model='test', id='id')])
            sdk = FakeSDK(stream)
            ticks = iter([0.0, 0.2, 0.5, 0.9, 1.0])
            result = await collect_stream(sdk, 'test', b'png', ocr, StreamSettings(), clock=lambda: next(ticks))
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['usage']['total_tokens'], 20)
            self.assertEqual(result['first_text_seconds'], .2)
            self.assertEqual(result['max_event_gap_seconds'], .4)
            self.assertEqual(result['max_text_gap_seconds'], .3)
            self.assertTrue(stream.closed)
            self.assertTrue(sdk.args['stream'])
            self.assertEqual(sdk.args['max_tokens'], 8192)
            self.assertNotIn('response_format', sdk.args)
            self.assertEqual(sdk.args['messages'][0]['role'], 'user')
            self.assertEqual(sdk.args['messages'][0]['content'][0]['text'], PROMPT)
            self.assertEqual('extra_body' in sdk.args, not ocr)

    async def test_deadline_keeps_partial_and_closes_stream(self):
        """AC-HTML-903: total deadline is independent of ongoing/read events."""
        stream = FakeStream([event('<table>')], hang=True)
        result = await collect_stream(FakeSDK(stream), 'test', b'png', False,
                                      StreamSettings(total_seconds=.02))
        self.assertEqual(result['status'], 'request_failed')
        self.assertEqual(result['error_type'], 'TotalDeadlineExceeded')
        self.assertEqual(result['content'], '<table>')
        self.assertTrue(stream.closed)

    async def test_read_error_is_redacted_partial_and_truncated_are_invalid(self):
        import httpx
        for tail, expected in ((httpx.ReadTimeout('do-not-save-secret'), 'request_failed'),
                               (event('', 'length'), 'incomplete'), (event(), 'incomplete')):
            stream = FakeStream([event(HTML), tail])
            result = await collect_stream(FakeSDK(stream), 'test', b'png', False, StreamSettings())
            self.assertEqual(result['status'], expected)
            self.assertEqual(result['content'], HTML)
            self.assertNotIn('do-not-save-secret', json.dumps(result))
            self.assertTrue(stream.closed)

    async def test_real_local_sse_sdk_transport(self):
        """AC-HTML-906: real HTTP/SSE through SDK, not only object mocks. No paid API."""
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from openai import AsyncOpenAI
        import httpx
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                body = ''.join('data: ' + json.dumps(data) + '\n\n' for data in [
                    {'id': 'local', 'model': 'test', 'choices': [{'index': 0, 'delta': {'content': HTML}, 'finish_reason': None}]},
                    {'id': 'local', 'model': 'test', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
                    {'id': 'local', 'model': 'test', 'choices': [], 'usage': {'prompt_tokens': 3, 'completion_tokens': 4, 'total_tokens': 7}},
                ]) + 'data: [DONE]\n\n'
                encoded = body.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            async with AsyncOpenAI(api_key='local-test-only', base_url=f'http://127.0.0.1:{server.server_port}/v1',
                                   max_retries=0, http_client=httpx.AsyncClient(trust_env=False)) as sdk:
                response = await collect_stream(sdk, 'test', b'png', True, StreamSettings())
            self.assertEqual(response['status'], 'completed')
            self.assertEqual(response['content'], HTML)
            self.assertEqual(response['usage']['total_tokens'], 7)
            self.assertEqual(len(requests), 1)
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close(); thread.join(timeout=2)


def prepared(root, count=3):
    prep = root / 'prepared'; prep.mkdir()
    items = []
    for i in range(count):
        case = f'page-{i}'; dest = prep / case; dest.mkdir()
        (dest / 'crop.png').write_bytes(b'png-test-fixture')
        (dest / 'baseline.html').write_text(HTML)
        items.append({'id': case, 'page': case + '.png', 'crop': case + '/crop.png',
                      'crop_sha256': sha(dest / 'crop.png'), 'baseline_sha256': sha(dest / 'baseline.html')})
    write_json(prep / 'manifest.json', {'source': str(root / 'source'), 'images': str(root / 'images'), 'results': items})
    return prep


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_budget_journal_and_preservation(self):
        """AC-HTML-904: interleaved arms, attempted journal before calls, immutable inputs."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prep = prepared(root); out = root / 'run'; calls = []
            before = {p: p.read_bytes() for p in prep.rglob('*') if p.is_file()}
            async def client(crop, checkpoint):
                journal = json.loads((out / 'summary.json').read_text())
                calls.append(crop)
                self.assertEqual(journal['calls_attempted'], len(calls))
                self.assertEqual(journal['results'][-1]['status'], 'attempted_no_response_yet')
                return {'status': 'completed', 'content': HTML, 'finish_reason': 'stop', 'total_seconds': .1}
            result = await run_ab(prep, out, {'generic_html': client, 'ocr_html': client}, max_calls=2)
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(result['results']), 6)
            self.assertEqual([r['arm'] for r in result['results'][:2]], ['generic_html', 'ocr_html'])
            self.assertEqual(sum(r['status'] == 'skipped_budget' for r in result['results']), 4)
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            with self.assertRaises(ValueError):
                await run_ab(prep, out, {'generic_html': client, 'ocr_html': client})

    async def test_auth_stops_one_arm_and_invalid_tables_keep_baseline(self):
        """AC-HTML-904/905: auth failures, invalid HTML and skips retained in denominator."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prep = prepared(root)
            async def auth(*args):
                return {'status': 'request_failed', 'http_status': 401, 'error_type': 'AuthenticationError', 'content': ''}
            async def bad(*args):
                return {'status': 'completed', 'content': '<table>', 'finish_reason': 'stop'}
            result = await run_ab(prep, root / 'run', {'generic_html': auth, 'ocr_html': bad})
            self.assertEqual(result['calls_attempted'], 4)
            self.assertEqual(sum(r['status'] == 'skipped_arm_unavailable' for r in result['results']), 2)
            self.assertEqual(sum(r['status'] == 'invalid_candidate_baseline_retained' for r in result['results']), 3)
            self.assertFalse(list((root / 'run').rglob('candidate.html')))

    async def test_hash_and_unique_id_preflight(self):
        """AC-HTML-904: no network if crop/baseline/id integrity fails."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prep = prepared(root)
            async def never(*args):
                self.fail('Network must not be called')
            (prep / 'page-1/crop.png').write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                await run_ab(prep, root / 'run', {'generic_html': never, 'ocr_html': never})
            self.assertFalse((root / 'run').exists())

    async def test_full_six_call_budget_and_duplicate_page_rejection(self):
        """AC-HTML-904: no hidden seventh call or duplicated case."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prep = prepared(root); calls = []
            async def valid(crop, checkpoint):
                calls.append(crop)
                return {'status': 'completed', 'content': HTML, 'finish_reason': 'stop'}
            clients = {'generic_html': valid, 'ocr_html': valid}
            result = await run_ab(prep, root / 'run', clients)
            self.assertEqual(len(calls), 6)
            self.assertEqual(result['calls_attempted'], 6)
            with self.assertRaises(ValueError):
                await run_ab(prep, root / 'too-many', clients, max_calls=7)
            m = json.loads((prep / 'manifest.json').read_text())
            m['results'][1]['id'] = m['results'][0]['id']
            write_json(prep / 'manifest.json', m)
            with self.assertRaises(ValueError):
                await run_ab(prep, root / 'duplicate', clients)
            self.assertEqual(len(calls), 6)


if __name__ == '__main__':
    unittest.main()
