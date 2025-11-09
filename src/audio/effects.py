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


__all__ = ["SoftKneeCompressorInsert", "ThreeBandEqInsert"]

