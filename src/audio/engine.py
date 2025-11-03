"""Core audio engine structures tuned for musician-first prototyping."""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
from typing import Dict, Iterable, Iterator, List, MutableMapping, Optional

import numpy as np


@dataclass
class EngineConfig:
    """Global audio configuration shared across modules."""

    sample_rate: int = 48_000
    block_size: int = 512
    channels: int = 2


@dataclass
class ParameterSpec:
    """Describes a parameter in musician-facing language."""

    name: str
    display_name: str
    default: float | None
    minimum: float
    maximum: float
    unit: str = ""
    description: str = ""
    musical_context: Optional[str] = None
    allow_none: bool = False

    def clamp(self, value: float | None) -> float | None:
        """Ensure *value* stays within the declared bounds."""

        if value is None:
            if not self.allow_none:
                raise ValueError(f"Parameter '{self.name}' does not accept silence/null values")
            return None
        if value < self.minimum:
            return self.minimum
        if value > self.maximum:
            return self.maximum
        return value


@dataclass(order=True)
class AutomationEvent:
    """A scheduled parameter change expressed in absolute time."""

    time_seconds: float
    module: str = field(compare=False)
    parameter: str = field(compare=False)
    value: float | None = field(compare=False)
    source: str = field(default="", compare=False)


@dataclass
class TempoMap:
    """Simple tempo map for converting beats/bars to seconds."""

    tempo_bpm: float = 120.0
    beats_per_bar: int = 4

    def beats_to_seconds(self, beats: float) -> float:
        return (60.0 / self.tempo_bpm) * beats

    def bars_to_seconds(self, bars: float) -> float:
        return self.beats_to_seconds(bars * self.beats_per_bar)


class AutomationTimeline:
    """Priority queue of automation events with musician-friendly helpers."""

    def __init__(self) -> None:
        self._events: List[AutomationEvent] = []

    def schedule(self, event: AutomationEvent) -> None:
        heapq.heappush(self._events, event)

    def schedule_in_beats(
        self,
        *,
        module: str,
        parameter: str,
        beats: float,
        value: float | None,
        tempo: TempoMap,
        source: str = "",
    ) -> None:
        seconds = tempo.beats_to_seconds(beats)
        self.schedule(
            AutomationEvent(
                time_seconds=seconds,
                module=module,
                parameter=parameter,
                value=value,
                source=source or f"beats@{beats}",
            )
        )

    def pop_events_up_to(self, time_seconds: float) -> Iterator[AutomationEvent]:
        while self._events and self._events[0].time_seconds <= time_seconds + 1e-9:
            yield heapq.heappop(self._events)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._events)


class BaseAudioModule:
    """Utility base class that stores musician-centric parameter metadata."""

    def __init__(self, name: str, config: EngineConfig, parameters: Iterable[ParameterSpec]):
        self.name = name
        self.config = config
        self._specs: Dict[str, ParameterSpec] = {spec.name: spec for spec in parameters}
        self._values: Dict[str, float | None] = {spec.name: spec.default for spec in parameters}

    def set_parameter(self, name: str, value: float | None) -> None:
        if name not in self._specs:
            raise KeyError(f"Unknown parameter '{name}' for module {self.name}")
        spec = self._specs[name]
        self._values[name] = spec.clamp(value)

    def get_parameter(self, name: str) -> float | None:
        if name not in self._values:
            raise KeyError(f"Unknown parameter '{name}' for module {self.name}")
        return self._values[name]

    def describe_parameters(self) -> List[ParameterSpec]:
        return list(self._specs.values())

    def process(self, frames: int) -> np.ndarray:
        raise NotImplementedError


class OfflineAudioEngine:
    """Block-based offline renderer driven by musician-friendly automation."""

    def __init__(
        self,
        config: EngineConfig,
        *,
        tempo: Optional[TempoMap] = None,
        timeline: Optional[AutomationTimeline] = None,
    ) -> None:
        self.config = config
        self.tempo = tempo or TempoMap()
        self.timeline = timeline or AutomationTimeline()
        self._modules: MutableMapping[str, BaseAudioModule] = {}
        self._output_module: Optional[str] = None

    def add_module(self, module: BaseAudioModule, *, as_output: bool = False) -> None:
        if module.name in self._modules:
            raise ValueError(f"Module named '{module.name}' already registered")
        self._modules[module.name] = module
        if as_output or self._output_module is None:
            self._output_module = module.name

    def set_output(self, module_name: str) -> None:
        if module_name not in self._modules:
            raise KeyError(f"Unknown module '{module_name}'")
        self._output_module = module_name

    def schedule_parameter_change(
        self,
        module: str,
        parameter: str,
        *,
        value: float | None,
        time_seconds: Optional[float] = None,
        beats: Optional[float] = None,
        source: str = "",
    ) -> None:
        if time_seconds is None and beats is None:
            raise ValueError("Either time_seconds or beats must be provided")
        if module not in self._modules:
            raise KeyError(f"Unknown module '{module}'")
        if beats is not None:
            self.timeline.schedule_in_beats(
                module=module,
                parameter=parameter,
                beats=beats,
                value=value,
                tempo=self.tempo,
                source=source,
            )
            return
        assert time_seconds is not None  # for type-checkers
        self.timeline.schedule(
            AutomationEvent(
                time_seconds=time_seconds,
                module=module,
                parameter=parameter,
                value=value,
                source=source,
            )
        )

    def render(self, duration_seconds: float) -> np.ndarray:
        if self._output_module is None:
            raise RuntimeError("No output module configured")
        total_frames = int(round(duration_seconds * self.config.sample_rate))
        output = np.zeros((total_frames, self.config.channels), dtype=np.float32)
        module = self._modules[self._output_module]

        for frame_start in range(0, total_frames, self.config.block_size):
            block_frames = min(self.config.block_size, total_frames - frame_start)
            block_time = frame_start / self.config.sample_rate
            for event in self.timeline.pop_events_up_to(block_time):
                target = self._modules.get(event.module)
                if target is None:
                    continue
                try:
                    target.set_parameter(event.parameter, event.value)
                except KeyError as exc:  # pragma: no cover - defensive guard
                    raise KeyError(
                        f"Module '{event.module}' missing parameter '{event.parameter}'"
                    ) from exc
            rendered = module.process(block_frames)
            if rendered.shape[1] != self.config.channels:
                raise ValueError(
                    f"Module {module.name} produced {rendered.shape[1]} channels;"
                    f" expected {self.config.channels}"
                )
            output[frame_start : frame_start + block_frames, :] = rendered
        return output


__all__ = [
    "AutomationEvent",
    "AutomationTimeline",
    "BaseAudioModule",
    "EngineConfig",
    "OfflineAudioEngine",
    "ParameterSpec",
    "TempoMap",
]
