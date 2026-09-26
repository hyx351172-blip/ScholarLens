"""Offline, no-gold SLANeXt static decoder audit and controlled length experiment.

This is NOT a production model patch. Only a pinned downloaded graph is cloned;
weights/preprocessing remain identical. No network clients or model discovery.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/Information-Extraction/unified/parsers'))
from html_table_candidate import parse_html_table

GRAPH_SHA = '5b872f08e74f628ca1db8405db147e82e6e0c7cb358e101fd01cdafc946632d8'
MODELS = ('SLANeXt_wired', 'SLANeXt_wireless')
CLASSIFIER = 'PP-LCNet_x1_0_table_cls'
FILES = ('inference.json', 'inference.pdiparams', 'inference.yml', 'config.json')
CACHE = ROOT / 'backend/data/benchmarks/model_cache/tablemagic/official_models'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def graph_nodes(graph):
    ops = graph['program']['regions'][0]['blocks'][0]['ops']
    nodes = {}
    for op in ops:
        outputs = op.get('O', [])
        if isinstance(outputs, dict):  # PIR parameter nodes use one object.
            outputs = [outputs]
        for value in outputs:
            if value['%'] in nodes:
                raise ValueError('Duplicate top-level SSA output')
            nodes[value['%']] = op
    return nodes


def attribute(op, name):
    found = [a['AT'] for a in op['A'] if a['N'] == name]
    if len(found) != 1:
        raise ValueError('Unknown graph attribute layout')
    return found[0]


def graph_audit(graph):
    """Check the known SSA dependency chain; never globally replace a number."""
    try:
        nodes = graph_nodes(graph)
        for out, inputs in ((2369, [2361, 2367, 2368]), (2375, [2361, 2373, 2374]), (2380, [2361, 2379])):
            if nodes[out]['#'] != '0.combine' or [i['%'] for i in nodes[out]['I']] != inputs:
                raise ValueError('Changed decoder buffer dependency')
        bound_op = nodes[2389]
        if bound_op['#'] != '1.assign_value_':
            raise ValueError('Unknown bound operation')
        values = attribute(bound_op, 'values')['D']
        if len(values) != 1:
            raise ValueError('Non-scalar loop bound')
        bound = values[0]['D']
        if bound not in (500.0, 1000.0):
            raise ValueError('Unsupported loop bound')
        for out in (2367, 2373, 2379):
            if nodes[out]['#'] != '1.full' or attribute(nodes[out], 'value')['D'] != bound + 1:
                raise ValueError('Decoder loop/capacity mismatch')
        if (nodes[2393]['#'] != '1.scale' or [i['%'] for i in nodes[2393]['I']] != [2389, 2392]
                or attribute(nodes[2393], 'bias')['D'] != 1.0
                or nodes[2394]['#'] != '1.less_than' or [i['%'] for i in nodes[2394]['I']] != [2391, 2393]):
            raise ValueError('Unknown loop comparison')
        return {'max_text_length': int(bound), 'max_steps': int(bound + 1),
                'loop_bound_ssa': 2389, 'capacity_ssa': [2367, 2373, 2379]}
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError('Unrecognized exported graph schema') from exc


def patch_graph(graph, max_text_length):
    if type(max_text_length) is not int or max_text_length != 1000:
        raise ValueError('Only bounded 500-to-1000 experiment is supported')
    if graph_audit(graph)['max_text_length'] != 500:
        raise ValueError('Only original graph may be extended')
    result = copy.deepcopy(graph)
    nodes = graph_nodes(result)
    attribute(nodes[2389], 'values')['D'][0]['D'] = float(max_text_length)
    for out in (2367, 2373, 2379):
        attribute(nodes[out], 'value')['D'] = float(max_text_length + 1)
    graph_audit(result)
    return result


def clone_model(source, dest):
    if sha(source / 'inference.json') != GRAPH_SHA:
        raise ValueError('Unknown model graph digest; re-audit required')
    if dest.exists() or source == dest or source in dest.parents or dest in source.parents:
        raise ValueError('Fresh independent model clone required')
    graph = patch_graph(read(source / 'inference.json'), 1000)
    before = {f: sha(source / f) for f in FILES}
    dest.mkdir(parents=True)
    for name in FILES[1:]:
        shutil.copyfile(source / name, dest / name)
        if sha(dest / name) != before[name]:
            raise ValueError('Copied model file hash mismatch')
    write(dest / 'inference.json', graph)
    if before != {f: sha(source / f) for f in FILES}:
        raise ValueError('Original model changed during cloning')
    audit = {'source_sha256': before, 'clone_sha256': {f: sha(dest / f) for f in FILES},
             'experimental': True, 'changed_constants': 4,
             'before': graph_audit(read(source / 'inference.json')), 'after': graph_audit(graph)}
    write(dest / 'clone-audit.json', audit)
    return audit


def inspect_probabilities(probs, vocabulary, eos_id, limit):
    import numpy as np
    a = np.asarray(probs)
    if (type(limit) is not int or limit not in (500, 1000) or not isinstance(vocabulary, list)
            or not 2 <= len(vocabulary) <= 512 or type(eos_id) is not int
            or not 0 <= eos_id < len(vocabulary)
            or a.ndim != 3 or a.shape[0] != 1 or a.shape[2] != len(vocabulary)
            or not 1 <= a.shape[1] <= limit + 1 or not np.isfinite(a).all()
            or np.any(a < 0) or np.any(a > 1) or not np.allclose(a.sum(axis=2), 1, atol=1e-4)):
        raise ValueError('Invalid structure probability tensor')
    ids = a.argmax(axis=2)[0].tolist()
    eos = ids.index(eos_id) if eos_id in ids else None
    cap = len(ids) == limit + 1
    termination = ('invalid_eos_at_start' if eos == 0 else 'eos' if eos is not None
                   else 'length_limit' if cap else 'unknown')
    return {'shape': list(a.shape), 'steps': len(ids), 'max_text_length': limit,
            'max_steps': limit + 1, 'hit_step_cap': cap, 'eos_id': eos_id, 'eos_index': eos,
            'termination': termination, 'vocabulary': vocabulary, 'token_ids': ids,
            'tokens': [vocabulary[i] for i in ids], 'confidence': a.max(axis=2)[0].tolist()}


def validate_output(raw_html, inspection):
    try:
        structure, _ = parse_html_table(raw_html)
        syntax = {'valid': True, 'rows': structure['num_rows'], 'cols': structure['num_cols'],
                  'cells': len(structure['table_cells'])}
    except ValueError as exc:
        syntax = {'valid': False, 'error': str(exc)}
    return {'valid': inspection['termination'] == 'eos' and syntax['valid'], 'html_validation': syntax}


def preflight(prepared, output):
    prepared, output = prepared.resolve(), output.resolve()
    if output.exists() or output == prepared or prepared in output.parents or output in prepared.parents:
        raise ValueError('Fresh output outside frozen inputs required')
    if output == CACHE or CACHE in output.parents or output in CACHE.parents:
        raise ValueError('Output may not overlap downloaded model cache')
    manifest = read(prepared / 'manifest.json')
    for key in ('source', 'images'):
        if key in manifest:
            p = Path(manifest[key]).resolve()
            if p == output or p in output.parents or output in p.parents:
                raise ValueError('Output overlaps input artifacts')
    items = manifest['results']
    if not 1 <= len(items) <= 3 or len({i['id'] for i in items}) != len(items):
        raise ValueError('Expected 1..3 unique frozen cases')
    for item in items:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', item['id']):
            raise ValueError('Unsafe case id')
        crop = (prepared / item['crop']).resolve()
        if prepared not in crop.parents or sha(crop) != item['crop_sha256']:
            raise ValueError('Crop path/hash mismatch')
        if sha(prepared / item['id'] / 'baseline.html') != item['baseline_sha256']:
            raise ValueError('Baseline hash mismatch')
        if 'source' in manifest and 'images' in manifest:
            source = Path(manifest['source']).resolve() / 'artifacts' / item['id']
            images = Path(manifest['images']).resolve()
            image = (images / item['page']).resolve()
            if images not in image.parents:
                raise ValueError('Source image path escape')
            for path, digest in ((image, item['image_sha256']),
                                 (source / 'document.json', item['document_sha256']),
                                 (source / 'docling-document.json', item['native_sha256'])):
                if sha(path) != digest:
                    raise ValueError('Frozen source artifact hash mismatch')
    return manifest


def pair_summary(original, extended):
    for key in ('crop_sha256', 'model', 'weight_sha256', 'preprocess_sha256', 'vocabulary'):
        if original[key] != extended[key]:
            raise ValueError('Confounded pair: ' + key)
    a, b = original['token_ids'], extended['token_ids']
    prefix = len(b) >= len(a) and a == b[:len(a)]
    return {'prefix_identical': prefix, 'original_steps': len(a), 'extended_steps': len(b),
            'length_limit_resolved': prefix and original['termination'] == 'length_limit' and extended['termination'] == 'eos',
            'early_eos_control_identical': (a == b) if original['termination'] == 'eos' else None,
            'original_termination': original['termination'], 'extended_termination': extended['termination']}


def local_path(path):
    # Paddle's Windows C++ model loader requires ASCII; Python still handles images.
    value = path.resolve().relative_to(ROOT).as_posix()
    if not value.isascii():
        raise ValueError('Use ASCII project-relative model/output paths')
    return value


def worker(crop, dest, model_root, limit):
    import numpy as np
    from PIL import Image
    from paddlex import create_predictor
    from importlib.metadata import version

    def predictor(name, root):
        directory = root / name
        for file in ('inference.json', 'inference.pdiparams', 'inference.yml'):
            if not (directory / file).is_file():
                raise ValueError('Local model incomplete; downloads are prohibited')
        return create_predictor(model_name=name, model_dir=local_path(directory), device='cpu',
                                engine='paddle_static', engine_config={'run_mode': 'paddle', 'cpu_threads': 4})

    start = time.monotonic()
    with Image.open(crop) as image:
        bgr = np.asarray(image.convert('RGB'))[:, :, ::-1].copy()
    cls = predictor(CLASSIFIER, CACHE)
    classified = list(cls(bgr))
    if len(classified) != 1:
        raise ValueError('Expected one classifier output')
    item = classified[0]
    scores = np.asarray(item['scores'])
    label = item['label_names'][int(np.argmax(scores))]
    if label not in ('wired_table', 'wireless_table'):
        raise ValueError('Unknown table class')
    name = 'SLANeXt_wired' if label == 'wired_table' else 'SLANeXt_wireless'
    model_dir = model_root / name
    audit = graph_audit(read(model_dir / 'inference.json'))
    if audit['max_text_length'] != limit:
        raise ValueError('Requested limit does not match graph')
    model = predictor(name, model_root)
    original_post = model.postprocessors
    capture = {}

    def spy(*args, **kwargs):
        if capture:
            raise ValueError('Only one single-image decoder batch allowed')
        pred = kwargs['pred']
        if len(pred) not in (1, 2):
            raise ValueError('Unexpected decoder outputs')
        probs = pred[-1]
        capture.update(inspect_probabilities(probs, list(original_post.character),
                       int(original_post.get_beg_end_flag_idx('end')), limit))
        np.savez_compressed(dest / 'decoder-tensors.npz', **{f'output_{i}': v for i, v in enumerate(pred)})
        write(dest / 'decoder.json', capture)
        return original_post(*args, **kwargs)

    model.postprocessors = spy
    initialized = time.monotonic()
    results = list(model(bgr))
    finished = time.monotonic()
    if len(results) != 1 or not capture:
        raise ValueError('Expected one instrumented result')
    raw = ''.join(results[0]['structure'])
    (dest / 'structure.html').write_text(raw, encoding='utf-8')
    config_serialized = json.dumps(model.config, sort_keys=True, ensure_ascii=False).encode('utf-8')
    write(dest / 'predictor-config.json', model.config)
    result = dict(capture, status='completed', model=name, classifier_label=label,
                  classifier_scores=scores.tolist(), classifier_labels=list(item['label_names']),
                  crop_sha256=sha(crop), graph_sha256=sha(model_dir / 'inference.json'),
                  weight_sha256=sha(model_dir / 'inference.pdiparams'),
                  preprocess_sha256=hashlib.sha256(config_serialized).hexdigest(),
                  validation=validate_output(raw, capture), total_seconds=round(finished - start, 4),
                  initialization_seconds=round(initialized - start, 4), inference_seconds=round(finished - initialized, 4),
                  versions={p: version(p) for p in ('paddlepaddle', 'paddlex', 'numpy')})
    write(dest / 'result.json', result)


def run(prepared, output, python):
    manifest = preflight(prepared, output)
    if not python.is_file():
        raise ValueError('Isolated Paddle Python not found')
    # Read all required models before any attempt. No automatic model acquisition.
    model_hashes = {n: {f: sha(CACHE / n / f) for f in FILES} for n in (*MODELS, CLASSIFIER)}
    if any(model_hashes[n]['inference.json'] != GRAPH_SHA for n in MODELS):
        raise ValueError('Unknown structure model graph')
    output.mkdir(parents=True)
    summary = {'schema_version': '1.0', 'experiment': 'table-decoder-v8', 'gold_access': False,
               'production_applied': False, 'ocr_text_evaluated': False, 'paid_calls': 0,
               'manifest_sha256': sha(prepared / 'manifest.json'), 'model_hashes_before': model_hashes,
               'settings': {'device': 'cpu', 'cpu_threads': 4, 'mkldnn': False, 'deadline_seconds': 300,
                            'retries': 0, 'max_cases_per_arm': 3, 'extended_limit': 1000},
               'attempts': [], 'pairs': []}
    journal = output / 'summary.json'
    env = dict(os.environ, PYTHONUTF8='1', PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',
               PADDLE_PDX_CACHE_HOME='backend/data/benchmarks/model_cache/tablemagic',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    records = {}
    for arm, limit in (('original', 500), ('extended', 1000)):
        model_root = CACHE
        if arm == 'extended':
            if not any(r.get('termination') == 'length_limit' for r in records.values()):
                summary['extension_skipped'] = 'No captured original length-limit exhaustion'
                break
            model_root = output / 'experimental-models'
            summary['clones'] = {name: clone_model(CACHE / name, model_root / name) for name in MODELS}
        for item in manifest['results']:
            crop = (prepared / item['crop']).resolve()
            if sha(crop) != item['crop_sha256']:
                raise ValueError('Crop changed after preflight')
            dest = output / arm / item['id']; dest.mkdir(parents=True)
            attempt = {'id': item['id'], 'arm': arm, 'status': 'attempted_no_result'}
            summary['attempts'].append(attempt); write(journal, summary)
            print(f'{arm}: {item["id"]}', flush=True)
            start = time.monotonic()
            with (dest / 'worker.log').open('w', encoding='utf-8') as log:
                try:
                    proc = subprocess.run([str(python), str(Path(__file__).resolve()), '--worker',
                        '--crop', str(crop), '--output', str(dest), '--model-root', str(model_root),
                        '--limit', str(limit)], cwd=ROOT, env=env, stdout=log,
                        stderr=subprocess.STDOUT, timeout=300, check=False)
                    attempt['exit_code'] = proc.returncode
                    result = read(dest / 'result.json') if proc.returncode == 0 and (dest / 'result.json').is_file() else {'status': 'worker_failed'}
                except subprocess.TimeoutExpired:
                    result = {'status': 'deadline_exceeded'}
            attempt.update(status=result['status'], process_seconds=round(time.monotonic() - start, 4))
            if result['status'] == 'completed':
                attempt.update({k: result[k] for k in ('model', 'steps', 'termination', 'eos_index', 'validation')})
                if arm == 'original':
                    records[item['id']] = result
                elif item['id'] in records:
                    summary['pairs'].append(dict(id=item['id'], **pair_summary(records[item['id']], result)))
            write(journal, summary)
            if result['status'] != 'completed':
                summary['stopped'] = 'Fail closed on local worker failure; no retry'
                break
        if summary.get('stopped'):
            break
    summary['model_hashes_after'] = {n: {f: sha(CACHE / n / f) for f in FILES} for n in (*MODELS, CLASSIFIER)}
    summary['original_models_unchanged'] = model_hashes == summary['model_hashes_after']
    # Reuse preflight validation with a fresh, never-created sentinel path.
    preflight(prepared, output.parent / (output.name + '-integrity-check-only'))
    summary['frozen_inputs_unchanged'] = sha(prepared / 'manifest.json') == summary['manifest_sha256']
    write(journal, summary)
    if not summary['original_models_unchanged'] or not summary['frozen_inputs_unchanged']:
        raise ValueError('Integrity verification failed')
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker', action='store_true')
    p.add_argument('--crop', type=Path)
    p.add_argument('--model-root', type=Path, default=CACHE)
    p.add_argument('--limit', type=int, choices=(500, 1000), default=500)
    p.add_argument('--prepared', type=Path, default=ROOT / 'output/benchmarks/omnidocbench-table-vlm-v5/prepared')
    p.add_argument('--python', type=Path, default=ROOT / 'backend/data/benchmarks/tablemagic/.venv/Scripts/python.exe')
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if a.worker:
        worker(a.crop.resolve(), a.output.resolve(), a.model_root.resolve(), a.limit)
    else:
        result = run(a.prepared.resolve(), a.output.resolve(), a.python.resolve())
        if result.get('stopped'):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
