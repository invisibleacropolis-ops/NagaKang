from pathlib import Path

import pytest

from tools.compare_stress_results import (
    MetricIssue,
    build_summary,
    compare_results,
    load_results_csv,
    load_results_json,
    validate_csv_consistency,
)


@pytest.fixture()
def baseline_paths(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[1]
    baseline_dir = repo_root / "docs" / "qa" / "artifacts" / "baseline"
    return baseline_dir / "stress_results.json", baseline_dir / "stress_results.csv"


def test_compare_results_matches_baseline(tmp_path: Path, baseline_paths: tuple[Path, Path]) -> None:
    baseline_json_path, baseline_csv_path = baseline_paths
    baseline_json = load_results_json(baseline_json_path)
    candidate_json = load_results_json(baseline_json_path)
    issues = compare_results(baseline_json, candidate_json)
    assert issues == []

    baseline_csv = load_results_csv(baseline_csv_path)
    candidate_csv = load_results_csv(baseline_csv_path)
    csv_issues = validate_csv_consistency(candidate_json, candidate_csv)
    assert csv_issues == []

    summary = build_summary([], baseline_json)
    assert "Stress Harness Trend Check" in summary
    for scenario in baseline_json:
        assert scenario in summary


def test_compare_results_detects_deviation(tmp_path: Path, baseline_paths: tuple[Path, Path]) -> None:
    baseline_json_path, _ = baseline_paths
    baseline_json = load_results_json(baseline_json_path)
    candidate_json = load_results_json(baseline_json_path)
    candidate_json["Baseline"]["avg_cpu_load"] += 0.1

    issues = compare_results(baseline_json, candidate_json, abs_tol=1e-6, rel_tol=1e-6)
    assert issues
    issue = issues[0]
    assert isinstance(issue, MetricIssue)
    assert issue.scenario == "Baseline"
    assert issue.metric == "avg_cpu_load"


def test_validate_csv_consistency_flags_missing(tmp_path: Path, baseline_paths: tuple[Path, Path]) -> None:
    baseline_json_path, _ = baseline_paths
    candidate_json = load_results_json(baseline_json_path)
    candidate_csv = {"Baseline": candidate_json["Baseline"]}

    issues = validate_csv_consistency(candidate_json, candidate_csv)
    assert any(issue.message.startswith("Scenario missing") for issue in issues)
