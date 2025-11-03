"""Musician-oriented audio modules built on the engine scaffolding."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from .engine import BaseAudioModule, EngineConfig, ParameterSpec


@dataclass
class SineOscillatorConfig:
    """Configuration for the sine oscillator module."""

    amplitude: float = 0.25
    frequency_hz: float = 440.0


class SineOscillator(BaseAudioModule):
    """Stereo sine oscillator with amplitude and pitch controls."""

    def __init__(
        self,
        name: str,
        config: EngineConfig,
        *,
        module_config: SineOscillatorConfig | None = None,
    ) -> None:
        module_config = module_config or SineOscillatorConfig()
        parameters: Iterable[ParameterSpec] = [
            ParameterSpec(
                name="amplitude",
                display_name="Loudness",
                default=module_config.amplitude,
                minimum=0.0,
                maximum=1.0,
                unit="",
                description="Overall output level scaled for headroom.",
                musical_context="dynamics",
            ),
            ParameterSpec(
                name="frequency_hz",
                display_name="Pitch",
                default=module_config.frequency_hz,
                minimum=20.0,
                maximum=20_000.0,
                unit="Hz",
                description="Fundamental frequency of the oscillator.",
                musical_context="pitch",
            ),
        ]
        super().__init__(name, config, parameters)
        self._phase = 0.0

    def process(self, frames: int) -> np.ndarray:
        amplitude = float(self.get_parameter("amplitude"))
        frequency = float(self.get_parameter("frequency_hz"))
        increment = 2.0 * math.pi * frequency / self.config.sample_rate
        positions = self._phase + increment * np.arange(frames, dtype=np.float32)
        self._phase = float((positions[-1] + increment) % (2.0 * math.pi))
        tone = np.sin(positions, dtype=np.float32) * amplitude
        return np.repeat(tone[:, None], self.config.channels, axis=1)


class AmplitudeEnvelope(BaseAudioModule):
    """One-knob gate with musical attack/release smoothing."""

    def __init__(
        self,
        name: str,
        config: EngineConfig,
        *,
        source: BaseAudioModule,
        attack_ms: float = 10.0,
        release_ms: float = 120.0,
    ) -> None:
        parameters: Iterable[ParameterSpec] = [
            ParameterSpec(
                name="gate",
                display_name="Gate",
                default=1.0,
                minimum=0.0,
                maximum=1.0,
                unit="",
                description="Target loudness for the envelope (0 = silent, 1 = full level).",
                musical_context="dynamics",
            ),
            ParameterSpec(
                name="attack_ms",
                display_name="Attack",
                default=attack_ms,
                minimum=0.0,
                maximum=5_000.0,
                unit="ms",
                description="How quickly the sound opens after a cue.",
                musical_context="articulation",
            ),
            ParameterSpec(
                name="release_ms",
                display_name="Release",
                default=release_ms,
                minimum=0.0,
                maximum=5_000.0,
                unit="ms",
                description="How gently the sound fades after the gate closes.",
                musical_context="articulation",
            ),
        ]
        super().__init__(name, config, parameters)
        self._source = source
        self._level = float(self.get_parameter("gate"))

    def _time_to_coefficient(self, time_ms: float) -> float:
        if time_ms <= 0.0:
            return 0.0
        seconds = time_ms / 1_000.0
        return math.exp(-1.0 / (seconds * self.config.sample_rate))

    def process(self, frames: int) -> np.ndarray:
        buffer = self._source.process(frames)
        if frames == 0:
            return buffer

        gate = float(self.get_parameter("gate"))
        attack = float(self.get_parameter("attack_ms"))
        release = float(self.get_parameter("release_ms"))

        attack_coeff = self._time_to_coefficient(attack)
        release_coeff = self._time_to_coefficient(release)

        envelope = np.empty(frames, dtype=np.float32)
        level = self._level
        for idx in range(frames):
            coeff = attack_coeff if gate > level else release_coeff
            level = gate + (level - gate) * coeff
            envelope[idx] = level
        self._level = float(level)

        return buffer * envelope[:, None]


class OnePoleLowPass(BaseAudioModule):
    """Simple low-pass filter tuned for smooth tone-shaping gestures."""

    def __init__(
        self,
        name: str,
        config: EngineConfig,
        *,
        source: BaseAudioModule,
        cutoff_hz: float = 4_000.0,
        mix: float = 1.0,
    ) -> None:
        parameters: Iterable[ParameterSpec] = [
            ParameterSpec(
                name="cutoff_hz",
                display_name="Cutoff",
                default=cutoff_hz,
                minimum=20.0,
                maximum=min(20_000.0, config.sample_rate / 2.0),
                unit="Hz",
                description="Frequency where highs start to roll off.",
                musical_context="tone",
            ),
            ParameterSpec(
                name="mix",
                display_name="Wet Mix",
                default=mix,
                minimum=0.0,
                maximum=1.0,
                unit="",
                description="Blend between raw tone (0) and filtered sound (1).",
                musical_context="tone",
            ),
        ]
        super().__init__(name, config, parameters)
        self._source = source
        self._state = np.zeros(config.channels, dtype=np.float32)

    def process(self, frames: int) -> np.ndarray:
        cutoff = float(self.get_parameter("cutoff_hz"))
        mix = float(self.get_parameter("mix"))
        dry = self._source.process(frames)
        if frames == 0:
            return dry

        alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / self.config.sample_rate)

        output = np.empty_like(dry)
        state = self._state
        for idx in range(frames):
            state += alpha * (dry[idx] - state)
            output[idx] = dry[idx] * (1.0 - mix) + state * mix
        self._state = state.astype(np.float32)
        return output


__all__ = [
    "AmplitudeEnvelope",
    "OnePoleLowPass",
    "SineOscillator",
    "SineOscillatorConfig",
]
