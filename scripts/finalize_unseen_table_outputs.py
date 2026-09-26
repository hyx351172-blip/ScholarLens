"""No-gold v12 export/replay; recover only a version-metadata reporting failure.

Original worker results and their hashes remain untouched. No model reruns.
"""
import argparse
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import cv2
import numpy as np

from experiment_unseen_tables import ROOT, read, write, sha, verify, choose_baseline_table, choose_effective, parse_html_table
from table_structure import extract_table_structure, render_table_html
from table_header_reconstruction import repair_header


def metadata_only_failure(result):
    return (result.get('status') == 'failed' and result.get('error_type') == 'PackageNotFoundError'
            and result.get('error') == 'No package metadata was found for docling')


def package_versions():
    result = {}
    for name in ('docling', 'docling-slim', 'docling-core', 'docling-ibm-models', 'easyocr', 'torch'):
        try: result[name] = version(name)
        except PackageNotFoundError: result[name] = None
    return result


def export_baseline(raw):
    tables = raw.get('tables', []); selected = choose_baseline_table(tables)
    if selected is None: return None, {'status': 'no_table', 'table_count': 0}
    structure = extract_table_structure(tables[selected]); raw_html = render_table_html(structure)
    if raw_html is None: raise ValueError('Invalid Docling table topology')
    canonical = parse_html_table(raw_html)[1]
    return canonical, {'status': 'completed', 'table_count': len(tables), 'selected_table': selected,
                       'structure': structure}


def run(root):
    protected = read(root / 'frozen-inputs.json'); verify(protected)
    manifest = read(root / 'prepared/manifest.json')
    snapshots = {}
    for arm in ('baseline', 'paddle'):
        summary = read(root / arm / 'summary.json')
        if not summary['complete'] or len(summary['results']) != len(manifest['cases']): raise ValueError('Incomplete inference')
        snapshots.update({str(root / arm / p): digest for p, digest in summary['artifact_sha256'].items()})
        snapshots[str(root / arm / 'summary.json')] = sha(root / arm / 'summary.json')
    snapshots[str(Path(__file__).resolve())] = sha(Path(__file__).resolve())
    verify(snapshots)
    out = root / 'final'; out.mkdir(); rows = []
    for item in manifest['cases']:
        case = item['id']; dest = out / case; dest.mkdir()
        base = root / 'baseline' / case; src = root / 'paddle' / case
        original = read(base / 'result.json'); baseline = None
        info = {'status': original['status'], 'metadata_recovery': False}
        if original['status'] == 'completed' or metadata_only_failure(original):
            try:
                baseline, info = export_baseline(read(base / 'docling-document.json'))
                info['metadata_recovery'] = metadata_only_failure(original)
            except Exception as exc:
                info = {'status': 'export_failed', 'error_type': type(exc).__name__, 'error': str(exc),
                        'metadata_recovery': metadata_only_failure(original)}
        write(dest / 'baseline-export.json', info)
        if baseline: (dest / 'baseline.html').write_text(baseline, encoding='utf-8')
        gate = {'passed': False, 'reasons': []}; candidate = None; status = 'rejected'
        try:
            result = read(src / 'result.json')
            if result['status'] != 'completed': raise ValueError('Paddle worker failed: ' + result['status'])
            if any(result['capture_counts'].get(k) != 1 for k in ('match', 'render', 'geometry_reprocessing')):
                raise ValueError('Missing or ambiguous instrumented table')
            structure = (src / 'structure.html').read_text(encoding='utf-8'); parse_html_table(structure)
            crop = root / 'prepared' / item['crop']
            gray = cv2.imdecode(np.frombuffer(crop.read_bytes(), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            trace = repair_header(structure, read(src / 'binding-capture.json'), gray)
            write(dest / 'grid-trace.json', trace)
            candidate, gate, status = trace['html'], trace['gate'], trace['status']
        except Exception as exc:
            gate = {'passed': False, 'reasons': [str(exc)], 'error_type': type(exc).__name__}
        if candidate: (dest / 'candidate.html').write_text(candidate, encoding='utf-8')
        effective = choose_effective(baseline, candidate, gate)
        if effective: (dest / 'effective.html').write_text(effective, encoding='utf-8')
        row = {'id': case, 'page': item['page'], 'status': status, 'gate': gate,
               'baseline_available': baseline is not None, 'baseline_status': info['status'],
               'baseline_metadata_recovery': info.get('metadata_recovery', False),
               'effective_available': effective is not None, 'effective_source': 'v11' if gate['passed'] else 'baseline'}
        rows.append(row); write(dest / 'result.json', row)
        print(case, info['status'], status, gate, flush=True)
    verify(protected); verify(snapshots)
    artifacts = {p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()}
    write(out / 'summary.json', {'results': rows, 'artifact_sha256': artifacts, 'inputs_unchanged': True,
          'gold_access_in_inference': False, 'production_applied': False, 'paid_api_calls': 0,
          'source_sha256': snapshots, 'versions': package_versions(),
          'manifest_sha256': sha(root / 'prepared/manifest.json'),
          'adapter_note': 'Docling-slim distribution has no docling package metadata. Original workers saved raw conversion before version reporting failed. This stage only exports already saved native tables; zero reruns.'})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--root', required=True, type=Path)
    run(p.parse_args().root.resolve())
