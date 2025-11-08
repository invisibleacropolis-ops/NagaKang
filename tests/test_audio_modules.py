import numpy as np
import pytest

from audio.engine import EngineConfig, OfflineAudioEngine
from audio.metrics import integrated_lufs, rms_dbfs
from audio.modules import (
    AmplitudeEnvelope,
    ClipSampler,
    ClipSampleLayer,
    OnePoleLowPass,
    SineOscillator,
)


pytestmark = pytest.mark.skipif(np is None, reason="NumPy is required for audio module tests")


def test_envelope_and_filter_chain_responds_to_automation():
    config = EngineConfig(sample_rate=48_000, block_size=64, channels=2)
    engine = OfflineAudioEngine(config)

    oscillator = SineOscillator("osc", config)
    envelope = AmplitudeEnvelope("env", config, source=oscillator, attack_ms=5.0, release_ms=30.0)
    filter_module = OnePoleLowPass("lp", config, source=envelope, cutoff_hz=800.0)

    engine.add_module(oscillator)
    engine.add_module(envelope)
    engine.add_module(filter_module, as_output=True)

    engine.schedule_parameter_change("osc", "amplitude", beats=0.0, value=0.4)
    engine.schedule_parameter_change("env", "gate", beats=0.0, value=0.0)
    engine.schedule_parameter_change("env", "gate", beats=1.0, value=1.0)
    engine.schedule_parameter_change("env", "gate", beats=3.0, value=0.0)
    engine.schedule_parameter_change("lp", "cutoff_hz", beats=0.0, value=400.0)
    engine.schedule_parameter_change("lp", "cutoff_hz", beats=2.0, value=6_000.0)

    audio = engine.render(4.0)
    assert audio.shape == (192_000, 2)

    start_rms = float(np.sqrt(np.mean(np.square(audio[: 24_000, 0]))))
    peak_rms = float(np.sqrt(np.mean(np.square(audio[72_000:96_000, 0]))))
    tail_rms = float(np.sqrt(np.mean(np.square(audio[150_000:, 0]))))

    assert start_rms < peak_rms * 0.75  # gate eased in from silence
    assert peak_rms > 0.03  # gate opened and filter raised
    assert tail_rms < peak_rms * 0.6  # release applied near the end


def test_sampler_respects_windowing_and_envelope_layer():
    config = EngineConfig(sample_rate=48_000, block_size=128, channels=2)
    engine = OfflineAudioEngine(config)

    time = np.linspace(0.0, 1.0, config.sample_rate, dtype=np.float32)
    sample = np.stack(
        [
            np.sin(2.0 * np.pi * 220.0 * time, dtype=np.float32),
            np.sin(2.0 * np.pi * 440.0 * time, dtype=np.float32),
        ],
        axis=1,
    )

    sampler = ClipSampler(
        "clip",
        config,
        sample=sample,
        start_percent=0.25,
        length_percent=0.25,
        amplitude=0.9,
    )
    envelope = AmplitudeEnvelope("clip_env", config, source=sampler, attack_ms=12.0, release_ms=60.0)
    filter_module = OnePoleLowPass("clip_lp", config, source=envelope, cutoff_hz=3_000.0)

    engine.add_module(sampler)
    engine.add_module(envelope)
    engine.add_module(filter_module, as_output=True)

    engine.schedule_parameter_change("clip", "retrigger", beats=0.0, value=1.0)
    engine.schedule_parameter_change("clip", "retrigger", beats=2.0, value=1.0)
    engine.schedule_parameter_change("clip", "transpose_semitones", beats=2.0, value=12.0)
    engine.schedule_parameter_change("clip_env", "gate", beats=0.0, value=1.0)
    engine.schedule_parameter_change("clip_env", "gate", beats=1.0, value=0.0)
    engine.schedule_parameter_change("clip_env", "gate", beats=2.0, value=1.0)
    engine.schedule_parameter_change("clip_env", "gate", beats=3.0, value=0.0)

    audio = engine.render(4.0)

    seconds_per_beat = engine.tempo.beats_to_seconds(1.0)
    frames_per_beat = int(round(seconds_per_beat * config.sample_rate))
    first_note = audio[:frames_per_beat]
    gap = audio[frames_per_beat : frames_per_beat * 2]
    second_note = audio[frames_per_beat * 2 : frames_per_beat * 3]

    def _rms(block: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(block), dtype=np.float32)))

    first_rms = _rms(first_note)
    gap_rms = _rms(gap)
    second_rms = _rms(second_note)

    assert first_rms > 0.05
    assert gap_rms < first_rms * 0.7
    assert second_rms > first_rms * 0.5

    retrigger_param = sampler.get_parameter("retrigger")
    assert retrigger_param == pytest.approx(0.0)


