"""Prototype insert processors for Step 6 mixer development.

The inserts defined here are intentionally lightweight but aim to mirror
the musician-first ergonomics laid out in the Comprehensive Development
Plan (README §6).  They accept numpy buffers shaped ``(frames, channels)``
and return processed buffers, making them directly compatible with the
``MixerChannel`` insert contract introduced in Step 6.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from .engine import EngineConfig


def _clamp_frequency(freq: float, sample_rate: int) -> float:
    nyquist = sample_rate / 2.0
    return float(max(10.0, min(freq, nyquist - 10.0)))


def _db_to_linear(value_db: float) -> float:
    return math.pow(10.0, value_db / 20.0)


def _linear_to_db(value: float) -> float:
    return 20.0 * math.log10(max(value, 1e-12))


class _Biquad:
    """Stateful Direct Form II biquad filter used by the EQ insert."""

    def __init__(self, b: Iterable[float], a: Iterable[float], channels: int) -> None:
        b0, b1, b2 = b
        a0, a1, a2 = a
        if not math.isclose(a0, 1.0):
            b0 /= a0
            b1 /= a0
            b2 /= a0
            a1 /= a0
            a2 /= a0
        self._b0 = float(b0)
        self._b1 = float(b1)
        self._b2 = float(b2)
        self._a1 = float(a1)
        self._a2 = float(a2)
        self._z1 = np.zeros(channels, dtype=np.float32)
        self._z2 = np.zeros(channels, dtype=np.float32)

    def process(self, buffer: np.ndarray) -> np.ndarray:
        if buffer.size == 0:
            return buffer
        output = np.empty_like(buffer, dtype=np.float32)
        for channel in range(buffer.shape[1]):
            z1 = float(self._z1[channel])
            z2 = float(self._z2[channel])
            for idx in range(buffer.shape[0]):
                x = float(buffer[idx, channel])
                y = self._b0 * x + z1
                z1_new = self._b1 * x - self._a1 * y + z2
                z2 = self._b2 * x - self._a2 * y
                z1 = z1_new
                output[idx, channel] = np.float32(y)
            self._z1[channel] = z1
            self._z2[channel] = z2
        return output


def _design_low_shelf(
    sample_rate: int, freq: float, gain_db: float, channels: int
) -> _Biquad | None:
    if abs(gain_db) < 1e-6:
        return None
    freq = _clamp_frequency(freq, sample_rate)
    a = math.pow(10.0, gain_db / 40.0)
    w0 = 2.0 * math.pi * freq / sample_rate
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    sqrt_a = math.sqrt(a)
    alpha = sin_w0 / 2.0 * math.sqrt(2.0)
    b0 = a * ((a + 1.0) - (a - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha)
    b1 = 2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0)
    b2 = a * ((a + 1.0) - (a - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha)
    a0 = (a + 1.0) + (a - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha
    a1 = -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0)
    a2 = (a + 1.0) + (a - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha
    return _Biquad((b0, b1, b2), (a0, a1, a2), channels=channels)


def _design_peak(
    sample_rate: int, freq: float, gain_db: float, q: float, channels: int
) -> _Biquad | None:
    if abs(gain_db) < 1e-6:
        return None
    freq = _clamp_frequency(freq, sample_rate)
    a = math.pow(10.0, gain_db / 40.0)
    w0 = 2.0 * math.pi * freq / sample_rate
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    alpha = sin_w0 / (2.0 * max(q, 1e-3))
    b0 = 1.0 + alpha * a
    b1 = -2.0 * cos_w0
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha / a
    return _Biquad((b0, b1, b2), (a0, a1, a2), channels=channels)


def _design_high_shelf(
    sample_rate: int, freq: float, gain_db: float, channels: int
) -> _Biquad | None:
    if abs(gain_db) < 1e-6:
        return None
    freq = _clamp_frequency(freq, sample_rate)
    a = math.pow(10.0, gain_db / 40.0)
    w0 = 2.0 * math.pi * freq / sample_rate
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    sqrt_a = math.sqrt(a)
    alpha = sin_w0 / 2.0 * math.sqrt(2.0)
    b0 = a * ((a + 1.0) + (a - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha)
    b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0)
    b2 = a * ((a + 1.0) + (a - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha)
    a0 = (a + 1.0) - (a - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha
    a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cos_w0)
    a2 = (a + 1.0) - (a - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha
    return _Biquad((b0, b1, b2), (a0, a1, a2), channels=channels)


@dataclass
class ThreeBandEqInsert:
    """Musician-facing three-band EQ insert.

    Parameters are expressed in decibels and Hertz to stay aligned with the
    project documentation.  The insert keeps per-channel state so it can be
    reused across successive mixer blocks without zipper noise.
    """

    config: EngineConfig
    low_gain_db: float = 0.0
    low_freq: float = 160.0
    mid_gain_db: float = 0.0
    mid_freq: float = 1_200.0
    mid_q: float = 1.0
    high_gain_db: float = 0.0
    high_freq: float = 6_000.0

    def __post_init__(self) -> None:
        channels = self.config.channels
        self._low = _design_low_shelf(
            self.config.sample_rate,
            self.low_freq,
            self.low_gain_db,
            channels,
        )
        self._mid = _design_peak(
            self.config.sample_rate,
            self.mid_freq,
            self.mid_gain_db,
            max(self.mid_q, 0.1),
            channels,
        )
        self._high = _design_high_shelf(
            self.config.sample_rate,
            self.high_freq,
            self.high_gain_db,
            channels,
        )

    def __call__(self, buffer: np.ndarray) -> np.ndarray:
        working = np.array(buffer, copy=True, dtype=np.float32)
        if self._low is not None:
            working = self._low.process(working)
        if self._mid is not None:
            working = self._mid.process(working)
        if self._high is not None:
            working = self._high.process(working)
        return working


@dataclass
class SoftKneeCompressorInsert:
    """Feed-forward dynamics processor for mixer inserts."""

    config: EngineConfig
    threshold_db: float = -18.0
    ratio: float = 3.0
    attack_ms: float = 10.0
    release_ms: float = 120.0
    knee_db: float = 6.0
    makeup_gain_db: float = 3.0

    def __post_init__(self) -> None:
        self._envelope_linear = 0.0
        self._gain_db = 0.0

    def _time_to_coeff(self, time_ms: float) -> float:
        if time_ms <= 0.0:
            return 0.0
        seconds = time_ms / 1_000.0
        return math.exp(-1.0 / (seconds * self.config.sample_rate))

    def __call__(self, buffer: np.ndarray) -> np.ndarray:
        attack_coeff = self._time_to_coeff(self.attack_ms)
        release_coeff = self._time_to_coeff(self.release_ms)
        working = np.array(buffer, copy=True, dtype=np.float32)
        for frame in range(working.shape[0]):
            detector = float(np.max(np.abs(working[frame])))
            if detector > self._envelope_linear:
                coeff = attack_coeff
            else:
                coeff = release_coeff
            self._envelope_linear = self._envelope_linear + (detector - self._envelope_linear) * (1.0 - coeff)

            level_db = _linear_to_db(self._envelope_linear)
            gain_db = self._compute_gain_db(level_db)
            self._gain_db = self._gain_db + (gain_db - self._gain_db) * (1.0 - coeff)
            linear_gain = _db_to_linear(self._gain_db + self.makeup_gain_db)
            working[frame] *= linear_gain
        return working

    def _compute_gain_db(self, level_db: float) -> float:
        threshold = self.threshold_db
        ratio = max(self.ratio, 1.0)
        knee = max(self.knee_db, 0.0)
        if level_db < threshold - knee / 2.0:
            return 0.0
        if knee > 0.0 and level_db <= threshold + knee / 2.0:
            delta = level_db - (threshold - knee / 2.0)
            return (1.0 / ratio - 1.0) * (delta ** 2) / (2.0 * knee)
        compressed = threshold + (level_db - threshold) / ratio
        return compressed - level_db


@dataclass
class StereoFeedbackDelayInsert:
    """Stereo feedback delay tailored for return buses.

    The implementation deliberately favours clarity over extreme DSP accuracy so
    outside engineers can reason about the behaviour when wiring return bus
    presets.  Delay time is stored in milliseconds, feedback is linear, and the
    mix parameter blends the dry input with the delayed tail.
    """

    config: EngineConfig
    delay_ms: float = 380.0
    feedback: float = 0.35
    mix: float = 0.5

    def __post_init__(self) -> None:
        self._delay_samples = max(
            1, int(round(self.delay_ms * self.config.sample_rate / 1_000.0))
        )
        self._buffer = np.zeros(
            (self._delay_samples, self.config.channels), dtype=np.float32
        )
        self._index = 0
        self._feedback = float(np.clip(self.feedback, 0.0, 0.95))
        self._mix = float(np.clip(self.mix, 0.0, 1.0))

    def __call__(self, buffer: np.ndarray) -> np.ndarray:
        if buffer.size == 0:
            return buffer
        working = np.array(buffer, copy=True, dtype=np.float32)
        wet = np.zeros_like(working)
        for frame in range(working.shape[0]):
            delayed = self._buffer[self._index]
            wet[frame] = delayed
            new_sample = working[frame] + delayed * self._feedback
            self._buffer[self._index] = new_sample
            self._index = (self._index + 1) % self._delay_samples
        dry_gain = 1.0 - self._mix
        wet_gain = self._mix
        return working * dry_gain + wet * wet_gain


class _DiffusedDelayNetwork:
    """Helper implementing a lightweight Schroeder-inspired reverb network."""

    def __init__(
        self,
        config: EngineConfig,
        delay_times_ms: Iterable[float],
        feedback: float,
        damping: float,
    ) -> None:
        sample_rate = config.sample_rate
        self._buffers = []
        self._indices = []
        self._filter_state = []
        for delay_ms in delay_times_ms:
            length = max(1, int(round(delay_ms * sample_rate / 1_000.0)))
            self._buffers.append(np.zeros((length, config.channels), dtype=np.float32))
            self._indices.append(0)
            self._filter_state.append(np.zeros(config.channels, dtype=np.float32))
        self._feedback = float(np.clip(feedback, 0.0, 0.95))
        self._damping = float(np.clip(damping, 0.0, 0.99))

    def process(self, excitation: np.ndarray) -> np.ndarray:
        if excitation.size == 0:
            return excitation
        channels = excitation.shape[1]
        output = np.zeros_like(excitation)
        for frame in range(excitation.shape[0]):
            accum = np.zeros(channels, dtype=np.float32)
            for idx, buffer in enumerate(self._buffers):
                pointer = self._indices[idx]
                delayed = buffer[pointer]
                filter_state = self._filter_state[idx]
                # Simple one-pole low-pass inside the feedback loop for damping.
                filter_state = (
                    (1.0 - self._damping) * delayed
                    + self._damping * filter_state
                )
                self._filter_state[idx] = filter_state
                buffer[pointer] = excitation[frame] + filter_state * self._feedback
                self._indices[idx] = (pointer + 1) % buffer.shape[0]
                accum += filter_state
            output[frame] = accum / max(len(self._buffers), 1)
        return output


@dataclass
class PlateReverbInsert:
    """Return-bus reverb using a compact diffused delay network."""

    config: EngineConfig
    pre_delay_ms: float = 20.0
    mix: float = 0.35
    decay: float = 0.75
    damping: float = 0.35

    def __post_init__(self) -> None:
        sample_rate = self.config.sample_rate
        if self.pre_delay_ms > 0.0:
            self._pre_delay_samples = max(
                1, int(round(self.pre_delay_ms * sample_rate / 1_000.0))
            )
            self._pre_delay = np.zeros(
                (self._pre_delay_samples, self.config.channels), dtype=np.float32
            )
            self._pre_index = 0
        else:
            self._pre_delay_samples = 0
            self._pre_delay = None
            self._pre_index = 0
        # Delay spread chosen to stay musical for common tempos while keeping CPU
        # light for prototypes.
        self._network = _DiffusedDelayNetwork(
            self.config,
            delay_times_ms=(43.0, 57.0, 71.0, 89.0),
            feedback=self.decay,
            damping=self.damping,
        )
        self._mix = float(np.clip(self.mix, 0.0, 1.0))

    def __call__(self, buffer: np.ndarray) -> np.ndarray:
        if buffer.size == 0:
            return buffer
        working = np.array(buffer, copy=True, dtype=np.float32)
        if self._pre_delay is None:
            pre_delayed = working
        else:
            pre_delayed = np.zeros_like(working)
            for frame in range(working.shape[0]):
                delayed = self._pre_delay[self._pre_index]
                pre_delayed[frame] = delayed
                self._pre_delay[self._pre_index] = working[frame]
                self._pre_index = (self._pre_index + 1) % self._pre_delay_samples
        wet = self._network.process(pre_delayed)
        dry_gain = 1.0 - self._mix
        wet_gain = self._mix
        return working * dry_gain + wet * wet_gain


__all__ = [
    "PlateReverbInsert",
    "SoftKneeCompressorInsert",
    "StereoFeedbackDelayInsert",
    "ThreeBandEqInsert",
]

