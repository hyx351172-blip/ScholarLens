import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from harness.cli import main as harness_main
from harness.config import ConfigError, load_config
from harness.reporting import compare_runs, render_comparison
from harness.runner import HarnessRunner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _config(*, source: dict, threshold: float = 0.8) -> dict:
    return {
        "schema_version": "1.0",
        "id": "unit-harness",
        "description": "Harness unit fixture",
        "stages": [
            {
                "id": "retrieval",
                "label": "Retrieval quality",
                "source": source,
                "metrics": [
                    {
                        "id": "recall",
                        "label": "Recall@K",
                        "path": "summary.recall",
                        "unit": "ratio",
                        "direction": "higher",
                    },
                    {
                        "id": "latency",
                        "label": "Mean latency",
                        "path": "summary.latency",
                        "unit": "seconds",
                        "direction": "lower",
                    },
                ],
                "gates": [
                    {
                        "id": "minimum_recall",
                        "metric": "recall",
                        "operator": ">=",
                        "value": threshold,
                    }
                ],
            }
        ],
    }


class HarnessConfigTests(unittest.TestCase):
    def test_rejects_duplicate_stage_and_unknown_gate_metric(self):
        """AC-501.1: declarations fail before any evaluator is executed."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = _config(source={"kind": "artifact", "path": "result.json"})
            payload["stages"].append(payload["stages"][0])
            path = root / "config.json"
            _write_json(path, payload)
            with self.assertRaisesRegex(ConfigError, "duplicate stage"):
                load_config(path)

            payload = _config(source={"kind": "artifact", "path": "result.json"})
            payload["stages"][0]["gates"][0]["metric"] = "missing"
            _write_json(path, payload)
            with self.assertRaisesRegex(ConfigError, "unknown metric"):
                load_config(path)


class HarnessRunnerTests(unittest.TestCase):
    def test_replay_run_copies_artifact_and_writes_complete_snapshot(self):
        """AC-501.2/501.3: a replay becomes an auditable PASS run."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_json(root / "fixture.json", {"summary": {"recall": 0.9, "latency": 1.2}})
            config_path = root / "config.json"
            _write_json(
                config_path,
                _config(source={"kind": "artifact", "path": "fixture.json"}),
            )
            result = HarnessRunner(root).run(load_config(config_path), run_id="replay-pass")

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["stages"][0]["status"], "PASS")
            run_dir = root / "harness" / "runs" / "replay-pass"
            self.assertTrue((run_dir / "config.json").is_file())
            self.assertTrue((run_dir / "artifacts" / "retrieval.json").is_file())
            self.assertTrue((run_dir / "run.json").is_file())
            self.assertIn("# ScholarLens Evaluation Harness", (run_dir / "report.md").read_text(encoding="utf-8"))

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                HarnessRunner(root).run(load_config(config_path), run_id="replay-pass")

    def test_gate_failure_is_no_go_instead_of_runtime_error(self):
        """AC-501.3: quality failure remains distinct from execution failure."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_json(root / "fixture.json", {"summary": {"recall": 0.5, "latency": 1.2}})
            config_path = root / "config.json"
            _write_json(
                config_path,
                _config(source={"kind": "artifact", "path": "fixture.json"}),
            )
            result = HarnessRunner(root).run(load_config(config_path), run_id="replay-fail")

            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["stages"][0]["status"], "FAIL")
            self.assertFalse(result["stages"][0]["gates"][0]["passed"])

    def test_command_stage_accepts_quality_exit_and_redacts_environment(self):
        """AC-501.2/501.3: logs never persist expanded secret placeholders."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = (
                "import json,pathlib,sys; "
                "pathlib.Path(sys.argv[1]).write_text(json.dumps({'summary': "
                "{'recall': 0.9, 'latency': 0.4}}), encoding='utf-8'); "
                "print(sys.argv[2]); raise SystemExit(2)"
            )
            source = {
                "kind": "command",
                "argv": ["{python}", "-c", code, "{artifact}", "${HARNESS_TEST_SECRET}"],
                "allowed_exit_codes": [0, 2],
                "timeout_seconds": 30,
            }
            config_path = root / "config.json"
            _write_json(config_path, _config(source=source))
            with patch.dict(os.environ, {"HARNESS_TEST_SECRET": "do-not-persist"}):
                result = HarnessRunner(root, python_executable=sys.executable).run(
                    load_config(config_path), run_id="command-pass"
                )

            self.assertEqual(result["status"], "PASS")
            stage = result["stages"][0]
            self.assertEqual(stage["command_exit_code"], 2)
            log = (root / "harness" / "runs" / "command-pass" / "logs" / "retrieval.log").read_text(encoding="utf-8")
            self.assertNotIn("do-not-persist", log)
            self.assertIn("[REDACTED]", log)
            snapshot = (root / "harness" / "runs" / "command-pass" / "config.json").read_text(encoding="utf-8")
            self.assertIn("${HARNESS_TEST_SECRET}", snapshot)
            self.assertNotIn("do-not-persist", snapshot)

    def test_missing_preflight_environment_stops_before_command(self):
        """AC-501.1/501.3: paid commands never start after a failed preflight."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                "kind": "command",
                "argv": [
                    "{python}",
                    "-c",
                    "raise RuntimeError('must not run')",
                    "{artifact}",
                ],
            }
            payload = _config(source=source)
            payload["preflight"] = {"required_env": ["HARNESS_MISSING_ENV"]}
            config_path = root / "config.json"
            _write_json(config_path, payload)
            with patch.dict(os.environ, {}, clear=True):
                result = HarnessRunner(root).run(
                    load_config(config_path), run_id="preflight-error"
                )

            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(result["stages"], [])
            self.assertEqual(result["preflight"]["checks"][0]["status"], "ERROR")


class HarnessComparisonTests(unittest.TestCase):
    def test_compare_is_direction_aware(self):
        """AC-501.4: higher recall and lower latency are both improvements."""
        baseline = {
            "run_id": "baseline",
            "stages": [
                {
                    "id": "retrieval",
                    "metrics": [
                        {"id": "recall", "value": 0.8, "direction": "higher", "unit": "ratio"},
                        {"id": "latency", "value": 1.0, "direction": "lower", "unit": "seconds"},
                    ],
                }
            ],
        }
        candidate = {
            "run_id": "candidate",
            "stages": [
                {
                    "id": "retrieval",
                    "metrics": [
                        {"id": "recall", "value": 0.9, "direction": "higher", "unit": "ratio"},
                        {"id": "latency", "value": 0.8, "direction": "lower", "unit": "seconds"},
                    ],
                }
            ],
        }
        comparison = compare_runs(baseline, candidate)

        self.assertEqual(comparison["summary"]["improved"], 2)
        self.assertEqual(comparison["summary"]["regressed"], 0)
        self.assertIn("Recall", render_comparison(comparison))


class HarnessCliTests(unittest.TestCase):
    def test_validate_run_report_and_compare_commands(self):
        """AC-501.5: all public CLI paths operate on the zero-cost replay."""
        project_root = Path(__file__).resolve().parents[1]
        config = project_root / "harness/configs/validated-replay-v1.json"
        with tempfile.TemporaryDirectory() as directory:
            runs = Path(directory)
            output = StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                self.assertEqual(
                    harness_main(["validate", "--config", str(config)]), 0
                )
                self.assertEqual(
                    harness_main(
                        [
                            "run",
                            "--config",
                            str(config),
                            "--run-id",
                            "cli-replay",
                            "--runs-dir",
                            str(runs),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    harness_main(
                        [
                            "report",
                            "--run",
                            "cli-replay",
                            "--runs-dir",
                            str(runs),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    harness_main(
                        [
                            "compare",
                            "--baseline",
                            "cli-replay",
                            "--candidate",
                            "cli-replay",
                            "--runs-dir",
                            str(runs),
                        ]
                    ),
                    0,
                )
            self.assertIn("PASS cli-replay", output.getvalue())
            self.assertIn("ScholarLens Harness Comparison", output.getvalue())


if __name__ == "__main__":
    unittest.main()
