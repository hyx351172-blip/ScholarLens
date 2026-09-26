"""No-gold offline v10 replay of fixed v8 structure + v9 detector/OCR captures."""
import argparse
from pathlib import Path
import struct
import time

from audit_table_decoder import read, write, sha, preflight, parse_html_table
from table_grid_binding import bind_grid, POLICY


FROZEN_MANIFEST = 'ec607623012941880f473966b1ddbe4e345919a886561044d6604175054411de'
CAPTURES = {
    'page-0cbdcfa9-3248-4e54-8704-2bc73e6d29e7': 'f68a8bd0f10470f19316252a4e8816cdb8f3b4cb79c13343c3f153b0a649c1f9',
    'page-14a6b411-9097-4eec-86da-92075868d243': '0b955ecebf7f2c811ad3cac15663af644a050a9fcdc138584fcdb20de8620728',
}


def fresh_output(output, inputs):
    output = output.resolve()
    if output.exists() or any(output == p.resolve() or output in p.resolve().parents or p.resolve() in output.parents for p in inputs):
        raise ValueError('Fresh output outside protected inputs required')


def verify_hashes(hashes):
    for name, digest in hashes.items():
        if sha(Path(name)) != digest: raise ValueError('Frozen input changed: ' + name)


def verify_run(root, summary):
    if not summary['protected_inputs_unchanged']: raise ValueError('Input integrity failed')
    verify_hashes(summary['protected_hashes'])
    for relative, digest in summary['artifact_sha256'].items():
        path = (root / relative).resolve()
        if root.resolve() not in path.parents: raise ValueError('Artifact path escape')
        if sha(path) != digest: raise ValueError('Run artifact changed: ' + relative)


def png_size(path):
    with path.open('rb') as f: header = f.read(24)
    if len(header) != 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
        raise ValueError('Invalid frozen PNG header')
    return list(struct.unpack('>II', header[16:24]))


def run(prepared, v8, v9, output):
    prepared, v8, v9, output = [p.resolve() for p in (prepared, v8, v9, output)]
    fresh_output(output, [prepared, v8, v9])
    manifest = preflight(prepared, output)
    if sha(prepared / 'manifest.json') != FROZEN_MANIFEST: raise ValueError('Unrecognized frozen cohort')
    prior = read(v9 / 'summary.json')
    if prior['manifest_sha256'] != FROZEN_MANIFEST: raise ValueError('v9 manifest mismatch')
    paths = [prepared / 'manifest.json', v9 / 'summary.json', v8 / 'summary.json', Path(__file__).resolve(),
             Path(__file__).with_name('table_grid_binding.py').resolve()]
    for item in manifest['results']:
        case = item['id']; struct_path = v8 / 'extended' / case / 'structure.html'
        paths += [prepared / item['crop'], prepared / case / 'baseline.html', struct_path]
        if 'source' in manifest:
            paths += [Path(manifest['source']) / 'artifacts' / case / name for name in ('document.json', 'docling-document.json')]
            paths.append(Path(manifest['images']) / item['page'])
        if case in CAPTURES:
            capture = v9 / case / 'binding-capture.json'; response = v9 / case / 'response.json'
            if sha(capture) != CAPTURES[case]: raise ValueError('Frozen capture hash mismatch')
            r = read(response)
            if r['structure_sha256'] != sha(struct_path) or r['crop_sha256'] != item['crop_sha256']:
                raise ValueError('Structure/crop provenance mismatch')
            paths += [capture, response]
    hashes = {str(p): sha(p) for p in paths}
    output.mkdir(parents=True)
    summary = {'experiment': 'table-grid-binding-v10', 'policy': POLICY, 'gold_access_in_inference': False,
               'production_applied': False, 'model_calls': 0, 'paid_api_calls': 0,
               'manifest_sha256': FROZEN_MANIFEST, 'protected_hashes': hashes, 'results': []}
    write(output / 'input-integrity.json', hashes)
    for item in manifest['results']:
        case = item['id']; dest = output / case; dest.mkdir()
        row = {'id': case, 'page': item['page'], 'gate': {'passed': False, 'reasons': []}}
        started = time.perf_counter()
        raw = (v8 / 'extended' / case / 'structure.html').read_text(encoding='utf-8')
        try:
            parse_html_table(raw)
        except ValueError as exc:
            row.update(status='invalid_v8_structure_baseline_retained', error=str(exc))
            row['gate']['reasons'] = ['invalid_v8_structure']
        else:
            if case not in CAPTURES: raise ValueError('Valid structure without approved frozen capture')
            trace = bind_grid(raw, read(v9 / case / 'binding-capture.json'), png_size(prepared / item['crop']))
            write(dest / 'grid-trace.json', trace)
            row.update(gate=trace['gate'], status='review_eligible' if trace['gate']['passed'] else 'grid_rejected_baseline_retained',
                       logical_cells=trace['logical_cells'], empty_cells=len(trace['empty_cell_ids']),
                       ocr_count=trace['ocr_count'], unassigned_ocr=len(trace['unassigned_ocr_ids']),
                       boundaries={a: len(v['boundaries']) for a, v in trace['axes'].items()})
            if trace['html'] is not None:
                (dest / 'raw-candidate.html').write_text(trace['html'], encoding='utf-8')
        row['replay_seconds'] = time.perf_counter() - started
        write(dest / 'result.json', row); summary['results'].append(row)
        print(case, row['status'], row['gate']['reasons'], flush=True)
    verify_hashes(hashes)
    summary['protected_inputs_unchanged'] = True
    summary['artifact_sha256'] = {p.relative_to(output).as_posix(): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    write(output / 'summary.json', summary)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'v8', 'v9', 'output'): p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args(); run(a.prepared, a.v8, a.v9, a.output)
