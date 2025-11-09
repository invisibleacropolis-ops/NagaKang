import math

import pytest

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore

from audio.engine import EngineConfig, OfflineAudioEngine, TempoMap
from audio.tracker_bridge import PatternPerformanceBridge
from domain.models import AutomationPoint, InstrumentDefinition, InstrumentModule, Pattern, PatternStep


pytestmark = pytest.mark.skipif(np is None, reason="NumPy is required for tracker bridge tests")


def _make_sample(duration_seconds: float, sample_rate: int) -> np.ndarray:
    frames = int(duration_seconds * sample_rate)
    time = np.linspace(0.0, duration_seconds, frames, endpoint=False, dtype=np.float32)
    tone = np.sin(2.0 * np.pi * 110.0 * time, dtype=np.float32)
    return np.stack([tone, tone], axis=1)


def test_pattern_bridge_renders_sampler_chain_and_logs_automation():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=128, channels=2)
    tempo = TempoMap(tempo_bpm=120.0)
    library = {"vox": _make_sample(1.0, sample_rate)}

    instrument = InstrumentDefinition(
        id="vox",
        name="Vocal Clip",
        modules=[
            InstrumentModule(
                id="sampler",
                type="clip_sampler:vox",
                parameters={
                    "start_percent": 0.1,
                    "length_percent": 0.4,
                    "amplitude": 0.8,
                },
            ),
            InstrumentModule(
                id="env",
                type="amplitude_envelope",
                parameters={"attack_ms": 8.0, "release_ms": 90.0},
                inputs=["sampler"],
            ),
            InstrumentModule(
                id="filter",
                type="one_pole_low_pass",
                parameters={"cutoff_hz": 2_500.0},
                inputs=["env"],
            ),
        ],
    )

    pattern = Pattern(
        id="phrase",
        name="Phrase",
        length_steps=16,
        steps=[
            PatternStep(note=60, velocity=100, instrument_id="vox"),
            *[PatternStep() for _ in range(7)],
            PatternStep(note=67, velocity=115, instrument_id="vox"),
            *[PatternStep() for _ in range(7)],
        ],
        automation={
            "filter.cutoff_hz|normalized": [
                AutomationPoint(position_beats=0.0, value=0.15),
                AutomationPoint(position_beats=2.0, value=0.9),
            ]
        },
    )

    bridge = PatternPerformanceBridge(config, tempo, sample_library=library)
    playback = bridge.render_pattern(pattern, instrument)

    assert playback.buffer.shape[1] == 2
    assert playback.duration_seconds == pytest.approx(tempo.beats_to_seconds(pattern.duration_beats))
    assert any(event["module"] == "sampler" for event in playback.automation_log)
    assert any(event["parameter"] == "gate" for event in playback.automation_log)
    assert any(event["parameter"] == "velocity" for event in playback.automation_log)

    filter_events = [
        event
        for event in playback.automation_log
        if event["module"] == "filter" and event["parameter"] == "cutoff_hz"
    ]
    assert len(filter_events) == 2
    assert [event["beats"] for event in filter_events] == [0.0, 2.0]
    assert filter_events[0]["lane_metadata"]["mode"] == "normalized"
    assert filter_events[0]["source_value"] == pytest.approx(0.15)
    assert filter_events[0]["value"] == pytest.approx(20.0 + (11_980.0 * 0.15))
    assert filter_events[1]["value"] == pytest.approx(20.0 + (11_980.0 * 0.9))

    sampler_velocity_events = [
        event
        for event in playback.automation_log
        if event["module"] == "sampler" and event["parameter"] == "velocity"
    ]
    assert len(sampler_velocity_events) == 2
    assert {event["beats"] for event in sampler_velocity_events} == {0.0, 2.0}
    assert {event["value"] for event in sampler_velocity_events} == {100.0, 115.0}

    frames_per_beat = int(round(sample_rate * tempo.beats_to_seconds(1.0)))
    first_note = playback.buffer[:frames_per_beat]
    middle = playback.buffer[frames_per_beat : frames_per_beat * 2]
    second_note = playback.buffer[frames_per_beat * 2 : frames_per_beat * 3]

    def _rms(block: np.ndarray) -> float:
        if block.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(block[:, 0]))))

    assert _rms(first_note) > 0.01
    assert _rms(middle) < _rms(first_note) * 0.2
    assert _rms(second_note) > _rms(first_note) * 0.4

    summaries = bridge.loudness_trends(playback, beats_per_bucket=1.0)
    assert len(summaries) >= math.ceil(pattern.duration_beats)
    assert summaries[0]["rms_left_dbfs"] <= 0.0
    assert summaries[0]["integrated_lufs"] <= summaries[0]["rms_left_dbfs"] + 6.0

    rows = bridge.tracker_loudness_rows(playback, beats_per_bucket=1.0)
    assert len(rows) == len(summaries)
    assert rows[0]["label"].startswith("Beats ")
    assert "dBFS" in rows[0]["rms_text"]
    assert rows[0]["dynamic_grade"] in {"bold", "balanced", "soft"}


