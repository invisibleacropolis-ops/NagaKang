import numpy as np
import pytest

from audio.engine import EngineConfig, OfflineAudioEngine
from audio.metrics import integrated_lufs, rms_dbfs
from audio.modules import AmplitudeEnvelope, OnePoleLowPass, SineOscillator


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
