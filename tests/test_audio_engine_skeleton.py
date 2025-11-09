import csv
import json
import math
from pathlib import Path

import pytest

from prototypes.audio_engine_skeleton import (
    AudioEngine,
    AudioSettings,
    StressTestScenario,
    load_stress_plan,
    render_musician_demo_patch,
    render_pattern_bridge_demo,
    run_stress_test_scenarios,
)

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore


pytestmark = pytest.mark.skipif(np is None, reason="NumPy is required for audio engine tests")


def test_offline_render_shape_and_dtype():
    engine = AudioEngine(AudioSettings(block_size=64, channels=2, test_tone_hz=440.0))
    buffer = engine.render_offline(0.01)
    assert buffer.shape[1] == 2
    assert buffer.dtype == np.float32
    # Expect approximately sample_rate * duration frames accounting for rounding
    expected_frames = int(math.ceil(engine.settings.sample_rate * 0.01))
    assert buffer.shape[0] >= expected_frames - engine.settings.block_size


def _load_golden_render(name: str) -> dict:
    fixture_path = Path(__file__).parent / "fixtures" / name
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if np is None:  # pragma: no cover - guard for type checkers
        raise RuntimeError("NumPy must be available for golden render verification")
    payload["samples"] = np.asarray(payload["samples"], dtype=np.float32)
    return payload


def test_offline_render_matches_golden_fixture():
    golden = _load_golden_render("golden_render_440hz_sr48000_bs64_ch1.json")
    duration = golden["block_size"] / golden["sample_rate"]
    engine = AudioEngine(
        AudioSettings(
            sample_rate=golden["sample_rate"],
            block_size=golden["block_size"],
            channels=golden["channels"],
            test_tone_hz=golden["frequency"],
        )
    )
    buffer = engine.render_offline(duration)
    assert buffer.shape == (golden["block_size"], golden["channels"])
    np.testing.assert_allclose(buffer[:, 0], golden["samples"], atol=1e-6)


def test_parameter_automation_updates_graph():
    engine = AudioEngine(AudioSettings(block_size=32, test_tone_hz=220.0))
    engine.schedule_parameter_automation("test_tone_hz", 880.0, time_seconds=0.0)
    engine.render_offline(0.005)
    assert math.isclose(engine.graph.get_parameter("test_tone_hz") or 0.0, 880.0, rel_tol=1e-5)
    assert engine.metrics.engine_time > 0.0


def test_parameter_automation_respects_future_timestamps():
    engine = AudioEngine(AudioSettings(block_size=64, test_tone_hz=110.0))
    engine.schedule_parameter_automation("test_tone_hz", 660.0, time_seconds=0.01)

    # First render shorter than automation timestamp; parameter should remain unchanged.
    engine.render_offline(0.002)
    assert math.isclose(engine.graph.get_parameter("test_tone_hz") or 0.0, 110.0, rel_tol=1e-6)

    # Continue rendering beyond timestamp and confirm the update is applied.
    engine.render_offline(0.02)
    assert math.isclose(engine.graph.get_parameter("test_tone_hz") or 0.0, 660.0, rel_tol=1e-6)


def test_stress_test_reports_underruns():
    engine = AudioEngine(AudioSettings(block_size=32, test_tone_hz=330.0))
    metrics = engine.run_stress_test(0.01, processing_overhead=0.002)
    assert metrics.underruns > 0
    assert metrics.max_callback_duration >= metrics.last_callback_duration
    assert metrics.average_cpu_load > 1.0
    assert metrics.max_cpu_load >= metrics.average_cpu_load


def test_metrics_snapshot_contains_latency_and_cpu_insights():
    engine = AudioEngine(AudioSettings(block_size=64, test_tone_hz=220.0))
    metrics = engine.run_stress_test(0.02, processing_overhead=0.0003)
    snapshot = metrics.snapshot()
    assert snapshot["callbacks"] == pytest.approx(metrics.callbacks)
    assert snapshot["avg_callback_ms"] > 0.0
    assert snapshot["p95_callback_ms"] >= snapshot["avg_callback_ms"] or math.isclose(
        snapshot["p95_callback_ms"],
        snapshot["avg_callback_ms"],
        rel_tol=0.15,
        abs_tol=0.05,
    )
    assert 0.0 < snapshot["avg_cpu_load"] <= snapshot["max_cpu_load"]