@pytest.mark.parametrize(
    "family,expected",
    [
        ("strings", 12.0),
        ("pads", 12.0),
        ("keys", 8.0),
        ("plucked", 6.0),
        ("vocal", 10.0),
    ],
)
def test_sampler_crossfade_defaults_apply_per_family(family, expected):
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=128, channels=2)
    tempo = TempoMap(tempo_bpm=110.0)
    soft = _make_sample(1.0, sample_rate)
    hard = soft * 1.1
    library = {"soft": soft, "hard": hard}

    instrument = InstrumentDefinition(
        id=f"vox_{family}",
        name="Velocity Layers",
        modules=[
            InstrumentModule(
                id="sampler",
                type="clip_sampler:soft",
                parameters={
                    "instrument_family": family,
                    "layers": [
                        {"sample_name": "soft", "max_velocity": 90},
                        {"sample_name": "hard", "min_velocity": 91},
                    ],
                },
            ),
        ],
    )

    pattern = Pattern(
        id=f"pattern_{family}",
        name="Pattern",
        length_steps=4,
        steps=[
            PatternStep(note=60, velocity=64, instrument_id=instrument.id),
            PatternStep(note=67, velocity=118, instrument_id=instrument.id),
            PatternStep(),
            PatternStep(),
        ],
    )

    bridge = PatternPerformanceBridge(config, tempo, sample_library=library)
    playback = bridge.render_pattern(pattern, instrument)

    params = playback.module_parameters["sampler"]
    assert params["velocity_crossfade_width"] == pytest.approx(expected)
    if family == "vocal":
        assert params["velocity_amplitude_min"] == pytest.approx(0.48, rel=1e-3)
        assert params["velocity_amplitude_max"] == pytest.approx(1.05, rel=1e-3)


def test_sampler_crossfade_respects_manual_override():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=128, channels=2)
    tempo = TempoMap(tempo_bpm=90.0)
    library = {"soft": _make_sample(1.0, sample_rate)}

    instrument = InstrumentDefinition(
        id="vox_override",
        name="Velocity Override",
        modules=[
            InstrumentModule(
                id="sampler",
                type="clip_sampler:soft",
                parameters={
                    "instrument_family": "strings",
                    "velocity_crossfade_width": 4.5,
                    "layers": [
                        {"sample_name": "soft", "max_velocity": 100},
                    ],
                },
            ),
        ],
    )

    pattern = Pattern(
        id="pattern_override",
        name="Pattern Override",
        length_steps=4,
        steps=[PatternStep(note=60, velocity=100, instrument_id=instrument.id)],
    )

    bridge = PatternPerformanceBridge(config, tempo, sample_library=library)
    playback = bridge.render_pattern(pattern, instrument)
    params = playback.module_parameters["sampler"]
    assert params["velocity_crossfade_width"] == pytest.approx(4.5)


