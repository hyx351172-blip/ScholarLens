"""Offline table specialists, immutable crops, no gold and no production writes.

Paddle runs in a bounded child process in its own environment. Native DashScope
uses the documented image-only built-in task, not the v6 custom prompt.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
# Pure parser only: don't pull production PDF/model dependencies into this venv.
sys.path.insert(0, str(ROOT / 'backend/Information-Extraction/unified/parsers'))
from html_table_candidate import parse_html_table

NATIVE_PATH = '/api/v1/services/aigc/multimodal-generation/generation'
MAX_CHARS = 1_000_000
PP_OPTIONS = dict(device='cpu', cpu_threads=4, enable_mkldnn=False,
                  use_doc_orientation_classify=False, use_doc_unwarping=False,
                  use_layout_detection=False,
                  wired_table_structure_recognition_model_name='SLANeXt_wired',
                  wireless_table_structure_recognition_model_name='SLANeXt_wireless',
                  text_detection_model_name='PP-OCRv5_server_det',
                  text_recognition_model_name='PP-OCRv5_server_rec')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    # Atomic checkpoints preserve the prior journal if a process is interrupted.
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_endpoint(base):
    parts = urlsplit(base.rstrip('/').removesuffix('/chat/completions'))
    known = parts.hostname in {'dashscope.aliyuncs.com', 'dashscope-intl.aliyuncs.com',
                               'dashscope-us.aliyuncs.com'}
    workspace = re.fullmatch(r'[a-z0-9-]+\.(cn-beijing|ap-southeast-1|us-east-1)\.maas\.aliyuncs\.com',
                             parts.hostname or '')
    if (parts.scheme != 'https' or not (known or workspace) or parts.username or parts.password
            or parts.query or parts.fragment or parts.port not in (None, 443)
            or parts.path not in ('/compatible-mode/v1', '/api/v1', NATIVE_PATH)):
        raise ValueError('Configure a recognized official Aliyun HTTPS base URL')
    return f'https://{parts.netloc}{NATIVE_PATH}'


def native_payload(image, model, max_tokens=8192):
    return {'model': model, 'input': {'messages': [{'role': 'user', 'content': [{
        'image': 'data:image/png;base64,' + base64.b64encode(image).decode('ascii'),
        'min_pixels': 3072, 'max_pixels': 8388608, 'enable_rotate': False}]}]},
        'parameters': {'ocr_options': {'task': 'table_parsing'},
                       'incremental_output': True, 'max_tokens': max_tokens}}


async def collect_native(http, endpoint, key, image, model, *, total_seconds=300, checkpoint=None):
    start = time.monotonic()
    result = {'status': 'incomplete', 'content': '', 'model': model, 'response_format': 'html',
              'usage': None, 'finish_reason': None, 'response_id': None, 'events': 0,
              'first_event_seconds': None, 'first_text_seconds': None}
    last_checkpoint = -1

    def consume_event(data):
        nonlocal last_checkpoint
        if data == '[DONE]':
            return
        obj = json.loads(data)
        if obj.get('code') or obj.get('status_code', 200) not in (200, '200'):
            # Do not persist arbitrary provider error bodies or request URLs.
            raise ValueError('NativeProviderError')
        now = time.monotonic() - start
        result['events'] += 1
        if result['first_event_seconds'] is None:
            result['first_event_seconds'] = round(now, 4)
        result['response_id'] = obj.get('request_id') or result['response_id']
        if obj.get('usage') is not None:
            result['usage'] = obj['usage']
        output = obj.get('output') or {}
        choices = output.get('choices') or []
        if len(choices) > 1:
            raise ValueError('MultipleChoices')
        for choice in choices:
            finish = choice.get('finish_reason') or output.get('finish_reason')
            if finish and finish != 'null':
                result['finish_reason'] = finish
            content = choice.get('message', {}).get('content', [])
            if not isinstance(content, list):
                raise ValueError('UnexpectedContent')
            for part in content:
                text = part.get('text', '')
                if not isinstance(text, str) or len(text) + len(result['content']) > MAX_CHARS:
                    raise ValueError('ResponseSizeLimit')
                if text and result['first_text_seconds'] is None:
                    result['first_text_seconds'] = round(now, 4)
                result['content'] += text
        if checkpoint and now - last_checkpoint >= 1:
            checkpoint({**result, 'status': 'streaming', 'elapsed_seconds': round(now, 4)})
            last_checkpoint = now

    async def consume():
        async with http.stream('POST', endpoint, headers={'Authorization': 'Bearer ' + key,
                'X-DashScope-SSE': 'enable'}, json=native_payload(image, model)) as response:
            result['http_status'] = response.status_code
            response.raise_for_status()
            if 'text/event-stream' not in response.headers.get('content-type', ''):
                raise ValueError('ExpectedNativeSSE')
            # Decode bytes rather than aiter_lines so even an endless no-newline
            # response is bounded before allocating an unbounded line buffer.
            import codecs
            decoder = codecs.getincrementaldecoder('utf-8')()
            pending, event_lines, wire_bytes = '', [], 0
            async for raw in response.aiter_bytes():
                wire_bytes += len(raw)
                if wire_bytes > 16_000_000:
                    raise ValueError('WireSizeLimit')
                pending += decoder.decode(raw)
                if len(pending) > 2_000_000:
                    raise ValueError('EventSizeLimit')
                while '\n' in pending:
                    line, pending = pending.split('\n', 1)
                    line = line.rstrip('\r')
                    if not line:
                        if event_lines:
                            consume_event('\n'.join(event_lines)); event_lines = []
                    elif line.startswith('data:'):
                        event_lines.append(line[5:].lstrip(' '))
                        if sum(map(len, event_lines)) > 2_000_000:
                            raise ValueError('EventSizeLimit')
            pending += decoder.decode(b'', final=True)
            if pending.strip() or event_lines:
                raise ValueError('TruncatedSSEFrame')
        if result['finish_reason'] == 'stop' and result['content']:
            result['status'] = 'completed'

    try:
        await asyncio.wait_for(consume(), total_seconds)
    except TimeoutError:
        result.update(status='request_failed', error_type='TotalDeadlineExceeded')
    except Exception as exc:
        result.update(status='request_failed', error_type=type(exc).__name__)
    result['total_seconds'] = round(time.monotonic() - start, 4)
    result['output_chars'] = len(result['content'])
    return result


class NativeClient:
    def __init__(self, env_file):
        import httpx
        from dotenv import dotenv_values
        conf = {**os.environ, **{k: v for k, v in dotenv_values(env_file).items() if v}}
        self.key = (conf.get('TABLE_OCR_API_KEY') or conf.get('DASHSCOPE_API_KEY')
                    or conf.get('VLM_REPAIR_API_KEY') or conf.get('API_KEY'))
        base = (conf.get('TABLE_OCR_NATIVE_BASE_URL') or conf.get('DASHSCOPE_NATIVE_BASE_URL')
                or conf.get('TABLE_OCR_BASE_URL') or conf.get('VLM_REPAIR_BASE_URL') or conf.get('MODEL_URL') or '')
        self.endpoint = native_endpoint(base)
        self.model = conf.get('TABLE_OCR_MODEL_NAME') or 'qwen3.5-ocr'
        if not self.key:
            raise ValueError('Missing local API key')
        self.http = httpx.AsyncClient(follow_redirects=False, transport=httpx.AsyncHTTPTransport(retries=0),
            timeout=httpx.Timeout(connect=20, read=60, write=30, pool=10))
        self.metadata = {'model': self.model, 'task': 'table_parsing', 'custom_prompt': False,
                         'endpoint_sha256': hashlib.sha256(self.endpoint.encode()).hexdigest(),
                         'max_tokens': 8192, 'retries': 0, 'total_deadline_seconds': 300,
                         'timeouts': {'connect': 20, 'read': 60, 'write': 30, 'pool': 10}}

    async def __call__(self, crop, dest, checkpoint):
        return await collect_native(self.http, self.endpoint, self.key, crop.read_bytes(), self.model,
                                    checkpoint=checkpoint)

    async def close(self):
        await self.http.aclose()


def extract_paddle_html(raw):
    if not isinstance(raw, dict):
        raise ValueError('Expected Paddle result dictionary')
    tables = raw.get('res', raw).get('table_res_list')
    if not isinstance(tables, list) or len(tables) != 1:
        raise ValueError('Expected exactly one Paddle table result')
    text = tables[0].get('pred_html')
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
        raise ValueError('Missing or oversized Paddle table HTML')
    return text


def paddle_cache_path(cache):
    """Windows C++ model loader cannot read this workspace's Unicode absolute path.

    Use an ASCII relative path against the explicit worker cwd, without moving any
    files or changing the user's workspace. Outside caches must already be ASCII.
    """
    cache = cache.resolve()
    path = str(cache.relative_to(ROOT)) if ROOT in cache.parents else str(cache)
    if os.name == 'nt' and not path.isascii():
        raise ValueError('Paddle on Windows requires an ASCII cache path relative to project root')
    return path


def paddle_worker(crop, dest):
    """Separate process: fail closed on native crashes/hangs; preserve raw geometry."""
    from importlib.metadata import version
    from paddleocr import TableRecognitionPipelineV2
    started = time.monotonic()
    pipeline = TableRecognitionPipelineV2(**PP_OPTIONS)
    initialized = time.monotonic()
    pipeline.export_paddlex_config_to_yaml(str(dest / 'pipeline-config.yaml'))
    # Decode through Python to avoid the same Windows Unicode issue in OpenCV.
    import numpy as np
    from PIL import Image
    with Image.open(crop) as image:
        bgr = np.asarray(image.convert('RGB'))[:, :, ::-1].copy()
    results = list(pipeline.predict(bgr, use_table_orientation_classify=False))
    if len(results) != 1:
        raise ValueError('Expected one cropped image result')
    raw = results[0].json
    if isinstance(raw, str):
        raw = json.loads(raw)
    write_json(dest / 'paddle-raw.json', raw)
    text = extract_paddle_html(raw)
    result = {'status': 'completed', 'finish_reason': 'stop', 'content': text,
              'model': 'PP-TableMagic', 'response_format': 'html', 'usage': None,
              'total_seconds': round(time.monotonic() - started, 4),
              'initialization_seconds': round(initialized - started, 4),
              'inference_seconds': round(time.monotonic() - initialized, 4),
              'versions': {p: version(p) for p in ('paddlepaddle', 'paddleocr', 'paddlex', 'numpy')},
              'options': PP_OPTIONS, 'table_orientation_classify': False,
              'raw_result_sha256': sha(dest / 'paddle-raw.json')}
    write_json(dest / 'worker-result.json', result)


class PaddleClient:
    def __init__(self, python, cache):
        self.python, self.cache = python.resolve(), cache.resolve()
        if not self.python.is_file():
            raise ValueError('Isolated Paddle Python not installed')
        self.metadata = {'model': 'PP-TableMagic', 'options': PP_OPTIONS, 'device': 'cpu',
                         'deadline_seconds': 600, 'process_per_crop': True, 'retries': 0}

    async def __call__(self, crop, dest, checkpoint):
        env = dict(os.environ, PYTHONUTF8='1', PADDLE_PDX_CACHE_HOME=paddle_cache_path(self.cache),
                   HF_HOME=str(self.cache / 'huggingface'), MODELSCOPE_CACHE=str(self.cache / 'modelscope'),
                   PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True')
        def invoke():
            start = time.monotonic()
            with (dest / 'worker.log').open('w', encoding='utf-8') as log:
                try:
                    proc = subprocess.run([str(self.python), str(Path(__file__).resolve()),
                        '--paddle-worker', '--crop', str(crop), '--worker-output', str(dest)],
                        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)
                except subprocess.TimeoutExpired:
                    return {'status': 'request_failed', 'error_type': 'PaddleDeadlineExceeded',
                            'content': '', 'total_seconds': round(time.monotonic() - start, 4)}
            result_path = dest / 'worker-result.json'
            if proc.returncode != 0 or not result_path.exists():
                return {'status': 'request_failed', 'error_type': 'PaddleWorkerFailed',
                        'exit_code': proc.returncode, 'content': '',
                        'total_seconds': round(time.monotonic() - start, 4)}
            result = read_json(result_path)
            result['process_total_seconds'] = round(time.monotonic() - start, 4)
            return result
        return await asyncio.to_thread(invoke)


def child(root, relative):
    path = (root / relative).resolve()
    if root not in path.parents:
        raise ValueError('Input path escape')
    return path


async def run_arm(prepared, output, arm, client, max_calls=3):
    if arm not in ('qwen_native', 'pp_tablemagic') or type(max_calls) is not int or not 0 <= max_calls <= 3:
        raise ValueError('Unknown arm or invalid call budget (0..3)')
    prepared, output = prepared.resolve(), output.resolve()
    manifest = read_json(prepared / 'manifest.json')
    protected = [prepared, Path(manifest['source']).resolve(), Path(manifest['images']).resolve()]
    if output.exists() or any(output == p or p in output.parents or output in p.parents for p in protected):
        raise ValueError('Use a fresh output directory outside inputs')
    items = manifest['results']
    if not 1 <= len(items) <= 3 or len({i['id'] for i in items}) != len(items) or len({i['page'] for i in items}) != len(items):
        raise ValueError('Expected 1..3 unique table cases')
    for item in items:
        case = item['id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', case):
            raise ValueError('Invalid case id')
        if sha(child(prepared, item['crop'])) != item['crop_sha256'] or sha(child(prepared, case + '/baseline.html')) != item['baseline_sha256']:
            raise ValueError('Crop or baseline hash mismatch')
    output.mkdir(parents=True)
    report = {'schema_version': '1.0', 'experiment': 'omnidocbench-table-specialist-v7',
              'arm': arm, 'response_format': 'html', 'gold_access': False, 'production_applied': False,
              'manifest_sha256': sha(prepared / 'manifest.json'), 'max_calls': max_calls,
              'calls_attempted': 0, 'sdk_retries': 0, 'settings': getattr(client, 'metadata', {}), 'results': []}
    stopped = False
    for item in items:
        record = {'id': item['id'], 'page': item['page'], 'arm': arm,
                  'crop_sha256': item['crop_sha256'], 'status': 'skipped_budget'}
        report['results'].append(record)
        if stopped:
            record['status'] = 'skipped_arm_unavailable'
        if stopped or report['calls_attempted'] >= max_calls:
            write_json(output / 'summary.json', report); continue
        crop = child(prepared, item['crop'])
        if sha(crop) != item['crop_sha256']:
            raise ValueError('Crop changed after preflight')
        dest = output / item['id']; dest.mkdir()
        record['status'] = 'attempted_no_response_yet'; report['calls_attempted'] += 1
        write_json(output / 'summary.json', report)
        print(f'{arm}: {item["page"]}, attempt {report["calls_attempted"]}/{max_calls}', flush=True)
        try:
            response = await client(crop, dest, lambda progress: write_json(dest / 'progress.json', progress))
        except Exception as exc:
            response = {'status': 'request_failed', 'content': '', 'error_type': type(exc).__name__}
        write_json(dest / 'response.json', response)
        record.update({k: v for k, v in response.items() if k != 'content'})
        record['latency_seconds'] = response.get('total_seconds')
        if response.get('status') == 'request_failed':
            record['status'] = 'request_failed_baseline_retained'
            stopped = response.get('http_status') in (401, 403, 404) or response.get('error_type') == 'PaddleWorkerFailed'
        else:
            try:
                if response.get('status') != 'completed' or response.get('finish_reason') != 'stop':
                    raise ValueError('Incomplete or truncated response')
                structure, rendered = parse_html_table(response.get('content'))
            except ValueError as exc:
                record.update(status='invalid_candidate_baseline_retained', validation_error=str(exc))
            else:
                write_json(dest / 'candidate-structure.json', structure)
                (dest / 'candidate.html').write_text(rendered, encoding='utf-8')
                record.update(status='valid_candidate_review_required', rows=structure['num_rows'],
                              cols=structure['num_cols'], cells=len(structure['table_cells']))
        write_json(output / 'summary.json', report)
        print(f'{arm}: {record["status"]} ({record["latency_seconds"]}s)', flush=True)
    return report


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=['pp_tablemagic', 'qwen_native'])
    parser.add_argument('--prepared-dir', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--paddle-python', type=Path, default=ROOT / 'backend/data/benchmarks/tablemagic/.venv/Scripts/python.exe')
    parser.add_argument('--cache', type=Path, default=ROOT / 'backend/data/benchmarks/model_cache/tablemagic')
    parser.add_argument('--max-calls', type=int, default=3)
    parser.add_argument('--paddle-worker', action='store_true')
    parser.add_argument('--crop', type=Path)
    parser.add_argument('--worker-output', type=Path)
    args = parser.parse_args()
    if args.paddle_worker:
        paddle_worker(args.crop, args.worker_output)
        return 0
    if not args.arm or not args.prepared_dir or not args.output_dir:
        parser.error('--arm, --prepared-dir and --output-dir are required')
    client = NativeClient(args.env_file) if args.arm == 'qwen_native' else PaddleClient(args.paddle_python, args.cache)
    try:
        report = await run_arm(args.prepared_dir, args.output_dir, args.arm, client, args.max_calls)
    finally:
        if isinstance(client, NativeClient):
            await client.close()
    return 0 if all(r['status'] == 'valid_candidate_review_required' for r in report['results']) else 2


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
