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


class ClipSampler(BaseAudioModule):
    """Musician-facing clip sampler with start/length gestures and retriggers."""

    def __init__(
        self,
        name: str,
        config: EngineConfig,
        *,
        sample: np.ndarray,
        root_midi_note: int = 60,
        amplitude: float = 1.0,
        start_percent: float = 0.0,
        length_percent: float = 1.0,
        playback_rate: float = 1.0,
        loop: bool = False,
    ) -> None:
        if sample.ndim == 1:
            sample = sample[:, None]
        if sample.shape[1] == 1 and config.channels > 1:
            sample = np.repeat(sample, config.channels, axis=1)
        if sample.shape[1] != config.channels:
            raise ValueError(
                "Sample channel count must match engine configuration; "
                f"received {sample.shape[1]} channels for {config.channels} channel engine"
            )
        self._sample = sample.astype(np.float32)
        self._loop = loop
        self._root_midi_note = root_midi_note
        self._clip_start = 0
        self._clip_end = len(self._sample)
        self._position = float(self._clip_start)
        self._pending_retrigger = True
        self._window_dirty = True
        parameters: Iterable[ParameterSpec] = [
            ParameterSpec(
                name="amplitude",
                display_name="Clip Level",
                default=amplitude,
                minimum=0.0,
                maximum=1.0,
                unit="",
                description="Overall clip loudness before envelopes or mixers.",
                musical_context="dynamics",
            ),
            ParameterSpec(
                name="start_percent",
                display_name="Clip Start",
                default=start_percent,
                minimum=0.0,
                maximum=1.0,
                unit="%",
                description="Where playback begins within the clip (0 = start, 1 = end).",
                musical_context="phrasing",
            ),
            ParameterSpec(
                name="length_percent",
                display_name="Clip Length",
                default=length_percent,
                minimum=0.0,
                maximum=1.0,
                unit="%",
                description="Portion of the clip to audition (0 = micro-slice, 1 = full clip).",
                musical_context="arrangement",
            ),
            ParameterSpec(
                name="playback_rate",
                display_name="Playback Rate",
                default=playback_rate,
                minimum=0.0,
                maximum=8.0,
                unit="×",
                description="Speed multiplier before pitch transposition.",
                musical_context="pitch",
            ),
            ParameterSpec(
                name="transpose_semitones",
                display_name="Transpose",
                default=0.0,
                minimum=-36.0,
                maximum=36.0,
                unit="st",
                description="Semitone shift relative to the clip's root pitch.",
                musical_context="pitch",
            ),
            ParameterSpec(
                name="retrigger",
                display_name="Retrigger",
                default=0.0,
                minimum=0.0,
                maximum=1.0,
                unit="",
                description="Fire the clip from the configured start on demand (momentary).",
                musical_context="articulation",
            ),
        ]
        super().__init__(name, config, parameters)

    def set_parameter(self, name: str, value: float | None) -> None:  # type: ignore[override]
        super().set_parameter(name, value)
        if name in {"start_percent", "length_percent"}:
            self._window_dirty = True
        if name == "retrigger" and value is not None and value > 0.0:
            self._pending_retrigger = True

    def _refresh_window(self) -> None:
        total_frames = len(self._sample)
        start_percent = float(self.get_parameter("start_percent") or 0.0)
        length_percent = float(self.get_parameter("length_percent") or 0.0)
        length_percent = min(max(length_percent, 0.0), 1.0)
        clip_frames = max(1, int(round(length_percent * total_frames)))
        max_start = max(0, total_frames - clip_frames)
        start_frame = int(round(start_percent * max_start))
        end_frame = min(total_frames, start_frame + clip_frames)
        if end_frame <= start_frame:
            end_frame = min(total_frames, start_frame + 1)
        self._clip_start = start_frame
        self._clip_end = end_frame
        if not (self._clip_start <= self._position < self._clip_end):
            self._pending_retrigger = True
        self._window_dirty = False

    def _next_frame(self, rate: float) -> np.ndarray:
        if self._position >= self._clip_end:
            if self._loop:
                self._position = float(self._clip_start)
            else:
                return np.zeros(self.config.channels, dtype=np.float32)

        index = int(self._position)
        frac = self._position - index
        if index >= self._clip_end - 1:
            frame = self._sample[self._clip_end - 1]
        else:
            frame = (1.0 - frac) * self._sample[index] + frac * self._sample[index + 1]
        self._position += rate
        return frame.astype(np.float32)

    def process(self, frames: int) -> np.ndarray:
        if frames <= 0:
            return np.zeros((0, self.config.channels), dtype=np.float32)

        if self._window_dirty:
            self._refresh_window()

        amplitude = float(self.get_parameter("amplitude") or 0.0)
        if amplitude <= 0.0:
            return np.zeros((frames, self.config.channels), dtype=np.float32)

        base_rate = float(self.get_parameter("playback_rate") or 0.0)
        transpose = float(self.get_parameter("transpose_semitones") or 0.0)
        if base_rate <= 0.0:
            return np.zeros((frames, self.config.channels), dtype=np.float32)

        rate = base_rate * (2.0 ** (transpose / 12.0))

        if self._pending_retrigger:
            self._position = float(self._clip_start)
            self._pending_retrigger = False
        # Reset retrigger parameter so a future automation event can fire again.
        super().set_parameter("retrigger", 0.0)

        output = np.zeros((frames, self.config.channels), dtype=np.float32)
        for idx in range(frames):
            frame = self._next_frame(rate)
            if not frame.any() and not self._loop and self._position >= self._clip_end:
                break
            output[idx] = frame * amplitude
        return output


__all__ = [
    "ClipSampler",
    "AmplitudeEnvelope",
    "OnePoleLowPass",
    "SineOscillator",
    "SineOscillatorConfig",
]
