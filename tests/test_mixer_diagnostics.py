import json

import pytest

from tools import mixer_diagnostics


def test_build_diff_reports_meter_and_level_changes(tmp_path) -> None:
    baseline = {
        "channel_groups": {"Kick": "drums"},
        "channel_post_meters": {
            "Kick": {"peak_db": -6.0, "rms_db": -9.0},
        },
        "subgroup_meters": {
            "drums": {"peak_db": -3.0, "rms_db": -6.0},
        },
        "return_levels": {"plate": -12.0},
        "master_meter": {"peak_db": -3.0, "rms_db": -6.0},
        "automation_events": [],
    }
    current = {
        "channel_groups": {"Kick": "band"},
        "channel_post_meters": {
            "Kick": {"peak_db": -3.0, "rms_db": -6.0},
        },
        "subgroup_meters": {
            "drums": {"peak_db": -1.5, "rms_db": -4.5},
        },
        "return_levels": {"plate": -6.0},
        "master_meter": {"peak_db": -1.0, "rms_db": -4.0},
        "automation_events": [],
    }

    diff = mixer_diagnostics._build_diff(baseline, current)
    assert diff["channel_groups"] == {"Kick": "drums → band"}
    assert pytest.approx(diff["channel_post_meters"]["Kick"]["peak_delta_db"], abs=1e-6) == 3.0
    assert pytest.approx(diff["channel_post_meters"]["Kick"]["rms_delta_db"], abs=1e-6) == 3.0
    assert pytest.approx(diff["subgroup_meters"]["drums"]["peak_delta_db"], abs=1e-6) == 1.5
    assert pytest.approx(diff["return_levels"]["plate"]["delta_db"], abs=1e-6) == 6.0
    assert pytest.approx(diff["master_meter"]["peak_delta_db"], abs=1e-6) == 2.0

    # Smoke-test CLI wiring with comparison file.
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline))
    args = mixer_diagnostics.parse_args(
        ["--compare", str(baseline_path), "--json", "--duration", "0.1"]
    )
    assert args.compare == baseline_path
