"""Command-line interface for ScholarLens Evaluation Harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .reporting import compare_runs, render_comparison, render_run_report
from .runner import HarnessRunner, HarnessRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_ROOT = PROJECT_ROOT / "harness" / "runs"


def _path(value: str, root: Path = PROJECT_ROOT) -> Path:
    candidate = Path(value)
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def _load_run(reference: str, runs_root: Path) -> dict:
    candidate = Path(reference)
    if not candidate.is_absolute() and len(candidate.parts) == 1:
        candidate = runs_root / candidate / "run.json"
    else:
        candidate = _path(reference)
        if candidate.is_dir():
            candidate = candidate / "run.json"
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "run_id" not in payload:
        raise ValueError(f"not a Harness run: {candidate}")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a Harness config")
    validate.add_argument("--config", required=True)

    run = subparsers.add_parser("run", help="execute configured evaluation stages")
    run.add_argument("--config", required=True)
    run.add_argument("--run-id")
    run.add_argument("--stage", action="append", default=[])
    run.add_argument("--runs-dir")

    report = subparsers.add_parser("report", help="render a completed run")
    report.add_argument("--run", required=True)
    report.add_argument("--runs-dir")
    report.add_argument("--output")

    compare = subparsers.add_parser("compare", help="compare two completed runs")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--runs-dir")
    compare.add_argument("--output")
    compare.add_argument("--json-output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    runs_root = _path(args.runs_dir) if getattr(args, "runs_dir", None) else DEFAULT_RUNS_ROOT
    try:
        if args.command == "validate":
            config = load_config(_path(args.config))
            print(f"VALID {config.id}: {len(config.stages)} stage(s)")
            return 0
        if args.command == "run":
            config = load_config(_path(args.config))
            result = HarnessRunner(PROJECT_ROOT, runs_root=runs_root).run(
                config,
                run_id=args.run_id,
                stage_ids=args.stage,
            )
            print(f"{result['status']} {result['run_id']}")
            print(runs_root / result["run_id"] / "report.md")
            return {"PASS": 0, "FAIL": 2, "ERROR": 1}[result["status"]]
        if args.command == "report":
            report = render_run_report(_load_run(args.run, runs_root))
            if args.output:
                output = _path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(report, encoding="utf-8")
            print(report)
            return 0
        if args.command == "compare":
            comparison = compare_runs(
                _load_run(args.baseline, runs_root),
                _load_run(args.candidate, runs_root),
            )
            markdown = render_comparison(comparison)
            if args.output:
                output = _path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(markdown, encoding="utf-8")
            if args.json_output:
                json_output = _path(args.json_output)
                json_output.parent.mkdir(parents=True, exist_ok=True)
                json_output.write_text(
                    json.dumps(comparison, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            print(markdown)
            return 0
    except (ConfigError, HarnessRuntimeError, FileNotFoundError, FileExistsError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1

