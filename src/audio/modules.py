"""Musician-oriented audio modules built on the engine scaffolding."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np

from .engine import BaseAudioModule, EngineConfig, ParameterSpec


@dataclass(frozen=True)
class ClipSampleLayer:
    """Velocity-aware sample description used by :class:`ClipSampler`."""

    sample: np.ndarray
    min_velocity: int = 0
    max_velocity: int = 127
    amplitude_scale: float = 1.0
    start_offset_percent: float = 0.0

    def includes(self, velocity: int) -> bool:
        return self.min_velocity <= velocity <= self.max_velocity


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
    """Musician-facing clip sampler with velocity gestures and layering."""

    def __init__(
        self,
        name: str,
        config: EngineConfig,
        *,
        sample: np.ndarray | None = None,
        layers: Sequence[ClipSampleLayer] | None = None,
        root_midi_note: int = 60,
        amplitude: float = 1.0,
        start_percent: float = 0.0,
        length_percent: float = 1.0,
        playback_rate: float = 1.0,
        loop: bool = False,
    ) -> None:
        if sample is None and not layers:
            raise ValueError("ClipSampler requires a sample or velocity layers")
        prepared_layers = self._prepare_layers(config, sample, layers)
        self._layers = tuple(prepared_layers)
        self._loop = loop
        self._root_midi_note = root_midi_note
        self._layer_windows: dict[int, tuple[int, int]] = {}
        self._layer_positions: dict[int, float] = {}
        self._layer_weights: dict[int, float] = {0: 1.0}
        self._layer_mix_scale = self._layers[0].amplitude_scale
        self._pending_retrigger = True
        self._window_dirty = True
        self._velocity_dirty = True
        self._velocity = 127
        self._velocity_gain = 1.0
        self._velocity_start_offset = 0.0
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
            ParameterSpec(
                name="velocity",
                display_name="Velocity",
                default=float(self._velocity),
                minimum=1.0,
                maximum=127.0,
                unit="MIDI",
                description="Latest MIDI velocity applied from tracker patterns.",
                musical_context="dynamics",
            ),
            ParameterSpec(
                name="velocity_amplitude_min",
                display_name="Velocity Min Gain",
                default=0.35,
                minimum=0.0,
                maximum=2.0,
                unit="×",
                description="Output gain applied at the softest velocity (relative to Clip Level).",
                musical_context="dynamics",
            ),
            ParameterSpec(
                name="velocity_amplitude_max",
                display_name="Velocity Max Gain",
                default=1.0,
                minimum=0.0,
                maximum=2.0,
                unit="×",
                description="Output gain applied at the hardest velocity (relative to Clip Level).",
                musical_context="dynamics",
            ),
            ParameterSpec(
                name="velocity_start_offset_percent",
                display_name="Velocity Start Offset",
                default=0.0,
                minimum=-1.0,
                maximum=1.0,
                unit="%",
                description=(
                    "Extra start offset applied at the softest velocity; negative values "
                    "pull harder hits earlier."
                ),
                musical_context="phrasing",
            ),
            ParameterSpec(
                name="velocity_crossfade_width",
                display_name="Velocity Crossfade",
                default=0.0,
                minimum=0.0,
                maximum=64.0,
                unit="MIDI",
                description=(
                    "Blend neighbouring velocity layers within this many MIDI steps to smooth "
                    "legato passages."
                ),
                musical_context="dynamics",
            ),
        ]
        super().__init__(name, config, parameters)

    def set_parameter(self, name: str, value: float | None) -> None:  # type: ignore[override]
        super().set_parameter(name, value)
        if name in {"start_percent", "length_percent"}:
            self._window_dirty = True
        if name in {
            "velocity",
            "velocity_amplitude_min",
            "velocity_amplitude_max",
            "velocity_crossfade_width",
        }:
            self._velocity_dirty = True
        if name in {"velocity", "velocity_start_offset_percent"}:
            self._window_dirty = True
        if name == "velocity" and value is not None:
            self._velocity = int(max(1, min(127, round(value))))
        if name == "retrigger" and value is not None and value > 0.0:
            self._pending_retrigger = True

    def _prepare_layers(
        self,
        config: EngineConfig,
        sample: np.ndarray | None,
        layers: Sequence[ClipSampleLayer] | None,
    ) -> list[ClipSampleLayer]:
        prepared: list[ClipSampleLayer] = []
        raw_layers = list(layers or [])
        if sample is not None:
            raw_layers.insert(0, ClipSampleLayer(sample=sample))
        if not raw_layers:
            raise ValueError("No sample data provided for ClipSampler")
        for layer in raw_layers:
            buffer = np.asarray(layer.sample, dtype=np.float32)
            if buffer.ndim == 1:
                buffer = buffer[:, None]
            if buffer.shape[1] == 1 and config.channels > 1:
                buffer = np.repeat(buffer, config.channels, axis=1)
            if buffer.shape[1] != config.channels:
                raise ValueError(
                    "Sample channel count must match engine configuration; "
                    f"received {buffer.shape[1]} channels for {config.channels} channel engine"
                )
            prepared.append(
                ClipSampleLayer(
                    sample=buffer,
                    min_velocity=max(0, int(layer.min_velocity)),
                    max_velocity=min(127, int(layer.max_velocity)),
                    amplitude_scale=float(layer.amplitude_scale),
                    start_offset_percent=float(layer.start_offset_percent),
                )
            )
        prepared.sort(key=lambda layer: (layer.min_velocity, layer.max_velocity))
        return prepared

    def _refresh_window(self) -> None:
        active_indices = list(self._layer_weights.keys())
        base_start = float(self.get_parameter("start_percent") or 0.0)
        length_percent = float(self.get_parameter("length_percent") or 0.0)
        length_percent = min(max(length_percent, 0.0), 1.0)

        for index in list(self._layer_windows.keys()):
            if index not in active_indices:
                self._layer_windows.pop(index, None)
                self._layer_positions.pop(index, None)

        for index in active_indices:
            layer = self._layers[index]
            total_frames = len(layer.sample)
            clip_frames = max(1, int(round(length_percent * total_frames)))
            max_start = max(0, total_frames - clip_frames)
            extra_start = self._velocity_start_offset + layer.start_offset_percent
            effective_start = min(max(base_start + extra_start, 0.0), 1.0)
            start_frame = int(round(effective_start * max_start))
            end_frame = min(total_frames, start_frame + clip_frames)
            if end_frame <= start_frame:
                end_frame = min(total_frames, start_frame + 1)
            self._layer_windows[index] = (start_frame, end_frame)
            position = self._layer_positions.get(index)
            if position is None or not (start_frame <= position < end_frame):
                self._layer_positions[index] = float(start_frame)
        self._window_dirty = False

    def _next_frame(self, rate: float) -> np.ndarray:
        output = np.zeros(self.config.channels, dtype=np.float32)
        silent_layers = 0
        active_layers = list(self._layer_weights.items())
        for index, weight in active_layers:
            start_frame, end_frame = self._layer_windows.get(index, (0, 0))
            if start_frame >= end_frame:
                silent_layers += 1
                continue
            position = self._layer_positions.get(index, float(start_frame))
            if position >= end_frame:
                if self._loop:
                    position = float(start_frame)
                else:
                    self._layer_positions[index] = float(end_frame)
                    silent_layers += 1
                    continue
            int_index = int(position)
            frac = position - int_index
            sample = self._layers[index].sample
            if int_index >= end_frame - 1:
                frame = sample[end_frame - 1]
            else:
                frame = (1.0 - frac) * sample[int_index] + frac * sample[int_index + 1]
            self._layer_positions[index] = position + rate
            output += frame.astype(np.float32) * weight
        if not self._loop and silent_layers == len(active_layers):
            return np.zeros(self.config.channels, dtype=np.float32)
        return output

    def process(self, frames: int) -> np.ndarray:
        if frames <= 0:
            return np.zeros((0, self.config.channels), dtype=np.float32)

        if self._velocity_dirty:
            self._update_velocity_mapping()
        if self._window_dirty:
            self._refresh_window()

        amplitude = float(self.get_parameter("amplitude") or 0.0)
        amplitude *= self._velocity_gain * self._layer_mix_scale
        if amplitude <= 0.0:
            return np.zeros((frames, self.config.channels), dtype=np.float32)

        base_rate = float(self.get_parameter("playback_rate") or 0.0)
        transpose = float(self.get_parameter("transpose_semitones") or 0.0)
        if base_rate <= 0.0:
            return np.zeros((frames, self.config.channels), dtype=np.float32)

        rate = base_rate * (2.0 ** (transpose / 12.0))

        if self._pending_retrigger:
            for index, (start_frame, _) in self._layer_windows.items():
                self._layer_positions[index] = float(start_frame)
            self._pending_retrigger = False
        # Reset retrigger parameter so a future automation event can fire again.
        super().set_parameter("retrigger", 0.0)

        output = np.zeros((frames, self.config.channels), dtype=np.float32)
        for idx in range(frames):
            frame = self._next_frame(rate)
            if not frame.any() and not self._loop:
                if all(
                    self._layer_positions.get(index, window[1]) >= window[1]
                    for index, window in self._layer_windows.items()
                ):
                    break
            output[idx] = frame * amplitude
        return output

    def _select_layer_index(self, velocity: int) -> int:
        for index, layer in enumerate(self._layers):
            if layer.includes(velocity):
                return index
        return len(self._layers) - 1

    def _update_velocity_mapping(self) -> None:
        velocity = int(max(0, min(127, self._velocity)))
        primary_index = self._select_layer_index(velocity)

        crossfade_width = float(self.get_parameter("velocity_crossfade_width") or 0.0)
        new_weights: dict[int, float]
        if crossfade_width <= 0.0:
            new_weights = {primary_index: 1.0}
        else:
            candidates: list[tuple[int, float]] = []
            for index, layer in enumerate(self._layers):
                min_velocity = layer.min_velocity
                max_velocity = layer.max_velocity
                if min_velocity <= velocity <= max_velocity:
                    weight = 1.0
                elif velocity < min_velocity:
                    delta = min_velocity - velocity
                    if delta > crossfade_width:
                        weight = 0.0
                    else:
                        weight = max(0.0, 1.0 - (delta / crossfade_width))
                else:
                    delta = velocity - max_velocity
                    if delta > crossfade_width:
                        weight = 0.0
                    else:
                        weight = max(0.0, 1.0 - (delta / crossfade_width))
                if weight > 0.0:
                    candidates.append((index, weight))
            if not candidates:
                candidates = [(primary_index, 1.0)]
            candidates.sort(key=lambda item: item[1], reverse=True)
            candidates = candidates[:2]
            total = sum(weight for _, weight in candidates)
            if total <= 0.0:
                new_weights = {primary_index: 1.0}
            else:
                new_weights = {index: weight / total for index, weight in candidates}

        if set(new_weights.keys()) != set(self._layer_weights.keys()):
            self._window_dirty = True
        self._layer_weights = new_weights
        self._layer_mix_scale = sum(
            self._layers[index].amplitude_scale * weight for index, weight in new_weights.items()
        )

        min_gain = float(self.get_parameter("velocity_amplitude_min") or 0.0)
        max_gain = float(self.get_parameter("velocity_amplitude_max") or 0.0)
        velocity_norm = velocity / 127.0 if velocity > 0 else 0.0
        gain = (min_gain * (1.0 - velocity_norm)) + (max_gain * velocity_norm)
        self._velocity_gain = float(max(gain, 0.0))

        start_param = float(self.get_parameter("velocity_start_offset_percent") or 0.0)
        self._velocity_start_offset = (1.0 - velocity_norm) * start_param

        self._velocity_dirty = False


__all__ = [
    "ClipSampleLayer",
    "ClipSampler",
    "AmplitudeEnvelope",
    "OnePoleLowPass",
    "SineOscillator",
    "SineOscillatorConfig",
]