def test_vocal_sampler_applies_velocity_amplitude_defaults_for_stabs():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=128, channels=2)
    tempo = TempoMap(tempo_bpm=120.0)

    duration_seconds = 0.3
    frames = int(duration_seconds * sample_rate)
    base = np.ones((frames, 2), dtype=np.float32)
    library = {"vox_soft": base * 0.5, "vox_bold": base}

    instrument = InstrumentDefinition(
        id="vox_short",
        name="Gospel Stab",
        modules=[
            InstrumentModule(
                id="sampler",
                type="clip_sampler:vox_soft",
                parameters={
                    "instrument_family": "vocal",
                    "length_percent": 0.35,
                    "layers": [
                        {"sample_name": "vox_soft", "max_velocity": 80},
                        {"sample_name": "vox_bold", "min_velocity": 81},
                    ],
                },
            ),
        ],
    )

    pattern = Pattern(
        id="stab_pattern",
        name="Stab Pattern",
        length_steps=8,
        steps=[
            PatternStep(note=60, velocity=48, instrument_id=instrument.id),
            PatternStep(),
            PatternStep(note=60, velocity=118, instrument_id=instrument.id),
            *[PatternStep() for _ in range(5)],
        ],
    )

    bridge = PatternPerformanceBridge(config, tempo, sample_library=library)
    playback = bridge.render_pattern(pattern, instrument)

    params = playback.module_parameters["sampler"]
    assert params["velocity_amplitude_min"] == pytest.approx(0.48, rel=1e-3)
    assert params["velocity_amplitude_max"] == pytest.approx(1.05, rel=1e-3)

    assert np.any(playback.buffer)
    frames_per_beat = int(round(sample_rate * tempo.beats_to_seconds(1.0)))
    first_hit = playback.buffer[:frames_per_beat]
    assert float(np.max(np.abs(first_hit[:, 0]))) > 0.0

    velocity_events = [
        event
        for event in playback.automation_log
        if event.get("module") == "sampler" and event.get("parameter") == "velocity"
    ]
    assert {event["beats"] for event in velocity_events} == {0.0, 0.5}
    assert all(event.get("event_id") for event in velocity_events)


def test_automation_lane_range_and_percent_modes():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=128, channels=2)
    tempo = TempoMap(tempo_bpm=100.0)

    instrument = InstrumentDefinition(
        id="tone",
        name="Simple Tone",
        modules=[
            InstrumentModule(
                id="osc",
                type="sine",
                parameters={"amplitude": 0.25, "frequency_hz": 220.0},
            ),
        ],
    )

    pattern = Pattern(
        id="automation_only",
        name="Automation Only",
        length_steps=4,
        automation={
            "osc.amplitude|percent|range=0.2:0.8": [
                AutomationPoint(position_beats=0.0, value=50.0),
                AutomationPoint(position_beats=1.0, value=120.0),
            ]
        },
    )

    bridge = PatternPerformanceBridge(config, tempo)
    playback = bridge.render_pattern(pattern, instrument)

    amplitude_events = [
        event
        for event in playback.automation_log
        if event["module"] == "osc" and event["parameter"] == "amplitude"
    ]
    assert [event["beats"] for event in amplitude_events] == [0.0, 1.0]
    assert amplitude_events[0]["value"] == pytest.approx(0.5)
    # Value beyond 100 percent should clamp to configured range, then spec clamp at 0.8
    assert amplitude_events[1]["value"] == pytest.approx(0.8)
    assert amplitude_events[0]["lane_metadata"]["mode"] == "percent"
    assert amplitude_events[0]["lane_metadata"]["range"] == (0.2, 0.8)


