"""Frozen v12 oracle-crop evaluation. Gold is used only in prepare/score stages."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from audit_table_decoder import ROOT, CACHE, MODELS, FILES, read, write, sha, local_path, parse_html_table
from experiment_table_ocr_binding import DEPENDENCIES, CLONE_SHA, plain

DATA = ROOT / 'backend/data/benchmarks/omnidocbench'
MODEL_ROOT = ROOT / 'output/benchmarks/omnidocbench-table-decoder-v8-run3/experimental-models'
MAIN_PYTHON = Path(sys.executable)
PADDLE_PYTHON = ROOT / 'backend/data/benchmarks/tablemagic/.venv/Scripts/python.exe'
SEED = 'scholarlens-unseen-pages-v12-20260925'


def rank(value):
    return hashlib.sha256((SEED + value).encode()).hexdigest()


def select_cases(pages, excluded, count=20):
    if not 1 <= count <= 30: raise ValueError('Count must be 1..30')
    groups = defaultdict(list)
    for p in pages:
        info = p['page_info']; name = info['image_path']
        if name in excluded: continue
        if Path(name).name != name: raise ValueError('Image name is not a basename')
        candidates = []
        for d in p['layout_dets']:
            if d['category_type'] != 'table' or d.get('ignore'): continue
            poly = d['poly']
            if len(poly) != 8 or not all(math.isfinite(v) for v in poly): raise ValueError('Invalid polygon')
            box = [min(poly[::2]), min(poly[1::2]), max(poly[::2]), max(poly[1::2])]
            area = (box[2] - box[0]) * (box[3] - box[1])
            if area <= 0: raise ValueError('Empty bbox')
            candidates.append((area, str(d['anno_id']), box))
        if not candidates: continue
        _, anno, bbox = sorted(candidates, key=lambda x: (-x[0], x[1]))[0]
        attr = info.get('page_attribute', {})
        subset = attr.get('subset', 'unknown')
        groups[subset].append({'page': name, 'anno_id': anno, 'bbox': bbox, 'subset': subset,
                               'layout': attr.get('layout'), 'special_issue': attr.get('special_issue', [])})
    for values in groups.values(): values.sort(key=lambda x: rank(x['page']))
    if sum(map(len, groups.values())) < count: raise ValueError('Insufficient unseen pages')
    selected = []
    while len(selected) < count:
        for key in sorted(groups):
            if groups[key] and len(selected) < count: selected.append(groups[key].pop(0))
    for i, case in enumerate(selected, 1): case['id'] = f'case-{i:02d}'
    return selected


def choose_baseline_table(tables):
    def area(t):
        boxes = [p['bbox'] for p in t.get('prov', []) if p.get('bbox')]
        return max((abs((b['r'] - b['l']) * (b['t'] - b['b'])) for b in boxes), default=0)
    return max(range(len(tables)), key=lambda i: (area(tables[i]), -i)) if tables else None


def choose_effective(baseline, candidate, gate):
    if gate['passed']:
        if not candidate: raise ValueError('Passing gate without candidate')
        return candidate
    return baseline


def aggregate_scores(rows):
    n = len(rows)
    if not n: raise ValueError('Empty scoring cohort')
    result = {'cases': n, 'accepted': sum(r['gate_passed'] for r in rows)}
    for arm in ('baseline', 'effective'):
        for metric in ('teds', 'structure_teds'):
            result[arm + '_' + metric] = sum(r[arm][metric] for r in rows) / n
    delta = [r['effective']['teds'] - r['baseline']['teds'] for r in rows]
    result.update(improved=sum(d > 1e-9 for d in delta), regressed=sum(d < -1e-9 for d in delta),
                  unchanged=sum(abs(d) <= 1e-9 for d in delta))
    return result


def verify(hashes):
    for path, digest in hashes.items():
        if sha(Path(path)) != digest: raise ValueError('Frozen input changed: ' + path)


def freeze_inputs():
    paths = [Path(__file__).resolve()]
    paths += [ROOT / 'scripts' / n for n in ('table_grid_binding.py', 'table_header_reconstruction.py',
              'table_ocr_binding.py', 'audit_table_decoder.py', 'experiment_table_ocr_binding.py',
              'score_table_header_reconstruction.py', 'score_vlm_table_experiment.py')]
    paths += [ROOT / 'backend/Information-Extraction/unified/parsers' / n
              for n in ('table_structure.py', 'html_table_candidate.py', 'docling_parser.py')]
    for name in MODELS:
        folder = MODEL_ROOT / name; audit = read(folder / 'clone-audit.json')
        if sha(folder / 'inference.json') != CLONE_SHA: raise ValueError('Unknown extended graph')
        for filename in FILES:
            if sha(folder / filename) != audit['clone_sha256'][filename]: raise ValueError('Clone drift')
            paths.append(folder / filename)
    for name in DEPENDENCIES.values():
        paths += [CACHE / name / n for n in ('inference.json', 'inference.pdiparams', 'inference.yml')]
    cache = ROOT / 'backend/data/benchmarks/model_cache'
    for folder in (cache / 'easyocr/model', cache / 'huggingface/hub'):
        paths += [p for p in folder.rglob('*') if p.is_file() and '.locks' not in p.parts]
    evaluator = DATA / 'evaluator'
    paths += [evaluator / n for n in ('src/core/preprocess/data_preprocess.py', 'src/metrics/table_metric.py')]
    return {str(p): sha(p) for p in sorted(set(paths))}


def prepare(root, count):
    from PIL import Image
    if root.exists(): raise ValueError('Fresh output required')
    source = DATA / 'OmniDocBench_academic_en_100.json'
    annotations = read(source); excluded = set(); exclusion_files = []
    for p in sorted((ROOT / 'output/benchmarks').glob('*/selected_annotations.json')):
        excluded.update(x['page_info']['image_path'] for x in read(p))
        exclusion_files.append(p)
    cases = select_cases(annotations, excluded, count)
    protected = freeze_inputs()
    protected.update({str(p): sha(p) for p in [source] + exclusion_files})
    root.mkdir(parents=True); (root / 'prepared').mkdir(); gold = {}
    page_map = {p['page_info']['image_path']: p for p in annotations}
    for case in cases:
        src = DATA / 'images_academic_en_100' / case['page']
        protected[str(src)] = sha(src)
        with Image.open(src) as img:
            l, t, r, b = case['bbox']
            box = (max(0, math.floor(l) - 12), max(0, math.floor(t) - 12),
                   min(img.width, math.ceil(r) + 12), min(img.height, math.ceil(b) + 12))
            if (box[2]-box[0])*(box[3]-box[1]) > 40_000_000: raise ValueError('Crop exceeds budget')
            path = root / 'prepared' / (case['id'] + '.png')
            img.convert('RGB').crop(box).save(path)
        case.update(crop=path.name, crop_sha256=sha(path), crop_bbox=list(box))
        protected[str(path)] = sha(path)
        table = next(d for d in page_map[case['page']]['layout_dets'] if str(d['anno_id']) == case['anno_id'])
        gold[case['id']] = {'page': case['page'], 'anno_id': case['anno_id'], 'html': table['html']}
    write(root / 'prepared/manifest.json', {'seed': SEED, 'crop_padding_px': 12, 'cases': cases,
          'excluded_pages': sorted(excluded), 'gold_access_in_inference': False, 'oracle_bbox': True})
    write(root / 'scoring-only-gold.json', gold)
    for name in ('prepared/manifest.json', 'scoring-only-gold.json'):
        p = root / name; protected[str(p)] = sha(p)
    write(root / 'frozen-inputs.json', protected)
    print('Prepared', len(cases), 'unique unseen pages; protected files', len(protected), flush=True)


def docling_worker(crop, dest):
    from importlib.metadata import version
    from generate_omnidocbench_predictions import image_to_pdf
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions, TableFormerMode
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
    from table_structure import extract_table_structure, render_table_html
    pdf = dest / 'crop.pdf'; image_to_pdf(crop, pdf)
    options = PdfPipelineOptions()
    options.do_ocr = True; options.do_formula_enrichment = False; options.do_table_structure = True
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    options.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
    options.ocr_options = EasyOcrOptions(download_enabled=False, use_gpu=False,
        model_storage_directory=str(ROOT / 'backend/data/benchmarks/model_cache/easyocr/model'))
    write(dest / 'pipeline-config.json', options.model_dump(mode='json'))
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    converted = converter.convert(str(pdf)); raw = converted.document.export_to_dict()
    write(dest / 'docling-document.json', raw)
    tables = raw.get('tables', []); selected = choose_baseline_table(tables)
    result = {'status': 'no_table', 'table_count': len(tables), 'selected_table': selected,
              'conversion_status': str(converted.status), 'versions': {p: version(p) for p in ('docling', 'easyocr', 'torch')}}
    if selected is not None:
        structure = extract_table_structure(tables[selected]); text = render_table_html(structure)
        if text is None: raise ValueError('Invalid Docling table topology')
        _, canonical = parse_html_table(text)
        write(dest / 'table-structure.json', structure)
        (dest / 'raw.html').write_text(text, encoding='utf-8')
        (dest / 'candidate.html').write_text(canonical, encoding='utf-8')
        result['status'] = 'completed'
    return result


def paddle_worker(crop, dest):
    import numpy as np
    from PIL import Image
    from importlib.metadata import version
    from paddleocr import TableRecognitionPipelineV2
    from paddlex.inference.pipelines.table_recognition import table_recognition_post_processing_v2 as post
    from paddlex.inference.pipelines.table_recognition.pipeline_v2 import _TableRecognitionPipelineV2 as Core
    with Image.open(crop) as img: bgr = np.asarray(img.convert('RGB'))[:, :, ::-1].copy()
    options = dict(device='cpu', cpu_threads=4, enable_mkldnn=False,
                   use_doc_orientation_classify=False, use_doc_unwarping=False,
                   use_layout_detection=False, use_ocr_model=True)
    for prefix, name in DEPENDENCIES.items():
        options[prefix + '_model_name'] = name
        options[prefix + '_model_dir'] = local_path(CACHE / name)
    for prefix, name in zip(('wired', 'wireless'), MODELS):
        options[prefix + '_table_structure_recognition_model_name'] = name
        options[prefix + '_table_structure_recognition_model_dir'] = local_path(MODEL_ROOT / name)
    pipeline = TableRecognitionPipelineV2(**options)
    pipeline.export_paddlex_config_to_yaml(str(dest / 'pipeline-config.yaml'))
    capture = {}; counts = defaultdict(int)
    old_match, old_render, old_reprocess = post.match_table_and_ocr, post.get_html_result, Core.cells_det_results_reprocessing
    def match(boxes, ocr_boxes, flags, rows):
        result = old_match(boxes, ocr_boxes, flags, rows)
        counts['match'] += 1
        capture['match'] = plain(dict(cell_boxes=boxes, ocr_boxes=ocr_boxes, group_starts=flags,
                                      row_starts_argument=rows, groups=result))
        write(dest / 'binding-capture.json', capture)
        return result
    def render(groups, texts, structures, breaks):
        counts['render'] += 1
        capture['render'] = plain(dict(groups=groups, texts=texts, structure_tokens=structures, breaks=breaks))
        write(dest / 'binding-capture.json', capture)
        (dest / 'structure.html').write_text(''.join(structures), encoding='utf-8')
        return old_render(groups, texts, structures, breaks)
    def reprocess(self, boxes, scores, ocr_boxes, desired):
        result = old_reprocess(self, boxes, scores, ocr_boxes, desired)
        counts['geometry_reprocessing'] += 1
        capture['geometry_reprocessing'] = plain(dict(detected_boxes=boxes, scores=scores,
              ocr_boxes=ocr_boxes, desired_cells=desired, processed_boxes=result))
        write(dest / 'binding-capture.json', capture)
        return result
    post.match_table_and_ocr, post.get_html_result, Core.cells_det_results_reprocessing = match, render, reprocess
    try:
        results = list(pipeline.predict(bgr, use_ocr_model=True, use_ocr_results_with_table_cells=True,
                                        use_table_orientation_classify=False))
    finally:
        post.match_table_and_ocr, post.get_html_result, Core.cells_det_results_reprocessing = old_match, old_render, old_reprocess
        write(dest / 'capture-counts.json', dict(counts))
    if len(results) != 1: raise ValueError('Expected one result')
    raw = results[0].json
    if isinstance(raw, str): raw = json.loads(raw)
    write(dest / 'paddle-raw.json', raw)
    tables = raw['res']['table_res_list']
    if len(tables) != 1: raise ValueError('Expected exactly one table')
    (dest / 'raw.html').write_text(tables[0]['pred_html'], encoding='utf-8')
    return {'status': 'completed', 'table_count': 1, 'capture_counts': dict(counts),
            'versions': {p: version(p) for p in ('paddleocr', 'paddlex', 'paddlepaddle', 'numpy')}}


def worker(arm, crop, dest):
    started = time.monotonic()
    try:
        result = (docling_worker if arm == 'baseline' else paddle_worker)(crop, dest)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = {'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)}
    result.update(seconds=time.monotonic()-started, crop_sha256=sha(crop), paid_api_calls=0, gold_access=False)
    write(dest / 'result.json', result)


def run_arm(root, arm):
    manifest = read(root / 'prepared/manifest.json'); protected = read(root / 'frozen-inputs.json'); verify(protected)
    output = root / arm
    output.mkdir()  # Never reuse or overwrite another run.
    python = MAIN_PYTHON if arm == 'baseline' else PADDLE_PYTHON
    env = dict(os.environ, PYTHONUTF8='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        HF_HOME=str(ROOT / 'backend/data/benchmarks/model_cache/huggingface'),
        EASYOCR_MODULE_PATH=str(ROOT / 'backend/data/benchmarks/model_cache/easyocr'),
        MPLCONFIGDIR=str(ROOT / 'backend/data/benchmarks/model_cache/matplotlib'),
        PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True', PADDLE_PDX_CACHE_HOME='backend/data/benchmarks/model_cache/tablemagic',
        OMP_NUM_THREADS='4', MKL_NUM_THREADS='4')
    rows = []
    for item in manifest['cases']:
        dest = output / item['id']; dest.mkdir(); crop = root / 'prepared' / item['crop']
        if sha(crop) != item['crop_sha256']: raise ValueError('Crop drift')
        started = time.monotonic()
        with (dest / 'worker.log').open('w', encoding='utf-8') as log:
            try:
                proc = subprocess.run([str(python), str(Path(__file__).resolve()), 'worker', '--arm', arm,
                    '--crop', str(crop), '--root', str(dest)], cwd=ROOT, env=env,
                    stdout=log, stderr=subprocess.STDOUT, timeout=240, check=False)
                result = read(dest / 'result.json') if proc.returncode == 0 and (dest / 'result.json').is_file() else {
                    'status': 'process_failed', 'exit_code': proc.returncode}
            except subprocess.TimeoutExpired:
                result = {'status': 'timeout', 'timeout_seconds': 240}
        result.update(id=item['id'], wall_seconds=time.monotonic()-started, crop_sha256=item['crop_sha256'])
        write(dest / 'result.json', result); rows.append(result)
        write(output / 'summary.json', {'arm': arm, 'results': rows, 'complete': False})
        print(arm, item['id'], result['status'], round(result['wall_seconds'], 1), flush=True)
    verify(protected)
    artifacts = {p.relative_to(output).as_posix(): sha(p) for p in output.rglob('*') if p.is_file() and p.name != 'summary.json'}
    write(output / 'summary.json', {'arm': arm, 'results': rows, 'complete': True, 'protected_inputs_unchanged': True,
                                   'artifact_sha256': artifacts})


def finalize(root):
    import cv2
    import numpy as np
    from table_header_reconstruction import repair_header
    protected = read(root / 'frozen-inputs.json'); verify(protected)
    manifest = read(root / 'prepared/manifest.json'); rows = []
    for arm in ('baseline', 'paddle'):
        summary = read(root / arm / 'summary.json')
        if not summary['complete'] or len(summary['results']) != len(manifest['cases']): raise ValueError('Incomplete inference')
        verify({str(root / arm / p): digest for p, digest in summary['artifact_sha256'].items()})
    out = root / 'final'; out.mkdir()
    for item in manifest['cases']:
        case = item['id']; dest = out / case; dest.mkdir(); src = root / 'paddle' / case
        basepath = root / 'baseline' / case / 'candidate.html'
        base_result = read(root / 'baseline' / case / 'result.json')
        baseline = basepath.read_text(encoding='utf-8') if base_result['status'] == 'completed' and basepath.is_file() else None
        gate = {'passed': False, 'reasons': []}; candidate = None; status = 'rejected'
        try:
            result = read(src / 'result.json')
            if result['status'] != 'completed': raise ValueError('Paddle worker failed: ' + result['status'])
            if any(result['capture_counts'].get(k) != 1 for k in ('match', 'render', 'geometry_reprocessing')):
                raise ValueError('Missing or ambiguous instrumented table')
            raw = (src / 'structure.html').read_text(encoding='utf-8'); parse_html_table(raw)
            gray = cv2.imdecode(np.frombuffer((root / 'prepared' / item['crop']).read_bytes(), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            trace = repair_header(raw, read(src / 'binding-capture.json'), gray)
            write(dest / 'grid-trace.json', trace)
            candidate, gate, status = trace['html'], trace['gate'], trace['status']
        except (ValueError, KeyError, FileNotFoundError, IndexError) as exc:
            gate = {'passed': False, 'reasons': [str(exc)]}
        if candidate: (dest / 'candidate.html').write_text(candidate, encoding='utf-8')
        effective = choose_effective(baseline, candidate, gate)
        if effective: (dest / 'effective.html').write_text(effective, encoding='utf-8')
        row = {'id': case, 'page': item['page'], 'status': status, 'gate': gate,
               'baseline_available': baseline is not None, 'effective_available': effective is not None,
               'effective_source': 'v11' if gate['passed'] else 'baseline'}
        rows.append(row); write(dest / 'result.json', row)
        print(case, status, gate, flush=True)
    verify(protected)
    artifacts = {p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()}
    write(out / 'summary.json', {'results': rows, 'artifact_sha256': artifacts, 'inputs_unchanged': True,
          'gold_access_in_inference': False, 'production_applied': False, 'paid_api_calls': 0,
          'manifest_sha256': sha(root / 'prepared/manifest.json')})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run', 'worker', 'finalize'])
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--arm', choices=['baseline', 'paddle'])
    p.add_argument('--count', type=int, default=20)
    p.add_argument('--crop', type=Path)
    args = p.parse_args(); root = args.root.resolve()
    if args.action == 'prepare': prepare(root, args.count)
    elif args.action == 'run': run_arm(root, args.arm)
    elif args.action == 'finalize': finalize(root)
    else: worker(args.arm, args.crop.resolve(), root)


if __name__ == '__main__': main()
