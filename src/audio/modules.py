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
        amplitude = self.get_parameter("amplitude")
        frequency = self.get_parameter("frequency_hz")
        increment = 2.0 * math.pi * frequency / self.config.sample_rate
        positions = self._phase + increment * np.arange(frames, dtype=np.float32)
        self._phase = float((positions[-1] + increment) % (2.0 * math.pi))
        tone = np.sin(positions, dtype=np.float32) * amplitude
        return np.repeat(tone[:, None], self.config.channels, axis=1)


__all__ = ["SineOscillator", "SineOscillatorConfig"]