def test_sampler_velocity_shapes_start_and_dynamics():
    config = EngineConfig(sample_rate=24_000, block_size=128, channels=2)
    engine = OfflineAudioEngine(config)

    frames = config.sample_rate
    ramp = np.linspace(0.0, 1.0, frames, dtype=np.float32)
    sample = np.stack([ramp, ramp], axis=1)

    sampler = ClipSampler(
        "clip",
        config,
        sample=sample,
        amplitude=0.8,
        start_percent=0.0,
        length_percent=0.5,
    )
    sampler.set_parameter("velocity_amplitude_min", 0.2)
    sampler.set_parameter("velocity_amplitude_max", 1.0)
    sampler.set_parameter("velocity_start_offset_percent", 0.4)

    engine.add_module(sampler, as_output=True)

    engine.schedule_parameter_change("clip", "velocity", beats=0.0, value=35.0)
    engine.schedule_parameter_change("clip", "retrigger", beats=0.0, value=1.0)
    engine.schedule_parameter_change("clip", "velocity", beats=2.0, value=120.0)
    engine.schedule_parameter_change("clip", "retrigger", beats=2.0, value=1.0)

    audio = engine.render(4.0)

    seconds_per_beat = engine.tempo.beats_to_seconds(1.0)
    frames_per_beat = int(round(seconds_per_beat * config.sample_rate))
    soft = audio[:frames_per_beat]
    loud = audio[frames_per_beat * 2 : frames_per_beat * 3]

    def _rms(block: np.ndarray) -> float:
        if block.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(block[:, 0]))))

    assert _rms(soft) < _rms(loud) * 0.75

    def _first_strong_index(block: np.ndarray) -> int:
        magnitudes = np.abs(block[:, 0])
        threshold = 0.05
        above = np.where(magnitudes > threshold)[0]
        return int(above[0]) if above.size else len(block)

    assert _first_strong_index(soft) < _first_strong_index(loud)


def test_sampler_velocity_layers_select_buffers():
    config = EngineConfig(sample_rate=12_000, block_size=64, channels=2)
    engine = OfflineAudioEngine(config)

    frames = config.sample_rate // 2
    left_only = np.zeros((frames, 2), dtype=np.float32)
    left_only[:, 0] = 0.6
    right_only = np.zeros((frames, 2), dtype=np.float32)
    right_only[:, 1] = 0.9

    sampler = ClipSampler(
        "clip",
        config,
        layers=[
            ClipSampleLayer(sample=left_only, max_velocity=80, amplitude_scale=0.8),
            ClipSampleLayer(sample=right_only, min_velocity=81, amplitude_scale=1.2),
        ],
        amplitude=0.7,
        length_percent=0.4,
    )
    engine.add_module(sampler, as_output=True)

    engine.schedule_parameter_change("clip", "velocity", beats=0.0, value=60.0)
    engine.schedule_parameter_change("clip", "retrigger", beats=0.0, value=1.0)
    engine.schedule_parameter_change("clip", "velocity", beats=1.0, value=110.0)
    engine.schedule_parameter_change("clip", "retrigger", beats=1.0, value=1.0)

    audio = engine.render(2.0)
    frames_per_beat = int(round(engine.tempo.beats_to_seconds(1.0) * config.sample_rate))
    soft = audio[:frames_per_beat]
    loud = audio[frames_per_beat : frames_per_beat * 2]

    soft_left = float(np.mean(np.abs(soft[:, 0])))
    soft_right = float(np.mean(np.abs(soft[:, 1])))
    loud_left = float(np.mean(np.abs(loud[:, 0])))
    loud_right = float(np.mean(np.abs(loud[:, 1])))

    assert soft_left > soft_right * 3.0
    assert loud_right > loud_left * 3.0


