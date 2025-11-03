import numpy as np
import pytest

from audio.engine import AutomationTimeline, EngineConfig, OfflineAudioEngine, TempoMap
from audio.modules import SineOscillator


def test_tempo_map_conversions():
    tempo = TempoMap(tempo_bpm=90.0, beats_per_bar=3)
    assert pytest.approx(tempo.beats_to_seconds(1.5), rel=1e-6) == 1.0
    assert pytest.approx(tempo.bars_to_seconds(2.0), rel=1e-6) == tempo.beats_to_seconds(6.0)


def test_automation_timeline_in_beats():
    timeline = AutomationTimeline()
    tempo = TempoMap(tempo_bpm=60.0)
    timeline.schedule_in_beats(
        module="osc",
        parameter="frequency_hz",
        beats=2.0,
        value=880.0,
        tempo=tempo,
        source="pitch lift",
    )
    events = list(timeline.pop_events_up_to(2.0))
    assert len(events) == 1
    event = events[0]
    assert event.time_seconds == pytest.approx(2.0)
    assert event.source == "pitch lift"
    assert len(list(timeline.pop_events_up_to(10.0))) == 0


def test_offline_engine_renders_with_automation():
    config = EngineConfig(sample_rate=48_000, block_size=256, channels=2)
    engine = OfflineAudioEngine(config)
    oscillator = SineOscillator("lead", config)
    engine.add_module(oscillator, as_output=True)
    engine.schedule_parameter_change(
        module="lead",
        parameter="amplitude",
        beats=2.0,
        value=0.75,
        source="chorus entry",
    )

    audio = engine.render(2.0)
    assert audio.shape == (96_000, 2)

    first_section = audio[: int(0.75 * config.sample_rate), 0]
    later_section = audio[int(1.25 * config.sample_rate) :, 0]

    def rms(block: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(block))))

    first_rms = rms(first_section)
    later_rms = rms(later_section)
    assert later_rms > first_rms * 2.5
    assert later_rms < first_rms * 3.5
