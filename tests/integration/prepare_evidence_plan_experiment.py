"""Freeze a paired development experiment without overwriting baseline artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    source = ROOT/'output/qasper-guard-validation-v1'
    out = ROOT/'output/qasper-evidence-plan-v1'
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    for name, digest in manifest['file_sha256'].items():
        assert hashlib.sha256((source/name).read_bytes()).hexdigest() == digest
    manifest.update(evidence_planning=True, baseline=str(source.relative_to(ROOT)),
                    interpretation='Paired development experiment, not held-out validation',
                    planner_sha256=hashlib.sha256((ROOT/'backend/chat/evidence_plan.py').read_bytes()).hexdigest())
    out.mkdir()  # Refuse overwrite.
    for name in ('inputs.json', 'labels.json'):
        (out/name).write_bytes((source/name).read_bytes())
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(out)


if __name__ == '__main__':
    main()