def test_automation_lane_curves_shape_values():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=128, channels=2)
    tempo = TempoMap(tempo_bpm=96.0)

    instrument = InstrumentDefinition(
        id="tone",
        name="Simple Tone",
        modules=[
            InstrumentModule(
                id="osc",
                type="sine",
                parameters={"amplitude": 0.2, "frequency_hz": 440.0},
            ),
        ],
    )

    pattern = Pattern(
        id="automation_curves",
        name="Automation Curves",
        length_steps=4,
        automation={
            "osc.amplitude|normalized|curve=exponential": [
                AutomationPoint(position_beats=0.0, value=0.5),
            ],
            "osc.frequency_hz|normalized|curve=log": [
                AutomationPoint(position_beats=0.0, value=0.25),
            ],
        },
    )

    bridge = PatternPerformanceBridge(config, tempo)
    playback = bridge.render_pattern(pattern, instrument)

    amp_event = next(
        event
        for event in playback.automation_log
        if event["module"] == "osc" and event["parameter"] == "amplitude"
    )
    freq_event = next(
        event
        for event in playback.automation_log
        if event["module"] == "osc" and event["parameter"] == "frequency_hz"
    )

    assert amp_event["lane_metadata"]["curve"] == "exponential"
    assert amp_event["value"] == pytest.approx(0.25)
    assert freq_event["lane_metadata"]["curve"] == "log"
    # sqrt(0.25) = 0.5 ➜ halfway between min/max frequency (20 Hz ➜ 20_000 Hz)
    assert freq_event["value"] == pytest.approx(10_010.0, rel=1e-4)


def test_automation_curve_intensity_adjusts_mapping():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=128, channels=2)
    tempo = TempoMap(tempo_bpm=110.0)

    instrument = InstrumentDefinition(
        id="tone",
        name="Dynamic Tone",
        modules=[
            InstrumentModule(
                id="osc",
                type="sine",
                parameters={"amplitude": 0.2, "frequency_hz": 440.0},
            ),
        ],
    )

    pattern = Pattern(
        id="curve_intensity",
        name="Curve Intensity",
        length_steps=4,
        automation={
            "osc.amplitude|normalized|curve=exponential:3.0": [
                AutomationPoint(position_beats=0.0, value=0.5)
            ],
            "osc.frequency_hz|normalized|curve=log:4.0": [
                AutomationPoint(position_beats=0.0, value=0.25)
            ],
            "osc.amplitude|normalized|curve=s_curve:0.5": [
                AutomationPoint(position_beats=1.0, value=0.75)
            ],
        },
    )

    bridge = PatternPerformanceBridge(config, tempo)
    playback = bridge.render_pattern(pattern, instrument)

    amp_events = [
        event
        for event in playback.automation_log
        if event["module"] == "osc" and event["parameter"] == "amplitude"
    ]
    freq_event = next(
        event
        for event in playback.automation_log
        if event["module"] == "osc" and event["parameter"] == "frequency_hz"
    )

    first_amp = next(event for event in amp_events if event["beats"] == pytest.approx(0.0))
    second_amp = next(event for event in amp_events if event["beats"] == pytest.approx(1.0))

    assert first_amp["lane_metadata"]["curve"] == "exponential"
    assert first_amp["lane_metadata"]["curve_intensity"] == pytest.approx(3.0)
    assert first_amp["value"] == pytest.approx(0.5**3, rel=1e-5)

    expected_freq = 20.0 + (20_000.0 - 20.0) * (0.25 ** (1.0 / 4.0))
    assert freq_event["lane_metadata"]["curve_intensity"] == pytest.approx(4.0)
    assert freq_event["value"] == pytest.approx(expected_freq, rel=1e-5)

    assert isinstance(second_amp["lane_metadata"], dict)
    assert second_amp["lane_metadata"]["curve"] == "s_curve"
    assert second_amp["lane_metadata"]["curve_intensity"] == pytest.approx(0.5)
    assert second_amp["value"] == pytest.approx(0.7, rel=0.1)


