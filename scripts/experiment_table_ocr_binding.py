"""Bounded local v9 experiment: extended structure + cached OCR + fresh cell splits.

All Paddle instrumentation is scoped to a child process; no package/model edits.
No gold access and no remote clients. Original invalid v8 case stays in denominator.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from audit_table_decoder import ROOT, CACHE, MODELS, FILES, read, write, sha, preflight, local_path
from table_ocr_binding import audit_binding, parse_html_table, binding_gate

CLONE_SHA = 'f1ec593a33056ac052a50c6740ec07a55e55327eff1657b397e2317d9f043882'
DEPENDENCIES = {
    'table_classification': 'PP-LCNet_x1_0_table_cls',
    'wired_table_cells_detection': 'RT-DETR-L_wired_table_cell_det',
    'wireless_table_cells_detection': 'RT-DETR-L_wireless_table_cell_det',
    'text_detection': 'PP-OCRv5_server_det', 'text_recognition': 'PP-OCRv5_server_rec'}


def plain(obj):
    if isinstance(obj, dict): return {str(k): plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [plain(v) for v in obj]
    if hasattr(obj, 'tolist'): return obj.tolist()
    return obj


def candidate_status(response):
    if not response.get('candidate_valid'):
        return 'invalid_candidate_baseline_retained'
    if not response.get('binding_integrity', {}).get('passed'):
        return 'binding_rejected_baseline_retained'
    return 'valid_candidate_review_required'


def check_inputs(prepared, v7, v8, output):
    manifest = preflight(prepared, output)
    for root in (v7, v8):
        if output == root or root in output.parents or output in root.parents:
            raise ValueError('Output overlaps previous evidence')
    old, decoder = read(v7 / 'summary.json'), read(v8 / 'summary.json')
    digest = sha(prepared / 'manifest.json')
    if old['manifest_sha256'] != digest or decoder['manifest_sha256'] != digest or not decoder.get('original_models_unchanged'):
        raise ValueError('Experiment provenance mismatch')
    files = [prepared / 'manifest.json', v7 / 'summary.json', v8 / 'summary.json']
    eligible = []
    for item in manifest['results']:
        case = item['id']; raw = v7 / case / 'paddle-raw.json'
        if sha(raw) != read(v7 / case / 'worker-result.json')['raw_result_sha256']:
            raise ValueError('Cached OCR artifact changed')
        files += [raw, v7 / case / 'worker-result.json', v8 / 'extended' / case / 'result.json',
                  v8 / 'extended' / case / 'structure.html']
        result = read(v8 / 'extended' / case / 'result.json')
        if result['crop_sha256'] != item['crop_sha256']:
            raise ValueError('Decoder crop mismatch')
        if result['validation']['valid'] and result['termination'] == 'eos':
            parse_html_table((v8 / 'extended' / case / 'structure.html').read_text(encoding='utf-8'))
            eligible.append(case)
    if len(eligible) > 2:
        raise ValueError('At most two v8-approved cases may run')
    for name in MODELS:
        clone = v8 / 'experimental-models' / name
        audit = read(clone / 'clone-audit.json')
        if sha(clone / 'inference.json') != CLONE_SHA:
            raise ValueError('Unrecognized experimental graph')
        for filename in FILES:
            path = clone / filename
            if sha(path) != audit['clone_sha256'][filename]:
                raise ValueError('Experimental model hash mismatch')
            files.append(path)
    for name in DEPENDENCIES.values():
        for filename in ('inference.json', 'inference.pdiparams', 'inference.yml'):
            path = CACHE / name / filename
            if not path.is_file(): raise ValueError('Model not cached; downloads prohibited')
            files.append(path)
    return manifest, eligible, {str(p): sha(p) for p in files}


def worker(crop, cached_raw, v8_case, model_root, dest):
    import numpy as np
    from PIL import Image
    from importlib.metadata import version
    from paddleocr import TableRecognitionPipelineV2
    from paddlex.inference.pipelines.ocr.result import OCRResult
    from paddlex.inference.pipelines.table_recognition import table_recognition_post_processing_v2 as post
    from paddlex.inference.pipelines.table_recognition.pipeline_v2 import _TableRecognitionPipelineV2 as Core

    start = time.monotonic()
    expected_structure = (v8_case / 'structure.html').read_text(encoding='utf-8')
    with Image.open(crop) as image:
        bgr = np.asarray(image.convert('RGB'))[:, :, ::-1].copy()
    cached = read(cached_raw)['res']['overall_ocr_res']
    for field in ('rec_boxes', 'rec_polys', 'dt_polys'):
        cached[field] = np.asarray(cached[field])
    cached['doc_preprocessor_res'] = {'output_img': bgr}
    ocr = OCRResult(cached)
    options = dict(device='cpu', cpu_threads=4, enable_mkldnn=False,
                   use_doc_orientation_classify=False, use_doc_unwarping=False,
                   use_layout_detection=False, use_ocr_model=True)
    for prefix, name in DEPENDENCIES.items():
        options[prefix + '_model_name'] = name
        options[prefix + '_model_dir'] = local_path(CACHE / name)
    for prefix, name in zip(('wired', 'wireless'), MODELS):
        options[prefix + '_table_structure_recognition_model_name'] = name
        options[prefix + '_table_structure_recognition_model_dir'] = local_path(model_root / name)
    pipeline = TableRecognitionPipelineV2(**options)
    pipeline.export_paddlex_config_to_yaml(str(dest / 'pipeline-config.yaml'))
    captured = {}
    old_match, old_render, old_reprocess = post.match_table_and_ocr, post.get_html_result, Core.cells_det_results_reprocessing

    def match(boxes, ocr_boxes, flags, rows):
        result = old_match(boxes, ocr_boxes, flags, rows)
        captured['match'] = plain({'cell_boxes': boxes, 'ocr_boxes': ocr_boxes, 'group_starts': flags,
                                   'row_starts_argument': rows, 'groups': result})
        write(dest / 'binding-capture.json', captured)
        return result

    def render(groups, texts, structures, breaks):
        raw_structure = ''.join(structures)
        if raw_structure != expected_structure:
            raise ValueError('Structure differs from frozen v8 result')
        captured['render'] = plain({'groups': groups, 'texts': texts, 'structure_tokens': structures, 'breaks': breaks})
        write(dest / 'binding-capture.json', captured)
        return old_render(groups, texts, structures, breaks)

    def reprocess(self, boxes, scores, ocr_boxes, desired):
        result = old_reprocess(self, boxes, scores, ocr_boxes, desired)
        captured['geometry_reprocessing'] = plain({'detected_boxes': boxes, 'scores': scores,
            'ocr_boxes': ocr_boxes, 'desired_cells': desired, 'processed_boxes': result})
        write(dest / 'binding-capture.json', captured)
        return result

    post.match_table_and_ocr, post.get_html_result, Core.cells_det_results_reprocessing = match, render, reprocess
    initialized = time.monotonic()
    try:
        results = list(pipeline.predict(bgr, use_ocr_model=False, overall_ocr_res=ocr,
                                       use_ocr_results_with_table_cells=True, use_table_orientation_classify=False))
    finally:
        post.match_table_and_ocr, post.get_html_result, Core.cells_det_results_reprocessing = old_match, old_render, old_reprocess
    if len(results) != 1:
        raise ValueError('Expected one cropped table')
    raw = results[0].json
    if isinstance(raw, str): raw = json.loads(raw)
    write(dest / 'paddle-raw.json', raw)
    tables = raw['res']['table_res_list']
    if len(tables) != 1: raise ValueError('Expected exactly one table result')
    text = tables[0]['pred_html']
    (dest / 'raw.html').write_text(text, encoding='utf-8')
    response = {'status': 'completed', 'finish_reason': 'eos_verified_v8_identical_structure', 'content': text,
                'inference_seconds': round(time.monotonic() - initialized, 4),
                'initialization_seconds': round(initialized - start, 4), 'total_seconds': round(time.monotonic() - start, 4),
                'cached_ocr_sha256': sha(cached_raw), 'structure_sha256': sha(v8_case / 'structure.html'),
                'crop_sha256': sha(crop), 'structure_identical_to_v8': 'render' in captured,
                'versions': {p: version(p) for p in ('paddleocr', 'paddlex', 'paddlepaddle', 'numpy')},
                'options': options, 'paid_api_calls': 0, 'gold_access': False}
    try:
        structure, canonical = parse_html_table(text)
        trace = audit_binding(expected_structure, text, captured)
    except (ValueError, KeyError) as exc:
        response.update(candidate_valid=False, validation_error=str(exc))
    else:
        write(dest / 'binding-trace.json', trace)
        gate = binding_gate(trace)
        (dest / 'raw-candidate.html').write_text(canonical, encoding='utf-8')
        if gate['passed']:
            write(dest / 'candidate-structure.json', structure)
            (dest / 'candidate.html').write_text(canonical, encoding='utf-8')
        response.update(candidate_valid=True, binding_integrity=gate,
                        binding_summary={k: v for k, v in trace.items() if k != 'cells'})
    write(dest / 'response.json', response)


def run(prepared, v7, v8, output, python):
    manifest, eligible, protected = check_inputs(prepared, v7, v8, output)
    if not python.is_file(): raise ValueError('Isolated Paddle Python missing')
    output.mkdir(parents=True)
    report = {'schema_version': '1.0', 'experiment': 'omnidocbench-table-ocr-binding-v9', 'arm': 'pp_binding_v9',
              'manifest_sha256': sha(prepared / 'manifest.json'), 'response_format': 'html',
              'paid_api_calls': 0, 'gold_access': False, 'production_applied': False,
              'max_calls': 2, 'calls_attempted': 0, 'deadline_seconds': 600, 'retries': 0,
              'protected_hashes': protected, 'results': []}
    env = dict(os.environ, PYTHONUTF8='1', PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',
               PADDLE_PDX_CACHE_HOME='backend/data/benchmarks/model_cache/tablemagic', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    stopped = False
    for item in manifest['results']:
        case = item['id']; row = dict(id=case, page=item['page'], crop_sha256=item['crop_sha256'])
        report['results'].append(row)
        if case not in eligible or stopped:
            row['status'] = 'skipped_prior_invalid_baseline_retained' if case not in eligible else 'skipped_worker_failure'
            write(output / 'summary.json', report); continue
        crop = (prepared / item['crop']).resolve()
        if sha(crop) != item['crop_sha256']: raise ValueError('Crop changed')
        dest = output / case; dest.mkdir()
        row['status'] = 'attempted'; report['calls_attempted'] += 1
        write(output / 'summary.json', report)
        print('binding:', case, flush=True)
        with (dest / 'worker.log').open('w', encoding='utf-8') as log:
            try:
                proc = subprocess.run([str(python), str(Path(__file__).resolve()), '--worker', '--crop', str(crop),
                    '--cached-raw', str(v7 / case / 'paddle-raw.json'), '--v8-case', str(v8 / 'extended' / case),
                    '--model-root', str(v8 / 'experimental-models'), '--output', str(dest)], cwd=ROOT, env=env,
                    stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)
                row['exit_code'] = proc.returncode
                response = read(dest / 'response.json') if proc.returncode == 0 and (dest / 'response.json').is_file() else None
            except subprocess.TimeoutExpired:
                response = None; row['error'] = 'worker_deadline'
        if response is None:
            row['status'] = 'request_failed_baseline_retained'; stopped = True
        else:
            row.update({k: v for k, v in response.items() if k not in ('content', 'status')})
            row['status'] = candidate_status(response)
        write(output / 'summary.json', report)
    report['protected_inputs_unchanged'] = all(sha(Path(path)) == digest for path, digest in protected.items())
    preflight(prepared, output.parent / (output.name + '-integrity-only'))
    report['frozen_15_files_unchanged'] = True
    write(output / 'summary.json', report)
    if stopped or not report['protected_inputs_unchanged']: raise RuntimeError('Experiment incomplete or integrity failed')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker', action='store_true')
    for key in ('crop', 'cached-raw', 'v8-case', 'model-root'): p.add_argument('--' + key, type=Path)
    p.add_argument('--prepared', type=Path, default=ROOT / 'output/benchmarks/omnidocbench-table-vlm-v5/prepared')
    p.add_argument('--v7', type=Path, default=ROOT / 'output/benchmarks/omnidocbench-table-specialist-v7/live/pp_tablemagic-v2')
    p.add_argument('--v8', type=Path, default=ROOT / 'output/benchmarks/omnidocbench-table-decoder-v8-run3')
    p.add_argument('--python', type=Path, default=ROOT / 'backend/data/benchmarks/tablemagic/.venv/Scripts/python.exe')
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if a.worker:
        worker(a.crop.resolve(), a.cached_raw.resolve(), a.v8_case.resolve(), a.model_root.resolve(), a.output.resolve())
    else:
        run(a.prepared.resolve(), a.v7.resolve(), a.v8.resolve(), a.output.resolve(), a.python.resolve())


if __name__ == '__main__': main()
