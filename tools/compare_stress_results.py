"""Compare stress harness exports against a committed baseline."""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCENARIO_KEY = "scenario"
INT_FIELDS: tuple[str, ...] = (
    "sample_rate",
    "block_size",
    "channels",
    "processed_blocks",
    "underruns",
    "callbacks",
)
FLOAT_FIELDS: tuple[str, ...] = (
    "duration_seconds",
    "processing_overhead_seconds",
    "avg_callback_ms",
    "p95_callback_ms",
    "avg_cpu_load",
    "max_cpu_load",
)
OPTIONAL_FLOAT_FIELDS: tuple[str, ...] = ("test_tone_hz",)


@dataclass
class MetricIssue:
    scenario: str
    metric: str | None
    baseline: Any
    candidate: Any
    message: str


def _normalize_optional_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    return float(value)


def _normalize_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {SCENARIO_KEY: str(raw[SCENARIO_KEY])}
    for field in INT_FIELDS:
        record[field] = int(float(raw[field]))
    for field in FLOAT_FIELDS:
        record[field] = float(raw[field])
    for field in OPTIONAL_FLOAT_FIELDS:
        record[field] = _normalize_optional_float(raw.get(field))
    return record


def load_results_json(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):  # pragma: no cover - defensive guard
        raise ValueError("Stress harness export must be a list of scenario objects")
    results: dict[str, dict[str, Any]] = {}
    for entry in payload:
        if not isinstance(entry, Mapping):  # pragma: no cover - defensive guard
            raise ValueError("Stress harness entries must be objects")
        record = _normalize_record(entry)
        results[record[SCENARIO_KEY]] = record
    return results


def load_results_csv(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        records = [_normalize_record(row) for row in reader]
    return {record[SCENARIO_KEY]: record for record in records}


def compare_results(
    baseline: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Mapping[str, Any]],
    *,
    abs_tol: float = 1e-4,
    rel_tol: float = 5e-3,
) -> list[MetricIssue]:
    issues: list[MetricIssue] = []
    for scenario, baseline_record in baseline.items():
        candidate_record = candidate.get(scenario)
        if candidate_record is None:
            issues.append(
                MetricIssue(
                    scenario=scenario,
                    metric=None,
                    baseline=None,
                    candidate=None,
                    message="Scenario missing from candidate results",
                )
            )
            continue
        for field in INT_FIELDS:
            baseline_value = int(baseline_record[field])
            candidate_value = int(candidate_record[field])
            if baseline_value != candidate_value:
                issues.append(
                    MetricIssue(
                        scenario=scenario,
                        metric=field,
                        baseline=baseline_value,
                        candidate=candidate_value,
                        message="Integer metric deviated",
                    )
                )
        for field in FLOAT_FIELDS:
            baseline_value = float(baseline_record[field])
            candidate_value = float(candidate_record[field])
            if not math.isclose(baseline_value, candidate_value, rel_tol=rel_tol, abs_tol=abs_tol):
                issues.append(
                    MetricIssue(
                        scenario=scenario,
                        metric=field,
                        baseline=baseline_value,
                        candidate=candidate_value,
                        message="Float metric deviated beyond tolerance",
                    )
                )
        for field in OPTIONAL_FLOAT_FIELDS:
            baseline_value = baseline_record.get(field)
            candidate_value = candidate_record.get(field)
            if baseline_value is None and candidate_value is None:
                continue
            if baseline_value is None or candidate_value is None:
                issues.append(
                    MetricIssue(
                        scenario=scenario,
                        metric=field,
                        baseline=baseline_value,
                        candidate=candidate_value,
                        message="Optional float metric mismatch",
                    )
                )
            elif not math.isclose(float(baseline_value), float(candidate_value), rel_tol=rel_tol, abs_tol=abs_tol):
                issues.append(
                    MetricIssue(
                        scenario=scenario,
                        metric=field,
                        baseline=float(baseline_value),
                        candidate=float(candidate_value),
                        message="Optional float metric deviated",
                    )
                )
    for scenario in candidate.keys() - baseline.keys():
        issues.append(
            MetricIssue(
                scenario=scenario,
                metric=None,
                baseline=None,
                candidate=None,
                message="Unexpected scenario present in candidate results",
            )
        )
    return issues


def build_summary(
    issues: Sequence[MetricIssue],
    baseline: Mapping[str, Mapping[str, Any]],
) -> str:
    lines = ["# Stress Harness Trend Check", ""]
    lines.append(f"Compared {len(baseline)} baseline scenarios against candidate results.")
    lines.append("")
    if not issues:
        for scenario in sorted(baseline):
            lines.append(f"- ✅ {scenario} metrics matched the baseline within tolerance.")
        return "\n".join(lines) + "\n"

    lines.append("Detected regressions:")
    grouped: dict[str, list[MetricIssue]] = {}
    for issue in issues:
        grouped.setdefault(issue.scenario, []).append(issue)
    for scenario in sorted(grouped):
        scenario_issues = grouped[scenario]
        lines.append(f"- ❌ {scenario}")
        for issue in scenario_issues:
            if issue.metric is None:
                lines.append(f"  - {issue.message}")
            else:
                lines.append(
                    "  - {} (baseline={}, candidate={})".format(
                        f"{issue.metric}: {issue.message}", issue.baseline, issue.candidate
                    )
                )
    return "\n".join(lines) + "\n"


