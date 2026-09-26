"""Render run reports and compare normalized Harness metrics."""

from __future__ import annotations

from typing import Any


def _format_value(value: Any, unit: str = "number") -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if unit == "ratio":
            return f"{float(value):.2%}"
        if unit == "seconds":
            return f"{float(value):.3f}s"
        return f"{float(value):.4f}" if isinstance(value, float) else str(value)
    return str(value)


def render_run_report(run: dict[str, Any]) -> str:
    lines = [
        "# ScholarLens Evaluation Harness",
        "",
        f"- Run: `{run['run_id']}`",
        f"- Configuration: `{run['config_id']}`",
        f"- Status: **{run['status']}**",
        f"- Git commit: `{run.get('git_commit') or 'unavailable'}`",
        f"- Started: {run['started_at']}",
        f"- Duration: {run['duration_seconds']:.3f}s",
        "",
        "## Stage summary",
        "",
        "| Stage | Status | Duration | Artifact |",
        "| --- | --- | ---: | --- |",
    ]
    for stage in run.get("stages", []):
        lines.append(
            f"| {stage['label']} | **{stage['status']}** | "
            f"{stage['duration_seconds']:.3f}s | `{stage.get('artifact') or '-'}` |"
        )
    if not run.get("stages"):
        lines.append("| No stage executed | **ERROR** | 0.000s | - |")

    for stage in run.get("stages", []):
        lines.extend(["", f"## {stage['label']}", ""])
        if stage.get("error"):
            lines.extend([f"Error: `{stage['error']}`", ""])
        lines.extend(["### Metrics", "", "| Metric | Value | Direction |", "| --- | ---: | --- |"])
        for metric in stage.get("metrics", []):
            lines.append(
                f"| {metric['label']} | {_format_value(metric['value'], metric['unit'])} | "
                f"{metric['direction']} |"
            )
        if not stage.get("metrics"):
            lines.append("| No metrics | - | - |")
        lines.extend(["", "### Gates", "", "| Gate | Actual | Rule | Result |", "| --- | ---: | --- | --- |"])
        for gate in stage.get("gates", []):
            unit = gate.get("unit", "number")
            lines.append(
                f"| {gate['id']} | {_format_value(gate['actual'], unit)} | "
                f"`{gate['operator']} {_format_value(gate['expected'], unit)}` | "
                f"**{'PASS' if gate['passed'] else 'FAIL'}** |"
            )
        if not stage.get("gates"):
            lines.append("| No quality gate | - | - | PASS |")

    preflight = run.get("preflight", {})
    lines.extend(["", "## Preflight", ""])
    for check in preflight.get("checks", []):
        lines.append(f"- **{check['status']}** `{check['id']}` — {check['message']}")
    if not preflight.get("checks"):
        lines.append("- No external preflight requirements.")
    lines.append("")
    return "\n".join(lines)


def _metric_index(run: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for stage in run.get("stages", []):
        for metric in stage.get("metrics", []):
            index[(str(stage["id"]), str(metric["id"]))] = {
                **metric,
                "stage_label": stage.get("label", stage["id"]),
            }
    return index


def compare_runs(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    baseline_metrics = _metric_index(baseline)
    candidate_metrics = _metric_index(candidate)
    rows: list[dict[str, Any]] = []
    counts = {"improved": 0, "regressed": 0, "unchanged": 0}
    for key in sorted(set(baseline_metrics) & set(candidate_metrics)):
        before = baseline_metrics[key]
        after = candidate_metrics[key]
        before_value = before.get("value")
        after_value = after.get("value")
        delta: float | None = None
        verdict = "unchanged"
        if (
            isinstance(before_value, (int, float))
            and not isinstance(before_value, bool)
            and isinstance(after_value, (int, float))
            and not isinstance(after_value, bool)
        ):
            delta = float(after_value) - float(before_value)
            direction = str(after.get("direction", before.get("direction", "neutral")))
            if abs(delta) > 1e-12:
                if direction == "higher":
                    verdict = "improved" if delta > 0 else "regressed"
                elif direction == "lower":
                    verdict = "improved" if delta < 0 else "regressed"
                else:
                    verdict = "unchanged"
        elif before_value != after_value:
            verdict = "regressed"
        counts[verdict] += 1
        rows.append(
            {
                "stage_id": key[0],
                "stage_label": after.get("stage_label", key[0]),
                "metric_id": key[1],
                "metric_label": after.get("label", key[1].replace("_", " ").title()),
                "unit": after.get("unit", before.get("unit", "number")),
                "direction": after.get("direction", before.get("direction", "neutral")),
                "baseline": before_value,
                "candidate": after_value,
                "delta": delta,
                "verdict": verdict,
            }
        )
    return {
        "schema_version": "1.0",
        "baseline_run_id": baseline.get("run_id"),
        "candidate_run_id": candidate.get("run_id"),
        "summary": {**counts, "common_metrics": len(rows)},
        "metrics": rows,
    }


def render_comparison(comparison: dict[str, Any]) -> str:
    summary = comparison["summary"]
    lines = [
        "# ScholarLens Harness Comparison",
        "",
        f"- Baseline: `{comparison.get('baseline_run_id')}`",
        f"- Candidate: `{comparison.get('candidate_run_id')}`",
        f"- Improved: {summary['improved']}",
        f"- Regressed: {summary['regressed']}",
        f"- Unchanged: {summary['unchanged']}",
        "",
        "| Stage | Metric | Baseline | Candidate | Delta | Verdict |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for metric in comparison.get("metrics", []):
        unit = metric.get("unit", "number")
        delta = metric.get("delta")
        delta_text = "-" if delta is None else f"{delta:+.4f}"
        lines.append(
            f"| {metric['stage_label']} | {metric['metric_label']} | "
            f"{_format_value(metric['baseline'], unit)} | "
            f"{_format_value(metric['candidate'], unit)} | {delta_text} | "
            f"**{metric['verdict'].upper()}** |"
        )
    if not comparison.get("metrics"):
        lines.append("| - | No common metrics | - | - | - | - |")
    lines.append("")
    return "\n".join(lines)

