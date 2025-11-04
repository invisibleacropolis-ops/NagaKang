import math

import pytest

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore

from audio.engine import EngineConfig, TempoMap
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
