"""Run current-code tests; frozen experiment suites run in their archived checkout.

The excluded modules are not skipped: run all ten together against the exact
historical source/fixtures referenced by their manifests.  Their preflight
hashes must continue rejecting the modified production checkout.
"""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARCHIVED_MODULES = frozenset({
    "test_prepare_qualified_claim_support",
    "test_prepare_qualified_evidence_ids",
    "test_qualified_claim_support_live",
    "test_qualified_ids_pilot",
    "test_qualified_quote_alignment_replay",
    "test_qualified_support_remaining",
    "test_scifact_verifier",
    "test_scifact_verifier_live",
    "test_selected_claim_support",
    "test_selected_claim_support_live",
})
FROZEN_SOURCE_SHA256 = {
    "backend/chat/answer_guard.py": "95c5a1eae60e7146085dd0e94d538aba4d44c4bc924a3428e72dbcee97f192cb",
    "backend/chat/kb_chat.py": "61dc1f00552a4f4c4722acaf8507e682ea3dd7a6e9ac9648fb93af69629637cc",
}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def run_archived_suite(archive: Path):
    archive = archive.resolve()
    if archive == ROOT.resolve():
        raise ValueError("The frozen suite must run against a separate historical checkout")
    for relative, expected in FROZEN_SOURCE_SHA256.items():
        source = archive / relative
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Historical source fingerprint mismatch: {relative}")
    for module in ARCHIVED_MODULES:
        if not (archive / "tests" / f"{module}.py").is_file():
            raise ValueError(f"Missing historical test module: {module}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(archive)
    command = [sys.executable, "-X", "utf8", "-m", "unittest",
               *(f"tests.{module}" for module in sorted(ARCHIVED_MODULES)), "-q"]
    print(f"Running {len(ARCHIVED_MODULES)} frozen modules in {archive}", flush=True)
    return subprocess.run(command, cwd=archive, env=env, check=False).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-root", type=Path,
                        help="also run the frozen experiment tests against a separate archived checkout")
    args = parser.parse_args()
    loader = unittest.TestLoader()
    discovered = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
    current, archived = [], []
    for case in flatten(discovered):
        module = case.id().split(".")[-3]
        (archived if module in ARCHIVED_MODULES else current).append(case)
    found = {case.id().split(".")[-3] for case in archived}
    if found != ARCHIVED_MODULES:
        raise RuntimeError(f"archived_module_inventory_changed: {sorted(found ^ ARCHIVED_MODULES)}")
    print(f"Discovered {len(current) + len(archived)} tests: "
          f"current={len(current)}, frozen_archive={len(archived)}", flush=True)
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(current))
    if not result.wasSuccessful():
        return 1
    if not args.historical_root:
        print("Frozen tests were not run here; pass --historical-root for both suites.", flush=True)
        return 0
    if run_archived_suite(args.historical_root):
        return 1
    print(f"PASS: {len(current)} current + {len(archived)} historical tests", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
