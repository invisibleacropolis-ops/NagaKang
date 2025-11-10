"""Mixer scaffolding covering channels, sends, and return buses.

This module kicks off README §6 by defining the first-pass routing
primitives that future DSP effects and GUI layers can build upon.  The
focus is on explicit, musician-readable configuration: channels expose
faders in decibels, linear pan values, and an insert chain that mirrors
tracker expectations.  Sends target named return buses so auxiliary
effects (reverbs, delays, etc.) can be layered without hard-coding any
particular processing order.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Set

import numpy as np

from .engine import (
    AutomationEvent,
    AutomationTimeline,
    BaseAudioModule,
    EngineConfig,
)


InsertProcessor = Callable[[np.ndarray], np.ndarray]


def _db_to_linear(value_db: float) -> float:
    """Convert a decibel value to a linear gain multiplier."""

    return math.pow(10.0, value_db / 20.0)


@dataclass
class MeterReading:
    """Represents a snapshot of signal level in decibels."""

    peak_db: float
    rms_db: float


def _linear_to_db(value: float) -> float:
    if value <= 0.0:
        return -float("inf")
    return 20.0 * math.log10(value)


@dataclass
class MixerSendConfig:
    """Configuration describing how a channel feeds an auxiliary bus."""

    bus: str
    level_db: float = -float("inf")
    pre_fader: bool = False

    def linear_gain(self) -> float:
        """Return the send level as a linear multiplier."""

        if math.isinf(self.level_db) and self.level_db < 0:
            return 0.0
        return _db_to_linear(self.level_db)


class MixerChannel:
    """Represents a track channel with inserts, pan, fader, and sends."""

    def __init__(
        self,
        name: str,
        *,
        source: BaseAudioModule,
        config: EngineConfig,
        inserts: Iterable[InsertProcessor] | None = None,
        pan: float = 0.0,
        fader_db: float = 0.0,
        muted: bool = False,
        sends: Iterable[MixerSendConfig] | None = None,
        solo: bool = False,
    ) -> None:
        self.name = name
        self._source = source
        self._config = config
        self._inserts = list(inserts or [])
        self._pan = float(np.clip(pan, -1.0, 1.0))
        self._fader_db = fader_db
        self._fader_gain = _db_to_linear(fader_db)
        self._muted = muted
        self._solo = solo
        self._sends: Dict[str, MixerSendConfig] = {send.bus: send for send in sends or []}

    @property
    def pan(self) -> float:
        return self._pan

    def set_pan(self, value: float) -> None:
        """Update the stereo pan (``-1`` = left, ``0`` = centre, ``1`` = right)."""

        self._pan = float(np.clip(value, -1.0, 1.0))

    @property
    def fader_db(self) -> float:
        return self._fader_db

    def set_fader_db(self, value: float) -> None:
        """Update the fader level in decibels."""

        self._fader_db = float(value)
        self._fader_gain = _db_to_linear(self._fader_db)

    @property
    def muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)

    @property
    def solo(self) -> bool:
        return self._solo

    def set_solo(self, solo: bool) -> None:
        self._solo = bool(solo)

    def add_insert(self, processor: InsertProcessor) -> None:
        """Append an insert processor to the channel chain."""

        self._inserts.append(processor)

    def move_insert(self, from_index: int, to_index: int) -> None:
        """Reorder inserts to support drag-and-drop style UI gestures."""

        if not self._inserts:
            raise IndexError("Channel has no inserts to reorder")
        if from_index < 0 or from_index >= len(self._inserts):
            raise IndexError("Insert move source index out of range")
        to_index = max(0, min(int(to_index), len(self._inserts) - 1))
        processor = self._inserts.pop(from_index)
        self._inserts.insert(to_index, processor)

    def set_send(self, config: MixerSendConfig) -> None:
        """Register or update an auxiliary send."""

        self._sends[config.bus] = config

    def set_send_level_db(self, bus: str, level_db: float) -> None:
        """Update the decibel level for an existing send."""

        if bus not in self._sends:
            self._sends[bus] = MixerSendConfig(bus=bus, level_db=level_db)
        else:
            self._sends[bus].level_db = float(level_db)

    def get_send_level_db(self, bus: str) -> float:
        """Return the configured decibel level for *bus* (``-inf`` if missing)."""

        if bus not in self._sends:
            return -float("inf")
        return float(self._sends[bus].level_db)

    def remove_send(self, bus: str) -> None:
        """Remove a configured send if present."""

        self._sends.pop(bus, None)

    def _apply_pan(self, buffer: np.ndarray) -> np.ndarray:
        if self._pan == 0.0 or buffer.shape[1] < 2:
            return buffer
        left_gain = 1.0 - max(0.0, self._pan)
        right_gain = 1.0 + min(0.0, self._pan)
        panned = buffer.copy()
        panned[:, 0] *= left_gain
        panned[:, 1] *= right_gain
        if buffer.shape[1] > 2:
            panned[:, 2:] *= 1.0
        return panned

    def process(self, frames: int) -> tuple[np.ndarray, Dict[str, np.ndarray]]:
        """Process *frames* samples returning the main signal and send taps."""

        block = np.array(self._source.process(frames), copy=True)
        if block.shape[1] != self._config.channels:
            raise ValueError(
                f"Source module '{self._source.name}' produced {block.shape[1]} channels;"
                f" expected {self._config.channels}"
            )

        for processor in self._inserts:
            block = np.array(processor(block), copy=False)
            if block.shape[1] != self._config.channels:
                raise ValueError("Insert processor altered channel count")

        pre_fader = block
        post_pan = self._apply_pan(pre_fader)
        post_fader = post_pan * (0.0 if self._muted else self._fader_gain)

        sends: Dict[str, np.ndarray] = {}
        for bus, config in self._sends.items():
            tap = pre_fader if config.pre_fader else post_fader
            gain = config.linear_gain()
            if gain == 0.0:
                continue
            sends[bus] = tap * gain
        return post_fader, sends


class MixerSubgroup:
    """Processes collections of channels before they reach the master bus."""

    def __init__(
        self,
        name: str,
        *,
        config: EngineConfig,
        inserts: Iterable[InsertProcessor] | None = None,
        fader_db: float = 0.0,
        muted: bool = False,
        solo: bool = False,
    ) -> None:
        self.name = name
        self._config = config
        self._inserts = list(inserts or [])
        self._fader_db = fader_db
        self._fader_gain = _db_to_linear(fader_db)
        self._muted = muted
        self._solo = solo
        self._last_meter = MeterReading(peak_db=-float("inf"), rms_db=-float("inf"))

    def add_insert(self, processor: InsertProcessor) -> None:
        self._inserts.append(processor)

    def set_fader_db(self, value: float) -> None:
        self._fader_db = float(value)
        self._fader_gain = _db_to_linear(self._fader_db)

    @property
    def fader_db(self) -> float:
        return self._fader_db

    @property
    def muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)

    @property
    def solo(self) -> bool:
        return self._solo

    def set_solo(self, solo: bool) -> None:
        self._solo = bool(solo)

    def process(self, buffer: np.ndarray) -> np.ndarray:
        working = np.array(buffer, copy=True, dtype=np.float32)
        for processor in self._inserts:
            working = np.array(processor(working), copy=False)
            if working.shape[1] != self._config.channels:
                raise ValueError("Subgroup insert altered channel count")
        if self._muted:
            working.fill(0.0)
        else:
            working *= self._fader_gain
        peak = float(np.max(np.abs(working))) if working.size else 0.0
        rms = float(np.sqrt(np.mean(np.square(working)))) if working.size else 0.0
        self._last_meter = MeterReading(
            peak_db=_linear_to_db(peak),
            rms_db=_linear_to_db(rms),
        )
        return working

    @property
    def last_meter(self) -> MeterReading:
        return self._last_meter


class MixerReturnBus:
    """Aggregates auxiliary sends and optionally processes the combined signal."""

    def __init__(
        self,
        name: str,
        *,
        processor: Optional[Callable[[np.ndarray], np.ndarray]] = None,
        level_db: float = 0.0,
    ) -> None:
        self.name = name
        self._processor = processor
        self._level_db = float(level_db)
        self._gain = _db_to_linear(self._level_db)

    def set_level_db(self, value: float) -> None:
        self._level_db = float(value)
        self._gain = _db_to_linear(self._level_db)

    @property
    def level_db(self) -> float:  # pragma: no cover - simple accessor
        return self._level_db

    def process(self, buffer: np.ndarray) -> np.ndarray:
        working = buffer
        if self._processor is not None:
            working = np.array(self._processor(buffer), copy=False)
        return working * self._gain


class MixerGraph:
    """Block-based mixer that sums channels, sends, and return buses."""

    def __init__(
        self,
        config: EngineConfig,
        *,
        master_fader_db: float = 0.0,
    ) -> None:
        self.config = config
        self._channels: MutableMapping[str, MixerChannel] = {}
        self._subgroups: MutableMapping[str, MixerSubgroup] = {}
        self._channel_groups: Dict[str, str] = {}
        self._subgroup_routes: Dict[str, str] = {}
        self._returns: MutableMapping[str, MixerReturnBus] = {}
        self._master_fader_db = master_fader_db
        self._master_gain = _db_to_linear(master_fader_db)
        self._last_subgroup_meters: Dict[str, MeterReading] = {}
        self._timeline = AutomationTimeline()
        self._processed_frames = 0
        self._automation_events: List[AutomationEvent] = []

    def add_channel(self, channel: MixerChannel) -> None:
        if channel.name in self._channels:
            raise ValueError(f"Channel '{channel.name}' already registered")
        self._channels[channel.name] = channel

    def add_subgroup(self, subgroup: MixerSubgroup) -> None:
        if subgroup.name in self._subgroups:
            raise ValueError(f"Subgroup '{subgroup.name}' already registered")
        self._subgroups[subgroup.name] = subgroup

    def add_return_bus(self, bus: MixerReturnBus) -> None:
        if bus.name in self._returns:
            raise ValueError(f"Return bus '{bus.name}' already registered")
        self._returns[bus.name] = bus

    def assign_channel_to_group(self, channel_name: str, group_name: str) -> None:
        if channel_name not in self._channels:
            raise KeyError(f"Unknown channel '{channel_name}'")
        if group_name not in self._subgroups:
            raise KeyError(f"Unknown subgroup '{group_name}'")
        self._channel_groups[channel_name] = group_name

    def clear_channel_group(self, channel_name: str) -> None:
        self._channel_groups.pop(channel_name, None)

    def assign_subgroup_to_group(self, subgroup_name: str, parent_name: str) -> None:
        if subgroup_name not in self._subgroups:
            raise KeyError(f"Unknown subgroup '{subgroup_name}'")
        if parent_name not in self._subgroups:
            raise KeyError(f"Unknown subgroup '{parent_name}'")
        if subgroup_name == parent_name:
            raise ValueError("Subgroup cannot target itself")
        self._subgroup_routes[subgroup_name] = parent_name

    def clear_subgroup_group(self, subgroup_name: str) -> None:
        self._subgroup_routes.pop(subgroup_name, None)

    def set_master_fader_db(self, value: float) -> None:
        self._master_fader_db = float(value)
        self._master_gain = _db_to_linear(self._master_fader_db)

    @property
    def channels(self) -> Mapping[str, MixerChannel]:  # pragma: no cover - trivial view
        return dict(self._channels)

    @property
    def channel_groups(self) -> Mapping[str, str]:  # pragma: no cover - trivial view
        return dict(self._channel_groups)

    @property
    def subgroups(self) -> Mapping[str, MixerSubgroup]:  # pragma: no cover - trivial view
        return dict(self._subgroups)

    @property
    def returns(self) -> Mapping[str, MixerReturnBus]:  # pragma: no cover - trivial view
        return dict(self._returns)

    @property
    def subgroup_meters(self) -> Mapping[str, MeterReading]:
        return dict(self._last_subgroup_meters)

    @property
    def automation_events(self) -> List[AutomationEvent]:  # pragma: no cover - view helper
        return list(self._automation_events)

    def _subgroup_children(self) -> Dict[str, Set[str]]:
        children: Dict[str, Set[str]] = {name: set() for name in self._subgroups}
        for child, parent in self._subgroup_routes.items():
            if child not in children:
                raise KeyError(f"Unknown subgroup '{child}' in routing table")
            if parent not in children:
                raise KeyError(f"Unknown subgroup '{parent}' in routing table")
            children[parent].add(child)
        return children

    def _ordered_subgroups(self) -> Iterable[str]:
        children = self._subgroup_children()
        visited: Set[str] = set()
        stack: Set[str] = set()
        order: list[str] = []

        def dfs(name: str) -> None:
            if name in visited:
                return
            if name in stack:
                raise ValueError("Subgroup routing contains a cycle")
            stack.add(name)
            for child in children[name]:
                dfs(child)
            stack.remove(name)
            visited.add(name)
            order.append(name)

        roots = [name for name in self._subgroups if name not in self._subgroup_routes]
        for root in roots:
            dfs(root)
        for name in self._subgroups:
            dfs(name)
        return order

    def process_block(self, frames: int) -> np.ndarray:
        block_start_time = self._processed_frames / float(self.config.sample_rate)
        for event in self._timeline.pop_events_up_to(block_start_time):
            self._apply_automation_event(event)

        master = np.zeros((frames, self.config.channels), dtype=np.float32)
        send_sums: Dict[str, np.ndarray] = {
            name: np.zeros((frames, self.config.channels), dtype=np.float32)
            for name in self._returns
        }
        group_sums: Dict[str, np.ndarray] = {
            name: np.zeros((frames, self.config.channels), dtype=np.float32)
            for name in self._subgroups
        }

        solo_channels: Set[str] = {
            name for name, channel in self._channels.items() if channel.solo
        }
        solo_groups: Set[str] = {
            name for name, subgroup in self._subgroups.items() if subgroup.solo
        }
        if solo_groups:
            for channel_name, group_name in self._channel_groups.items():
                current = group_name
                while current is not None:
                    if current in solo_groups:
                        solo_channels.add(channel_name)
                        break
                    current = self._subgroup_routes.get(current)
        if solo_channels:
            active_channels = solo_channels
        else:
            active_channels = set(self._channels.keys())

        for name, channel in self._channels.items():
            if name not in active_channels:
                continue
            main, sends = channel.process(frames)
            group_name = self._channel_groups.get(name)
            if group_name is not None:
                if group_name not in group_sums:
                    raise KeyError(
                        f"Channel '{name}' targets missing subgroup '{group_name}'"
                    )
                group_sums[group_name] += main
            else:
                master += main
            for bus, buffer in sends.items():
                if bus not in send_sums:
                    raise KeyError(
                        f"Channel '{name}' targets missing return bus '{bus}'"
                    )
                send_sums[bus] += buffer

        meters: Dict[str, MeterReading] = {}
        for name in self._ordered_subgroups():
            subgroup = self._subgroups[name]
            processed = subgroup.process(group_sums[name])
            meters[name] = subgroup.last_meter
            parent = self._subgroup_routes.get(name)
            if parent is not None:
                group_sums[parent] += processed
            else:
                master += processed

        for name, bus in self._returns.items():
            processed = bus.process(send_sums[name])
            master += processed

        self._last_subgroup_meters = meters
        self._processed_frames += frames
        return master * self._master_gain

    def render(self, duration_seconds: float) -> np.ndarray:
        self._processed_frames = 0
        total_frames = int(round(duration_seconds * self.config.sample_rate))
        output = np.zeros((total_frames, self.config.channels), dtype=np.float32)
        for frame_start in range(0, total_frames, self.config.block_size):
            block_frames = min(self.config.block_size, total_frames - frame_start)
            block = self.process_block(block_frames)
            output[frame_start : frame_start + block_frames, :] = block
        return output

    # ------------------------------------------------------------------
    # Automation helpers
    # ------------------------------------------------------------------
    def reset_automation_state(self) -> None:
        """Clear processed time so subsequent renders replay automation."""

        self._processed_frames = 0

    def schedule_parameter_change(
        self,
        module: str,
        parameter: str,
        *,
        value: float | None,
        time_seconds: float,
        source: str = "",
    ) -> None:
        event = AutomationEvent(
            time_seconds=float(time_seconds),
            module=module,
            parameter=parameter,
            value=value,
            source=source,
        )
        self._automation_events.append(event)
        self._timeline.schedule(event)

    def _apply_automation_event(self, event: AutomationEvent) -> None:
        module = event.module
        if not module.startswith("mixer:"):
            return
        parts = module.split(":", 2)
        if len(parts) < 3:
            return
        scope = parts[1]
        target = parts[2]
        value = event.value
        if scope == "channel":
            channel = self._channels.get(target)
            if channel is None:
                return
            parameter = event.parameter
            if parameter == "fader_db" and value is not None:
                channel.set_fader_db(float(value))
            elif parameter == "pan" and value is not None:
                channel.set_pan(float(value))
            elif parameter == "mute":
                channel.set_muted(bool(value and float(value) >= 0.5))
            elif parameter.startswith("send:"):
                _, _, bus = parameter.partition(":")
                level = -float("inf") if value is None else float(value)
                channel.set_send_level_db(bus, level)
        elif scope == "subgroup":
            subgroup = self._subgroups.get(target)
            if subgroup is None:
                return
            if event.parameter == "fader_db" and value is not None:
                subgroup.set_fader_db(float(value))
            elif event.parameter == "mute":
                subgroup.set_muted(bool(value and float(value) >= 0.5))


__all__ = [
    "InsertProcessor",
    "MeterReading",
    "MixerChannel",
    "MixerGraph",
    "MixerSubgroup",
    "MixerReturnBus",
    "MixerSendConfig",
]