def _append_history_json(path: Path, payload: Mapping[str, Any]) -> None:
    records: list[Mapping[str, Any]] = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(existing, list):
            records = list(existing)
    records.append(dict(payload))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")


def _append_history_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [] if not existing else [existing.rstrip(), ""]
    timestamp = payload.get("timestamp", "unknown")
    status = payload.get("status", "unknown")
    heading = f"## {timestamp} – {status.capitalize()}"
    lines.append(heading)
    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.append("")
        lines.append(summary.strip())
    issues = payload.get("issues")
    if isinstance(issues, Sequence) and issues:
        lines.append("")
        lines.append("### Issues")
        for issue in issues:
            scenario = issue.get("scenario") if isinstance(issue, Mapping) else None
            metric = issue.get("metric") if isinstance(issue, Mapping) else None
            message = issue.get("message") if isinstance(issue, Mapping) else None
            details = ", ".join(
                str(part)
                for part in (scenario, metric, message)
                if part not in (None, "")
            )
            if details:
                lines.append(f"- {details}")
    lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def validate_csv_consistency(
    candidate_json: Mapping[str, Mapping[str, Any]],
    csv_results: Mapping[str, Mapping[str, Any]],
) -> list[MetricIssue]:
    issues: list[MetricIssue] = []
    for scenario, json_record in candidate_json.items():
        csv_record = csv_results.get(scenario)
        if csv_record is None:
            issues.append(
                MetricIssue(
                    scenario=scenario,
                    metric=None,
                    baseline=None,
                    candidate=None,
                    message="Scenario missing from CSV export",
                )
            )
            continue
        for field in INT_FIELDS + FLOAT_FIELDS:
            if json_record[field] != csv_record[field]:
                issues.append(
                    MetricIssue(
                        scenario=scenario,
                        metric=field,
                        baseline=json_record[field],
                        candidate=csv_record[field],
                        message="CSV export diverged from JSON export",
                    )
                )
        json_optional = json_record.get("test_tone_hz")
        csv_optional = csv_record.get("test_tone_hz")
        if json_optional != csv_optional:
            issues.append(
                MetricIssue(
                    scenario=scenario,
                    metric="test_tone_hz",
                    baseline=json_optional,
                    candidate=csv_optional,
                    message="CSV export diverged from JSON export",
                )
            )
    for scenario in csv_results.keys() - candidate_json.keys():
        issues.append(
            MetricIssue(
                scenario=scenario,
                metric=None,
                baseline=None,
                candidate=None,
                message="Unexpected scenario present in CSV export",
            )
        )
    return issues


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare stress harness exports against the committed baseline",
    )
    parser.add_argument("--baseline-json", type=Path, required=True)
    parser.add_argument("--candidate-json", type=Path, required=True)
    parser.add_argument("--baseline-csv", type=Path, required=True)
    parser.add_argument("--candidate-csv", type=Path, required=True)
    parser.add_argument("--summary-path", type=Path)
    parser.add_argument("--history-json", type=Path, help="Append run metadata to a JSON history log")
    parser.add_argument(
        "--history-markdown",
        type=Path,
        help="Append run metadata and summary to a Markdown changelog",
    )
    parser.add_argument("--abs-tol", type=float, default=1e-4)
    parser.add_argument("--rel-tol", type=float, default=5e-3)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    baseline_json = load_results_json(args.baseline_json)
    candidate_json = load_results_json(args.candidate_json)
    baseline_csv = load_results_csv(args.baseline_csv)
    candidate_csv = load_results_csv(args.candidate_csv)

    issues = compare_results(baseline_json, candidate_json, abs_tol=args.abs_tol, rel_tol=args.rel_tol)
    issues.extend(compare_results(baseline_csv, candidate_csv, abs_tol=0.0, rel_tol=0.0))
    issues.extend(validate_csv_consistency(candidate_json, candidate_csv))

    summary = build_summary(issues, baseline_json)
    if args.summary_path is not None:
        args.summary_path.write_text(summary, encoding="utf-8")
    print(summary)

    status = "success" if not issues else "regression"
    history_payload = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "status": status,
        "issues": [issue.__dict__ for issue in issues],
        "summary": summary,
        "baseline_json": str(args.baseline_json),
        "candidate_json": str(args.candidate_json),
        "baseline_csv": str(args.baseline_csv),
        "candidate_csv": str(args.candidate_csv),
        "abs_tol": args.abs_tol,
        "rel_tol": args.rel_tol,
    }

    if args.history_json is not None:
        _append_history_json(args.history_json, history_payload)
    if args.history_markdown is not None:
        _append_history_markdown(args.history_markdown, history_payload)

    return 1 if issues else 0


if __name__ == "__main__":  # pragma: no cover - manual execution utility
    raise SystemExit(main())
