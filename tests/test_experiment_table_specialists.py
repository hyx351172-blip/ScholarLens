import asyncio
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from scripts.experiment_table_specialists import (
    native_endpoint, native_payload, collect_native, extract_paddle_html,
    run_arm, sha, write_json,
)

HTML = '<table><tr><td>1.2</td></tr></table>'


def prep(root):
    prepared = root / 'prepared'
    records = []
    for n in range(3):
        folder = prepared / f'page-{n}'; folder.mkdir(parents=True)
        (folder / 'crop.png').write_bytes(b'png')
        (folder / 'baseline.html').write_text(HTML)
        records.append({'id': folder.name, 'page': folder.name + '.png',
                        'crop': folder.name + '/crop.png',
                        'crop_sha256': sha(folder / 'crop.png'),
                        'baseline_sha256': sha(folder / 'baseline.html')})
    write_json(prepared / 'manifest.json', {'source': str(root / 'source'),
               'images': str(root / 'images'), 'results': records})
    return prepared


class ContractTests(unittest.TestCase):
    def test_paddle_unicode_workspace_uses_same_relative_cache(self):
        """AC-1001, AC-1006: fix real Windows model loader seam without moving files."""
        from scripts.experiment_table_specialists import ROOT, paddle_cache_path
        cache = ROOT / 'backend/data/benchmarks/model_cache/tablemagic'
        relative = paddle_cache_path(cache)
        self.assertTrue(relative.isascii())
        self.assertEqual((ROOT / relative).resolve(), cache.resolve())

    def test_native_client_config_and_redaction(self):
        """AC-1002: actual client factory settings, not just payload tests."""
        from unittest.mock import patch
        import os
        from scripts.experiment_table_specialists import NativeClient
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            path.write_text('API_KEY=local-secret\nMODEL_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n')
            with patch.dict(os.environ, {}, clear=True), patch('httpx.AsyncClient') as http, patch('httpx.AsyncHTTPTransport') as transport:
                client = NativeClient(path)
                args = http.call_args.kwargs
                self.assertFalse(args['follow_redirects'])
                self.assertEqual(transport.call_args.kwargs['retries'], 0)
                self.assertEqual((args['timeout'].connect, args['timeout'].read,
                                  args['timeout'].write, args['timeout'].pool), (20, 60, 30, 10))
                self.assertNotIn('local-secret', json.dumps(client.metadata))

    def test_official_endpoints_only(self):
        """AC-1002: same official origin, never leak keys to arbitrary URLs."""
        suffix = '/api/v1/services/aigc/multimodal-generation/generation'
        self.assertEqual(native_endpoint('https://dashscope.aliyuncs.com/compatible-mode/v1'),
                         'https://dashscope.aliyuncs.com' + suffix)
        self.assertEqual(native_endpoint('https://test.cn-beijing.maas.aliyuncs.com/api/v1'),
                         'https://test.cn-beijing.maas.aliyuncs.com' + suffix)
        for bad in ('http://dashscope.aliyuncs.com/compatible-mode/v1',
                    'https://dashscope.aliyuncs.com.attacker.test/v1',
                    'https://example.aliyuncs.com/compatible-mode/v1',
                    'https://key@dashscope.aliyuncs.com/api/v1',
                    'https://dashscope.aliyuncs.com/api/v1?key=secret',
                    'https://dashscope.aliyuncs.com:8443/api/v1',
                    'https://dashscope.aliyuncs.com/unrecognized'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                native_endpoint(bad)

    def test_payload_has_no_prompt_or_gold(self):
        """AC-1002: built-in task, image only, bounded max tokens."""
        body = native_payload(b'png', 'qwen3.5-ocr')
        self.assertEqual(body['parameters']['ocr_options'], {'task': 'table_parsing'})
        self.assertTrue(body['parameters']['incremental_output'])
        content = body['input']['messages'][0]['content']
        self.assertEqual(len(content), 1)
        self.assertNotIn('text', content[0])
        self.assertEqual(body['parameters']['max_tokens'], 8192)

    def test_paddle_exactly_one_table_preserve_markup(self):
        """AC-1001, AC-1004: no largest-table guessing or silent repair."""
        self.assertEqual(extract_paddle_html({'res': {'table_res_list': [{'pred_html': HTML}]}}), HTML)
        for raw in ({}, {'res': {'table_res_list': []}},
                    {'res': {'table_res_list': [{'pred_html': HTML}] * 2}},
                    {'res': {'table_res_list': [{'pred_html': 123}]}}):
            with self.assertRaises(ValueError):
                extract_paddle_html(raw)


def native_event(text='', finish=None):
    return {'request_id': 'local-id', 'output': {'choices': [{'finish_reason': finish,
               'message': {'content': [{'text': text}]}}]},
            'usage': {'input_tokens': 3, 'output_tokens': 4, 'total_tokens': 7}}


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_native_http_sse(self):
        """AC-1006: real localhost HTTP, multiline SSE and incrementality."""
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                requests.append((self.headers['X-DashScope-SSE'],
                    json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                data = ': heartbeat\n\n' + ''.join('event: result\ndata: ' + json.dumps(e) + '\n\n'
                    for e in [native_event('<table>'), native_event('<tr><td>1.2</td></tr></table>', 'stop')])
                raw = data.encode(); self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            async with httpx.AsyncClient(trust_env=False) as http:
                result = await collect_native(http, f'http://127.0.0.1:{server.server_port}',
                                              'test-not-real', b'png', 'test-model')
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['content'], HTML)
            self.assertEqual(result['usage']['total_tokens'], 7)
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0][0], 'enable')
            self.assertNotIn('test-not-real', json.dumps(result))
        finally:
            await asyncio.to_thread(server.shutdown); server.server_close(); thread.join(2)

    async def test_failures_partial_content_and_redaction(self):
        """AC-1002, AC-1004: HTTP failures, absent stop, length, provider SSE errors."""
        for status, events, expected in [
            (401, [], 'request_failed'),
            (200, [native_event(HTML)], 'incomplete'),
            (200, [native_event(HTML, 'length')], 'incomplete'),
            (200, [native_event('<table>'), {'code': 'DataInspectionFailed', 'message': 'secret'}], 'request_failed')]:
            def handler(request):
                body = ''.join('data: ' + json.dumps(e) + '\n\n' for e in events)
                return httpx.Response(status, headers={'Content-Type': 'text/event-stream'}, text=body)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                result = await collect_native(http, 'https://local.test', 'secret', b'png', 'test')
            self.assertEqual(result['status'], expected)
            self.assertNotIn('secret', json.dumps(result))
            if events:
                self.assertTrue(result['content'].startswith('<table>'))

    async def test_total_deadline_and_size_limit(self):
        """AC-1002: no unbounded wait or output allocation."""
        class Slow(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield ('data: ' + json.dumps(native_event('<table>')) + '\n\n').encode()
                await asyncio.Event().wait()
        async def handler(request):
            return httpx.Response(200, headers={'Content-Type': 'text/event-stream'}, stream=Slow())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            result = await collect_native(http, 'https://local.test', 'secret', b'png', 'test', total_seconds=.03)
        self.assertEqual(result['error_type'], 'TotalDeadlineExceeded')
        self.assertEqual(result['content'], '<table>')
        def huge(request):
            return httpx.Response(200, headers={'Content-Type': 'text/event-stream'},
                text='data: ' + json.dumps(native_event('x' * 1_000_001)) + '\n\n')
        async with httpx.AsyncClient(transport=httpx.MockTransport(huge)) as http:
            result = await collect_native(http, 'https://local.test', 'secret', b'png', 'test')
        self.assertEqual(result['status'], 'request_failed')


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_paddle_worker_timeout_and_process_contract(self):
        """AC-1001, AC-1006: bounded isolated worker, safe logs and same cache location."""
        import subprocess
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        from scripts.experiment_table_specialists import PaddleClient, ROOT
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            client = PaddleClient(Path(sys.executable), ROOT / 'backend/data/benchmarks/model_cache/tablemagic')
            with patch('scripts.experiment_table_specialists.subprocess.run',
                       side_effect=subprocess.TimeoutExpired('sensitive-command', 600)) as run:
                result = await client(dest / 'crop.png', dest, None)
                self.assertEqual(run.call_args.kwargs['timeout'], 600)
                self.assertEqual(run.call_args.kwargs['cwd'], ROOT)
                self.assertTrue(run.call_args.kwargs['env']['PADDLE_PDX_CACHE_HOME'].isascii())
                self.assertEqual(result['error_type'], 'PaddleDeadlineExceeded')
                self.assertNotIn('sensitive-command', json.dumps(result))
            with patch('scripts.experiment_table_specialists.subprocess.run', return_value=SimpleNamespace(returncode=1)):
                result = await client(dest / 'crop.png', dest, None)
                self.assertEqual(result['error_type'], 'PaddleWorkerFailed')

    async def test_budget_journal_and_immutable_inputs(self):
        """AC-1003: zero hidden retries; record attempted before invoking."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prepared = prep(root); out = root / 'run'; calls = []
            original = {p: p.read_bytes() for p in prepared.rglob('*') if p.is_file()}
            async def client(crop, dest, checkpoint):
                calls.append(crop)
                state = json.loads((out / 'summary.json').read_text())
                self.assertEqual(state['calls_attempted'], len(calls))
                self.assertEqual(state['results'][-1]['status'], 'attempted_no_response_yet')
                return {'status': 'completed', 'finish_reason': 'stop', 'content': HTML}
            result = await run_arm(prepared, out, 'qwen_native', client, max_calls=1)
            self.assertEqual(len(calls), 1)
            self.assertEqual([r['status'] for r in result['results']],
                             ['valid_candidate_review_required', 'skipped_budget', 'skipped_budget'])
            self.assertEqual(original, {p: p.read_bytes() for p in original})
            with self.assertRaises(ValueError):
                await run_arm(prepared, out, 'qwen_native', client)
            with self.assertRaises(ValueError):
                await run_arm(prepared, root / 'over-budget', 'qwen_native', client, max_calls=4)

    async def test_preflight_tamper_and_path_escape(self):
        """AC-1003: malformed inputs must fail before client execution."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prepared = prep(root)
            async def never(*args):
                self.fail('Client should not run')
            m = json.loads((prepared / 'manifest.json').read_text())
            m['results'][0]['crop'] = '../outside.png'; write_json(prepared / 'manifest.json', m)
            with self.assertRaises(ValueError):
                await run_arm(prepared, root / 'run', 'pp_tablemagic', never)
            self.assertFalse((root / 'run').exists())
            m['results'][0]['crop'] = 'page-0/crop.png'; write_json(prepared / 'manifest.json', m)
            (prepared / 'page-1/baseline.html').write_text('changed')
            with self.assertRaises(ValueError):
                await run_arm(prepared, root / 'run', 'pp_tablemagic', never)

    async def test_auth_short_circuit_and_invalid_fallback(self):
        """AC-1003, AC-1004: don't repeatedly pay on auth errors; no invalid output."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prepared = prep(root)
            async def denied(*args):
                return {'status': 'request_failed', 'http_status': 403, 'content': ''}
            result = await run_arm(prepared, root / 'auth', 'qwen_native', denied)
            self.assertEqual(result['calls_attempted'], 1)
            async def invalid(*args):
                return {'status': 'completed', 'finish_reason': 'stop', 'content': '<table>'}
            result = await run_arm(prepared, root / 'bad', 'pp_tablemagic', invalid)
            self.assertTrue(all(r['status'] == 'invalid_candidate_baseline_retained' for r in result['results']))
            self.assertFalse(list((root / 'bad').rglob('candidate.html')))


if __name__ == '__main__':
    unittest.main()