def test_automation_lane_smoothing_averages_collisions():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=128, channels=2)
    tempo = TempoMap(tempo_bpm=100.0)

    instrument = InstrumentDefinition(
        id="tone",
        name="Simple Tone",
        modules=[
            InstrumentModule(
                id="osc",
                type="sine",
                parameters={"amplitude": 0.2, "frequency_hz": 220.0},
            ),
        ],
    )

    pattern = Pattern(
        id="automation_smoothing",
        name="Automation Smoothing",
        length_steps=4,
        automation={
            "osc.amplitude|normalized": [AutomationPoint(position_beats=0.0, value=0.2)],
            "osc.amplitude|percent|range=0.0:1.0": [
                AutomationPoint(position_beats=0.0, value=80.0)
            ],
        },
    )

    bridge = PatternPerformanceBridge(config, tempo)
    playback = bridge.render_pattern(pattern, instrument)

    amp_event = next(
        event
        for event in playback.automation_log
        if event["module"] == "osc"
        and event["parameter"] == "amplitude"
        and event["beats"] == pytest.approx(0.0)
    )

    assert amp_event["value"] == pytest.approx((0.2 + 0.8) / 2.0)
    assert isinstance(amp_event["lane_metadata"], list)
    assert {meta["mode"] for meta in amp_event["lane_metadata"]} == {"normalized", "percent"}
    assert amp_event["smoothing_mode"] == "average"
    assert amp_event["smoothed_values"] == pytest.approx([0.2, 0.8])
    assert sorted(amp_event["smoothing_sources"]) == sorted(pattern.automation.keys())
    assert amp_event["source_value"] == [0.2, 80.0]
    assert "smoothing" not in amp_event


def test_automation_lane_smoothing_creates_linear_ramp():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=120, channels=2)
    tempo = TempoMap(tempo_bpm=120.0)

    instrument = InstrumentDefinition(
        id="tone",
        name="Smooth Tone",
        modules=[
            InstrumentModule(
                id="osc",
                type="sine",
                parameters={"amplitude": 0.2, "frequency_hz": 330.0},
            ),
        ],
    )

    pattern = Pattern(
        id="automation_smoothing_window",
        name="Automation Smoothing Window",
        length_steps=4,
        automation={
            "osc.amplitude|normalized|smooth=5ms": [
                AutomationPoint(position_beats=1.0, value=0.6)
            ],
        },
    )

    bridge = PatternPerformanceBridge(config, tempo)
    engine = OfflineAudioEngine(config, tempo=tempo)
    modules = bridge._instantiate_instrument(engine, instrument)
    automation_log: list[dict[str, object]] = []
    bridge._schedule_automation_lanes(engine, pattern, modules, automation_log)

    events = sorted(engine.timeline._events, key=lambda evt: evt.time_seconds)
    assert len(events) >= 3

    seconds_per_beat = tempo.beats_to_seconds(1.0)
    start_time = seconds_per_beat * (1.0 - 0.01)
    assert events[0].time_seconds == pytest.approx(start_time, rel=1e-3)
    assert events[-1].time_seconds == pytest.approx(seconds_per_beat * 1.0, rel=1e-3)

    values = [event.value for event in events]
    assert values[0] == pytest.approx(0.2)
    assert values[-1] == pytest.approx(0.6)
    assert any(abs(v - 0.4) <= 0.08 for v in values[1:-1])

    assert len(automation_log) == 1
    smoothing = automation_log[0]["smoothing"]
    assert smoothing["applied"] is True
    assert smoothing["strategy"] == "linear_ramp"
    assert smoothing["previous_value"] == pytest.approx(0.2)
    assert smoothing["window_seconds"] == pytest.approx(0.005, rel=0.2)
    assert smoothing["segments"] >= 3


