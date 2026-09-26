"""Load and validate versioned Evaluation Harness configurations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ENV_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_OPERATORS = {">=", "<=", ">", "<", "==", "!="}
_DIRECTIONS = {"higher", "lower", "neutral"}


class ConfigError(ValueError):
    """Raised when a Harness configuration is invalid."""


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    url: str
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class PreflightSpec:
    required_env: tuple[str, ...] = ()
    services: tuple[ServiceSpec, ...] = ()


@dataclass(frozen=True)
class SourceSpec:
    kind: str
    path: str | None = None
    argv: tuple[str, ...] = ()
    allowed_exit_codes: tuple[int, ...] = (0,)
    timeout_seconds: float = 900.0


@dataclass(frozen=True)
class MetricSpec:
    id: str
    label: str
    path: str
    unit: str = "number"
    direction: str = "neutral"


@dataclass(frozen=True)
class GateSpec:
    id: str
    metric: str
    operator: str
    value: Any


@dataclass(frozen=True)
class StageSpec:
    id: str
    label: str
    source: SourceSpec
    metrics: tuple[MetricSpec, ...]
    gates: tuple[GateSpec, ...]


@dataclass(frozen=True)
class HarnessConfig:
    schema_version: str
    id: str
    description: str
    preflight: PreflightSpec
    stages: tuple[StageSpec, ...]
    raw: dict[str, Any]
    path: Path


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{context} must be an object")
    return value


def _list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(f"{context} must be an array")
    return value


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{context} must be a non-empty string")
    return value.strip()


def _identifier(value: Any, context: str) -> str:
    identifier = _text(value, context)
    if not _ID_PATTERN.fullmatch(identifier):
        raise ConfigError(f"{context} contains unsupported characters: {identifier!r}")
    return identifier


def _parse_preflight(raw: Any) -> PreflightSpec:
    if raw is None:
        return PreflightSpec()
    payload = _object(raw, "preflight")
    required_env: list[str] = []
    for index, value in enumerate(_list(payload.get("required_env", []), "preflight.required_env")):
        name = _text(value, f"preflight.required_env[{index}]")
        if not _ENV_PATTERN.fullmatch(name):
            raise ConfigError(f"invalid environment variable name: {name!r}")
        if name in required_env:
            raise ConfigError(f"duplicate required environment variable: {name}")
        required_env.append(name)

    services: list[ServiceSpec] = []
    service_names: set[str] = set()
    for index, value in enumerate(_list(payload.get("services", []), "preflight.services")):
        item = _object(value, f"preflight.services[{index}]")
        name = _identifier(item.get("name"), f"preflight.services[{index}].name")
        if name in service_names:
            raise ConfigError(f"duplicate preflight service: {name}")
        service_names.add(name)
        url = _text(item.get("url"), f"preflight.services[{index}].url")
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"preflight service URL must use HTTP(S): {url!r}")
        timeout = item.get("timeout_seconds", 5)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ConfigError(f"preflight service timeout must be positive: {name}")
        services.append(ServiceSpec(name=name, url=url, timeout_seconds=float(timeout)))
    return PreflightSpec(tuple(required_env), tuple(services))


def _parse_source(raw: Any, stage_id: str) -> SourceSpec:
    payload = _object(raw, f"stage {stage_id} source")
    kind = _text(payload.get("kind"), f"stage {stage_id} source.kind")
    if kind == "artifact":
        path = _text(payload.get("path"), f"stage {stage_id} source.path")
        return SourceSpec(kind=kind, path=path)
    if kind != "command":
        raise ConfigError(f"stage {stage_id} source kind must be artifact or command")

    argv_values = _list(payload.get("argv"), f"stage {stage_id} source.argv")
    argv = tuple(_text(value, f"stage {stage_id} source.argv") for value in argv_values)
    if not argv:
        raise ConfigError(f"stage {stage_id} command argv cannot be empty")
    if not any("{artifact}" in value for value in argv):
        raise ConfigError(f"stage {stage_id} command must write to {{artifact}}")
    exit_codes = _list(payload.get("allowed_exit_codes", [0]), f"stage {stage_id} allowed_exit_codes")
    if not exit_codes or any(not isinstance(code, int) or isinstance(code, bool) for code in exit_codes):
        raise ConfigError(f"stage {stage_id} allowed_exit_codes must contain integers")
    timeout = payload.get("timeout_seconds", 900)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ConfigError(f"stage {stage_id} timeout_seconds must be positive")
    return SourceSpec(
        kind=kind,
        argv=argv,
        allowed_exit_codes=tuple(dict.fromkeys(exit_codes)),
        timeout_seconds=float(timeout),
    )


def _parse_stage(raw: Any, index: int) -> StageSpec:
    payload = _object(raw, f"stages[{index}]")
    stage_id = _identifier(payload.get("id"), f"stages[{index}].id")
    label = _text(payload.get("label", stage_id), f"stage {stage_id} label")
    source = _parse_source(payload.get("source"), stage_id)

    metrics: list[MetricSpec] = []
    metric_ids: set[str] = set()
    for metric_index, value in enumerate(_list(payload.get("metrics"), f"stage {stage_id} metrics")):
        item = _object(value, f"stage {stage_id} metrics[{metric_index}]")
        metric_id = _identifier(item.get("id"), f"stage {stage_id} metric id")
        if metric_id in metric_ids:
            raise ConfigError(f"stage {stage_id} has duplicate metric: {metric_id}")
        metric_ids.add(metric_id)
        direction = _text(item.get("direction", "neutral"), f"metric {metric_id} direction")
        if direction not in _DIRECTIONS:
            raise ConfigError(f"metric {metric_id} direction must be higher, lower or neutral")
        metrics.append(
            MetricSpec(
                id=metric_id,
                label=_text(item.get("label", metric_id), f"metric {metric_id} label"),
                path=_text(item.get("path"), f"metric {metric_id} path"),
                unit=_text(item.get("unit", "number"), f"metric {metric_id} unit"),
                direction=direction,
            )
        )
    if not metrics:
        raise ConfigError(f"stage {stage_id} must declare at least one metric")

    gates: list[GateSpec] = []
    gate_ids: set[str] = set()
    for gate_index, value in enumerate(_list(payload.get("gates", []), f"stage {stage_id} gates")):
        item = _object(value, f"stage {stage_id} gates[{gate_index}]")
        gate_id = _identifier(item.get("id"), f"stage {stage_id} gate id")
        if gate_id in gate_ids:
            raise ConfigError(f"stage {stage_id} has duplicate gate: {gate_id}")
        gate_ids.add(gate_id)
        metric_id = _identifier(item.get("metric"), f"gate {gate_id} metric")
        if metric_id not in metric_ids:
            raise ConfigError(f"gate {gate_id} references unknown metric: {metric_id}")
        operator = _text(item.get("operator"), f"gate {gate_id} operator")
        if operator not in _OPERATORS:
            raise ConfigError(f"gate {gate_id} uses unsupported operator: {operator}")
        if "value" not in item or isinstance(item["value"], (dict, list)):
            raise ConfigError(f"gate {gate_id} value must be a scalar")
        gates.append(GateSpec(gate_id, metric_id, operator, item["value"]))
    return StageSpec(stage_id, label, source, tuple(metrics), tuple(gates))


def load_config(path: str | Path) -> HarnessConfig:
    config_path = Path(path).resolve()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read Harness config {config_path}: {exc}") from exc
    payload = _object(raw, "config")
    schema_version = _text(payload.get("schema_version"), "schema_version")
    if schema_version != "1.0":
        raise ConfigError(f"unsupported schema_version: {schema_version}")
    config_id = _identifier(payload.get("id"), "id")
    description = _text(payload.get("description", config_id), "description")
    stages = tuple(
        _parse_stage(value, index)
        for index, value in enumerate(_list(payload.get("stages"), "stages"))
    )
    if not stages:
        raise ConfigError("config must declare at least one stage")
    stage_ids = [stage.id for stage in stages]
    duplicate = next((item for item in stage_ids if stage_ids.count(item) > 1), None)
    if duplicate:
        raise ConfigError(f"duplicate stage: {duplicate}")
    return HarnessConfig(
        schema_version=schema_version,
        id=config_id,
        description=description,
        preflight=_parse_preflight(payload.get("preflight")),
        stages=stages,
        raw=payload,
        path=config_path,
    )