def _rms(values: "np.ndarray") -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def test_multi_stage_automation_creates_distinct_signal_segments():
    engine = AudioEngine(
        AudioSettings(block_size=32, channels=1, test_tone_hz=None)
    )
    engine.schedule_parameter_automation("test_tone_hz", 110.0, time_seconds=0.0)
    engine.schedule_parameter_automation("test_tone_hz", None, time_seconds=0.015)
    engine.schedule_parameter_automation("test_tone_hz", 440.0, time_seconds=0.03)

    duration = 0.05
    buffer = engine.render_offline(duration)
    flat = buffer[:, 0]

    sr = engine.settings.sample_rate
    idx_mid = int(0.015 * sr)
    idx_final = int(0.03 * sr)

    active_segment = flat[: idx_mid - 10]
    silent_segment = flat[idx_mid: idx_final - 10]
    final_segment = flat[idx_final:]

    assert _rms(active_segment) > 0.3
    assert _rms(silent_segment) < 1e-3
    assert _rms(final_segment) > 0.3
    assert math.isclose(engine.graph.get_parameter("test_tone_hz") or 0.0, 440.0, rel_tol=1e-6)


def test_musician_engine_bridge_uses_beats_for_automation():
    settings = AudioSettings(block_size=64, channels=1, test_tone_hz=220.0, tempo_bpm=60.0)
    engine = AudioEngine(settings)

    buffer = engine.render_with_musician_engine(
        4.0,
        beat_automation=[(0.0, 220.0), (2.0, None), (3.0, 660.0)],
    )

    assert buffer.shape == (settings.sample_rate * 4, 1)

    first_section = buffer[: settings.sample_rate]
    silent_section = buffer[settings.sample_rate * 2 : settings.sample_rate * 3]
    final_section = buffer[settings.sample_rate * 3 :]

    assert _rms(first_section[:, 0]) > 0.2
    assert _rms(silent_section[:, 0]) < 1e-3
    assert _rms(final_section[:, 0]) > 0.2
    assert engine.metrics.engine_time >= 4.0


def test_stress_scenario_runner_exports_csv_and_json(tmp_path):
    scenarios = [
        StressTestScenario(
            name="Baseline",
            duration_seconds=0.02,
            processing_overhead=0.0,
            settings=AudioSettings(block_size=64, test_tone_hz=220.0),
        ),
        StressTestScenario(
            name="Loaded",
            duration_seconds=0.02,
            processing_overhead=0.0004,
            settings=AudioSettings(block_size=32, test_tone_hz=440.0),
        ),
    ]

    csv_path = tmp_path / "metrics.csv"
    json_path = tmp_path / "metrics.json"
    results = run_stress_test_scenarios(scenarios, csv_path=csv_path, json_path=json_path)

    assert csv_path.exists()
    assert json_path.exists()
    assert len(results) == len(scenarios)
    assert isinstance(results[0]["callbacks"], int)

    with csv_path.open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert [row["scenario"] for row in csv_rows] == [scenario.name for scenario in scenarios]

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload[0]["scenario"] == "Baseline"
    assert payload[0]["callbacks"] == results[0]["callbacks"]


def test_pattern_bridge_demo_summary_includes_smoothing_totals():
    settings = AudioSettings(sample_rate=48_000, block_size=256, channels=2, tempo_bpm=120.0)
    summary = render_pattern_bridge_demo(settings)

    smoothing_rows = summary["automation_smoothing"]
    assert smoothing_rows, "Expected smoothing rows to be present"
    first_row = smoothing_rows[0]
    assert first_row["segment_total"] >= 1
    assert isinstance(first_row.get("segment_breakdown"), dict)

    smoothing_summary = summary["automation_smoothing_summary"]
    assert smoothing_summary["rows"] == len(smoothing_rows)
    assert smoothing_summary["segment_total"] >= first_row["segment_total"]


def test_load_stress_plan_parses_settings(tmp_path):
    plan = [
        {
            "name": "PlanA",
            "duration_seconds": 0.05,
            "processing_overhead_seconds": 0.0005,
            "settings": {
                "sample_rate": 44_100,
                "block_size": 128,
                "channels": 2,
                "test_tone_hz": 330.0,
            },
        }
    ]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    scenarios = load_stress_plan(path)
    assert len(scenarios) == 1
    scenario = scenarios[0]
    assert isinstance(scenario, StressTestScenario)
    assert scenario.settings.sample_rate == 44_100
    assert scenario.settings.block_size == 128
    assert scenario.settings.channels == 2
    assert scenario.settings.test_tone_hz == 330.0
    assert scenario.processing_overhead == pytest.approx(0.0005)


def test_musician_demo_patch_reports_loudness():
    settings = AudioSettings(block_size=64, channels=2, test_tone_hz=440.0, tempo_bpm=120.0)
    metrics = render_musician_demo_patch(settings, 2.0)
    assert metrics["duration_seconds"] == pytest.approx(2.0)
    assert metrics["rms_left_dbfs"] < -1.0
    assert metrics["integrated_lufs"] < -3.0