def test_sampler_velocity_crossfade_blends_layers():
    config = EngineConfig(sample_rate=12_000, block_size=64, channels=2)
    engine = OfflineAudioEngine(config)

    frames = config.sample_rate // 2
    left = np.zeros((frames, 2), dtype=np.float32)
    left[:, 0] = 1.0
    right = np.zeros((frames, 2), dtype=np.float32)
    right[:, 1] = 1.0

    sampler = ClipSampler(
        "clip",
        config,
        layers=[
            ClipSampleLayer(sample=left, max_velocity=80, amplitude_scale=1.0),
            ClipSampleLayer(sample=right, min_velocity=81, amplitude_scale=1.0),
        ],
        amplitude=0.8,
        length_percent=0.6,
    )
    sampler.set_parameter("velocity_amplitude_min", 1.0)
    sampler.set_parameter("velocity_amplitude_max", 1.0)
    sampler.set_parameter("velocity_crossfade_width", 8.0)
    engine.add_module(sampler, as_output=True)

    engine.schedule_parameter_change("clip", "velocity", beats=0.0, value=75.0)
    engine.schedule_parameter_change("clip", "retrigger", beats=0.0, value=1.0)
    engine.schedule_parameter_change("clip", "velocity", beats=1.0, value=84.0)
    engine.schedule_parameter_change("clip", "retrigger", beats=1.0, value=1.0)

    audio = engine.render(2.0)
    frames_per_beat = int(round(engine.tempo.beats_to_seconds(1.0) * config.sample_rate))
    soft = audio[:frames_per_beat]
    blended = audio[frames_per_beat : frames_per_beat * 2]

    soft_left = float(np.mean(np.abs(soft[:, 0])))
    soft_right = float(np.mean(np.abs(soft[:, 1])))
    blend_left = float(np.mean(np.abs(blended[:, 0])))
    blend_right = float(np.mean(np.abs(blended[:, 1])))

    assert soft_left > soft_right * 3.0
    assert blend_right > blend_left
    assert blend_left > soft_left * 0.1  # crossfade preserved some left channel energy


def test_sampler_velocity_crossfade_preserves_decay_tails():
    config = EngineConfig(sample_rate=24_000, block_size=64, channels=2)
    engine = OfflineAudioEngine(config)

    frames = config.sample_rate // 2
    soft = np.zeros((frames, 2), dtype=np.float32)
    soft[:, 0] = np.linspace(0.9, 0.1, frames, dtype=np.float32)
    mid = np.zeros((frames, 2), dtype=np.float32)
    mid[:, 0] = np.linspace(0.4, 0.2, frames, dtype=np.float32)
    mid[:, 1] = np.linspace(0.2, 0.4, frames, dtype=np.float32)
    hard = np.zeros((frames, 2), dtype=np.float32)
    hard[:, 1] = np.linspace(1.1, 0.3, frames, dtype=np.float32)

    sampler = ClipSampler(
        "clip",
        config,
        layers=[
            ClipSampleLayer(sample=soft, max_velocity=70, amplitude_scale=0.85),
            ClipSampleLayer(sample=mid, min_velocity=60, max_velocity=105, amplitude_scale=1.0),
            ClipSampleLayer(sample=hard, min_velocity=106, amplitude_scale=1.15),
        ],
        amplitude=0.75,
    )
    sampler.set_parameter("velocity_crossfade_width", 12.0)
    sampler.set_parameter("velocity_amplitude_min", 1.0)
    sampler.set_parameter("velocity_amplitude_max", 1.0)
    engine.add_module(sampler, as_output=True)

    engine.schedule_parameter_change("clip", "velocity", beats=0.0, value=65.0)
    engine.schedule_parameter_change("clip", "retrigger", beats=0.0, value=1.0)
    engine.schedule_parameter_change("clip", "velocity", beats=1.0, value=112.0)
    engine.schedule_parameter_change("clip", "retrigger", beats=1.0, value=1.0)

    audio = engine.render(2.0)
    frames_per_beat = int(round(engine.tempo.beats_to_seconds(1.0) * config.sample_rate))
    high_note = audio[frames_per_beat : frames_per_beat * 2]
    tail_window = high_note[-frames_per_beat // 2 :]

    tail_left = float(np.mean(np.abs(tail_window[:, 0])))
    tail_right = float(np.mean(np.abs(tail_window[:, 1])))

    assert tail_right > tail_left  # harder layer still leans right
    assert tail_left > 0.05  # mid layer tail stayed present during blend
    assert tail_left > tail_right * 0.15  # avoid vanishing left channel when fading

def test_render_metrics_report_musician_friendly_numbers():
    config = EngineConfig(sample_rate=48_000, block_size=128, channels=2)
    engine = OfflineAudioEngine(config)
    oscillator = SineOscillator("osc", config)
    engine.add_module(oscillator, as_output=True)
    engine.schedule_parameter_change("osc", "amplitude", beats=0.0, value=0.5)
    audio = engine.render(1.0)

    db = rms_dbfs(audio)
    lufs = integrated_lufs(audio, sample_rate=config.sample_rate)

    assert db.shape == (2,)
    assert db[0] == pytest.approx(-9.03, abs=0.15)
    assert lufs == pytest.approx(-9.7, abs=1.0)
