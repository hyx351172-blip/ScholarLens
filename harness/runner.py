"""Execute replay and command stages into auditable Harness runs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import GateSpec, HarnessConfig, MetricSpec, StageSpec
from .reporting import render_run_report


_ENV_REFERENCE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class HarnessRuntimeError(RuntimeError):
    """Raised for infrastructure failures rather than failed quality gates."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _lookup(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise HarnessRuntimeError(f"artifact has no value at {path!r}")
    if isinstance(current, (dict, list)):
        raise HarnessRuntimeError(f"metric path {path!r} must resolve to a scalar")
    return current


def _evaluate_gate(actual: Any, gate: GateSpec) -> bool:
    expected = gate.value
    try:
        if gate.operator == ">=":
            return actual >= expected
        if gate.operator == "<=":
            return actual <= expected
        if gate.operator == ">":
            return actual > expected
        if gate.operator == "<":
            return actual < expected
        if gate.operator == "==":
            return actual == expected
        if gate.operator == "!=":
            return actual != expected
    except TypeError as exc:
        raise HarnessRuntimeError(
            f"gate {gate.id} cannot compare {actual!r} {gate.operator} {expected!r}"
        ) from exc
    raise HarnessRuntimeError(f"unsupported gate operator: {gate.operator}")


class HarnessRunner:
    def __init__(
        self,
        project_root: str | Path,
        *,
        runs_root: str | Path | None = None,
        python_executable: str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.runs_root = (
            Path(runs_root).resolve()
            if runs_root is not None
            else self.project_root / "harness" / "runs"
        )
        self.python_executable = python_executable or sys.executable

    def _project_path(self, value: str) -> Path:
        path = (self.project_root / value).resolve()
        if not path.is_relative_to(self.project_root):
            raise HarnessRuntimeError(f"path escapes project root: {value}")
        return path

    def _git_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError:
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    def _preflight(self, config: HarnessConfig) -> dict[str, Any]:
        checks: list[dict[str, str]] = []
        failed = False
        for name in config.preflight.required_env:
            exists = bool(os.getenv(name, "").strip())
            failed = failed or not exists
            checks.append(
                {
                    "id": f"env:{name}",
                    "status": "PASS" if exists else "ERROR",
                    "message": "configured" if exists else "missing required environment variable",
                }
            )
        for service in config.preflight.services:
            try:
                with urllib.request.urlopen(service.url, timeout=service.timeout_seconds) as response:
                    ok = 200 <= int(response.status) < 300
                    message = f"HTTP {response.status}"
            except Exception as exc:  # Network failures have platform-specific subclasses.
                ok = False
                message = f"unavailable ({type(exc).__name__})"
            failed = failed or not ok
            checks.append(
                {
                    "id": f"service:{service.name}",
                    "status": "PASS" if ok else "ERROR",
                    "message": message,
                }
            )
        return {"status": "ERROR" if failed else "PASS", "checks": checks}

    @staticmethod
    def _redact(text: str, secrets: list[str]) -> str:
        redacted = text
        for secret in sorted({value for value in secrets if value}, key=len, reverse=True):
            redacted = redacted.replace(secret, "[REDACTED]")
        return redacted

    def _expand_command(self, stage: StageSpec, artifact_path: Path, run_dir: Path) -> tuple[list[str], list[str]]:
        replacements = {
            "{python}": self.python_executable,
            "{project_root}": str(self.project_root),
            "{run_dir}": str(run_dir),
            "{artifact}": str(artifact_path),
        }
        secrets: list[str] = []
        expanded: list[str] = []
        for template in stage.source.argv:
            value = template
            for token, replacement in replacements.items():
                value = value.replace(token, replacement)
            for name in _ENV_REFERENCE.findall(value):
                secret = os.getenv(name, "")
                if not secret:
                    raise HarnessRuntimeError(f"missing environment variable referenced by command: {name}")
                secrets.append(secret)
                value = value.replace(f"${{{name}}}", secret)
            expanded.append(value)
        return expanded, secrets

    def _execute_stage(self, stage: StageSpec, run_dir: Path) -> dict[str, Any]:
        started = time.perf_counter()
        artifact_path = run_dir / "artifacts" / f"{stage.id}.json"
        log_path = run_dir / "logs" / f"{stage.id}.log"
        command_exit_code: int | None = None
        if stage.source.kind == "artifact":
            source_path = self._project_path(stage.source.path or "")
            if not source_path.is_file():
                raise HarnessRuntimeError(f"replay artifact does not exist: {stage.source.path}")
            shutil.copy2(source_path, artifact_path)
            log_path.write_text(
                f"source_kind=artifact\nsource={stage.source.path}\n",
                encoding="utf-8",
            )
        else:
            command, secrets = self._expand_command(stage, artifact_path, run_dir)
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=stage.source.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                stdout = self._redact(str(exc.stdout or ""), secrets)
                stderr = self._redact(str(exc.stderr or ""), secrets)
                log_path.write_text(
                    f"command_template={json.dumps(stage.source.argv, ensure_ascii=False)}\n"
                    f"timeout_seconds={stage.source.timeout_seconds}\nstdout:\n{stdout}\nstderr:\n{stderr}\n",
                    encoding="utf-8",
                )
                raise HarnessRuntimeError(
                    f"stage {stage.id} timed out after {stage.source.timeout_seconds:g}s"
                ) from None
            command_exit_code = completed.returncode
            stdout = self._redact(completed.stdout, secrets)
            stderr = self._redact(completed.stderr, secrets)
            log_path.write_text(
                f"command_template={json.dumps(stage.source.argv, ensure_ascii=False)}\n"
                f"exit_code={completed.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}\n",
                encoding="utf-8",
            )
            if completed.returncode not in stage.source.allowed_exit_codes:
                raise HarnessRuntimeError(
                    f"stage {stage.id} exited with {completed.returncode}; allowed codes are "
                    f"{list(stage.source.allowed_exit_codes)}"
                )
            if not artifact_path.is_file():
                raise HarnessRuntimeError(f"stage {stage.id} produced no JSON artifact")

        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HarnessRuntimeError(f"stage {stage.id} artifact is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise HarnessRuntimeError(f"stage {stage.id} artifact root must be an object")

        metrics: list[dict[str, Any]] = []
        values: dict[str, Any] = {}
        specs: dict[str, MetricSpec] = {}
        for metric in stage.metrics:
            value = _lookup(payload, metric.path)
            values[metric.id] = value
            specs[metric.id] = metric
            metrics.append(
                {
                    "id": metric.id,
                    "label": metric.label,
                    "path": metric.path,
                    "value": value,
                    "unit": metric.unit,
                    "direction": metric.direction,
                }
            )
        gates: list[dict[str, Any]] = []
        for gate in stage.gates:
            metric = specs[gate.metric]
            actual = values[gate.metric]
            gates.append(
                {
                    "id": gate.id,
                    "metric": gate.metric,
                    "actual": actual,
                    "operator": gate.operator,
                    "expected": gate.value,
                    "unit": metric.unit,
                    "passed": _evaluate_gate(actual, gate),
                }
            )
        status = "PASS" if all(gate["passed"] for gate in gates) else "FAIL"
        return {
            "id": stage.id,
            "label": stage.label,
            "source_kind": stage.source.kind,
            "status": status,
            "duration_seconds": round(time.perf_counter() - started, 6),
            "artifact": f"artifacts/{stage.id}.json",
            "log": f"logs/{stage.id}.log",
            "command_exit_code": command_exit_code,
            "metrics": metrics,
            "gates": gates,
        }

    def run(
        self,
        config: HarnessConfig,
        *,
        run_id: str | None = None,
        stage_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        selected = set(stage_ids or [])
        if selected:
            unknown = selected - {stage.id for stage in config.stages}
            if unknown:
                raise HarnessRuntimeError(f"unknown selected stages: {sorted(unknown)}")
        stages = [stage for stage in config.stages if not selected or stage.id in selected]
        identifier = run_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{config.id}"
        if not _RUN_ID.fullmatch(identifier):
            raise HarnessRuntimeError(f"invalid run id: {identifier!r}")
        run_dir = self.runs_root / identifier
        if run_dir.exists():
            raise FileExistsError(f"run directory already exists: {run_dir}")
        (run_dir / "artifacts").mkdir(parents=True)
        (run_dir / "logs").mkdir()
        (run_dir / "config.json").write_text(
            json.dumps(config.raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        started_at = _utc_now()
        started = time.perf_counter()
        preflight = self._preflight(config)
        stage_results: list[dict[str, Any]] = []
        if preflight["status"] == "PASS":
            for stage in stages:
                try:
                    stage_results.append(self._execute_stage(stage, run_dir))
                except Exception as exc:
                    log_path = run_dir / "logs" / f"{stage.id}.log"
                    if not log_path.exists():
                        log_path.write_text(f"error={type(exc).__name__}: {exc}\n", encoding="utf-8")
                    stage_results.append(
                        {
                            "id": stage.id,
                            "label": stage.label,
                            "source_kind": stage.source.kind,
                            "status": "ERROR",
                            "duration_seconds": 0.0,
                            "artifact": f"artifacts/{stage.id}.json" if (run_dir / "artifacts" / f"{stage.id}.json").exists() else None,
                            "log": f"logs/{stage.id}.log",
                            "command_exit_code": None,
                            "metrics": [],
                            "gates": [],
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        if preflight["status"] == "ERROR" or any(stage["status"] == "ERROR" for stage in stage_results):
            status = "ERROR"
        elif any(stage["status"] == "FAIL" for stage in stage_results):
            status = "FAIL"
        else:
            status = "PASS"
        result = {
            "schema_version": "1.0",
            "run_id": identifier,
            "config_id": config.id,
            "description": config.description,
            "status": status,
            "started_at": started_at,
            "completed_at": _utc_now(),
            "duration_seconds": round(time.perf_counter() - started, 6),
            "git_commit": self._git_commit(),
            "run_directory": f"harness/runs/{identifier}",
            "preflight": preflight,
            "stages": stage_results,
        }
        (run_dir / "run.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "report.md").write_text(render_run_report(result), encoding="utf-8")
        return result