def test_automation_lane_smoothing_respects_segment_override():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=120, channels=2)
    tempo = TempoMap(tempo_bpm=128.0)

    instrument = InstrumentDefinition(
        id="tone",
        name="Segmented Tone",
        modules=[
            InstrumentModule(
                id="osc",
                type="sine",
                parameters={"amplitude": 0.2, "frequency_hz": 330.0},
            ),
        ],
    )

    pattern = Pattern(
        id="automation_segments",
        name="Automation Segments",
        length_steps=4,
        automation={
            "osc.amplitude|normalized|smooth=8ms:5": [
                AutomationPoint(position_beats=1.0, value=0.7)
            ],
        },
    )

    bridge = PatternPerformanceBridge(config, tempo)
    engine = OfflineAudioEngine(config, tempo=tempo)
    modules = bridge._instantiate_instrument(engine, instrument)
    automation_log: list[dict[str, object]] = []
    bridge._schedule_automation_lanes(engine, pattern, modules, automation_log)

    events = sorted(engine.timeline._events, key=lambda evt: evt.time_seconds)
    assert len(events) == 5
    smoothing_entry = automation_log[0]["smoothing"]
    assert smoothing_entry["segments"] == 5
    assert smoothing_entry["strategy"] == "linear_ramp"


def test_automation_dashboard_rows_surface_metadata():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=120, channels=2)
    tempo = TempoMap(tempo_bpm=110.0)

    instrument = InstrumentDefinition(
        id="tone",
        name="Dashboard Tone",
        modules=[
            InstrumentModule(
                id="osc",
                type="sine",
                parameters={"amplitude": 0.25, "frequency_hz": 220.0},
            ),
        ],
    )

    pattern = Pattern(
        id="automation_dashboard",
        name="Automation Dashboard",
        length_steps=4,
        automation={
            "osc.amplitude|normalized|smooth=6ms:4": [
                AutomationPoint(position_beats=1.0, value=0.5)
            ],
            "osc.amplitude|percent|range=0.0:1.0": [
                AutomationPoint(position_beats=1.0, value=80.0)
            ],
        },
    )

    bridge = PatternPerformanceBridge(config, tempo)
    playback = bridge.render_pattern(pattern, instrument)
    rows = bridge.automation_smoothing_rows(playback)

    assert rows, "Expected smoothing rows to be generated"
    row = rows[0]
    assert row["label"] == "osc.amplitude"
    assert row["identifier"].startswith("osc.amplitude@")
    assert row["event_id"] == row["identifier"]
    assert isinstance(row["event_index"], int)
    assert row["applied"] is True
    assert row["segments"] == 4
    assert row["segment_total"] == 4
    assert row["segment_breakdown"] == {"osc.amplitude|normalized|smooth=6ms:4": 4}
    assert row["strategy"] == "linear_ramp"
    assert row["sources"]
    assert row["mode"] == "average"
    assert row["resolved_values"]


def test_automation_smoothing_rows_capture_multi_lane_segment_totals():
    sample_rate = 24_000
    config = EngineConfig(sample_rate=sample_rate, block_size=120, channels=2)
    tempo = TempoMap(tempo_bpm=110.0)

    instrument = InstrumentDefinition(
        id="tone",
        name="Dashboard Tone",
        modules=[
            InstrumentModule(
                id="osc",
                type="sine",
                parameters={"amplitude": 0.25, "frequency_hz": 220.0},
            ),
        ],
    )

    pattern = Pattern(
        id="automation_dashboard_collisions",
        name="Automation Dashboard Collisions",
        length_steps=4,
        automation={
            "osc.amplitude|normalized|smooth=4ms:5": [
                AutomationPoint(position_beats=1.0, value=0.5)
            ],
            "osc.amplitude|percent|smooth=4ms:9": [
                AutomationPoint(position_beats=1.0, value=60.0)
            ],
        },
    )

    bridge = PatternPerformanceBridge(config, tempo)
    playback = bridge.render_pattern(pattern, instrument)
    rows = bridge.automation_smoothing_rows(playback)

    assert rows, "Expected smoothing rows to be generated"
    row = rows[0]
    assert row["segment_total"] == 14
    assert row["segment_breakdown"] == {
        "osc.amplitude|normalized|smooth=4ms:5": 5,
        "osc.amplitude|percent|smooth=4ms:9": 9,
    }
    assert set(row["sources"]) == {
        "osc.amplitude|normalized|smooth=4ms:5",
        "osc.amplitude|percent|smooth=4ms:9",
    }
