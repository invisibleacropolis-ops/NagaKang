import math

import pytest

from prototypes.audio_engine_skeleton import AudioEngine, AudioSettings

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
