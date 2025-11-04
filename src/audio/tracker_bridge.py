"""Helpers that translate tracker patterns into offline engine renders."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping

import numpy as np

from domain.models import AutomationPoint, InstrumentDefinition, Pattern, PatternStep

from .engine import EngineConfig, OfflineAudioEngine, TempoMap
from .metrics import integrated_lufs, rms_dbfs
from .modules import (
    AmplitudeEnvelope,
    ClipSampler,
    ClipSampleLayer,
    OnePoleLowPass,
    SineOscillator,
)


@dataclass
class PatternPlayback:
    """Rendered audio plus metadata useful for tracker previews."""

    buffer: np.ndarray
    duration_seconds: float
    beat_frames: List[int]
    module_parameters: Dict[str, Dict[str, float | None]]
    automation_log: List[dict[str, object]]


class PatternPerformanceBridge:
    """Bridge domain patterns into the musician-facing offline engine."""

    def __init__(
        self,
        config: EngineConfig,
        tempo: TempoMap,
        *,
        sample_library: Mapping[str, np.ndarray] | None = None,
    ) -> None:
        self.config = config
        self.tempo = tempo
        self.sample_library = sample_library or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def render_pattern(
        self,
        pattern: Pattern,
        instrument: InstrumentDefinition,
    ) -> PatternPlayback:
        engine = OfflineAudioEngine(self.config, tempo=self.tempo)
        modules = self._instantiate_instrument(engine, instrument)

        automation_log: List[dict[str, object]] = []
        self._schedule_steps(engine, pattern, instrument, modules, automation_log)
        self._schedule_automation_lanes(engine, pattern, automation_log)

        duration_seconds = self.tempo.beats_to_seconds(pattern.duration_beats)
        buffer = engine.render(duration_seconds)

        beat_frames = self._beat_frames(pattern.duration_beats)
        module_parameters = {
            name: {spec.name: module.get_parameter(spec.name) for spec in module.describe_parameters()}
            for name, module in modules.items()
        }

        return PatternPlayback(
            buffer=buffer,
            duration_seconds=duration_seconds,
            beat_frames=beat_frames,
            module_parameters=module_parameters,
            automation_log=automation_log,
        )

    def loudness_trends(
        self,
        playback: PatternPlayback,
        *,
        beats_per_bucket: float = 1.0,
    ) -> List[dict[str, object]]:
        """Return per-beat loudness snapshots suited for tracker dashboards."""

        if beats_per_bucket <= 0.0:
            raise ValueError("beats_per_bucket must be positive")

        beat_span_seconds = self.tempo.beats_to_seconds(beats_per_bucket)
        frames_per_bucket = max(1, int(round(beat_span_seconds * self.config.sample_rate)))
        buffer = playback.buffer
        total_frames = buffer.shape[0]
        summaries: List[dict[str, object]] = []
        for bucket_index, start in enumerate(range(0, total_frames, frames_per_bucket)):
            end = min(total_frames, start + frames_per_bucket)
            segment = buffer[start:end]
            if segment.size == 0:
                continue
            rms_values = rms_dbfs(segment)
            lufs_value = integrated_lufs(segment, sample_rate=self.config.sample_rate)
            summaries.append(
                {
                    "start_beat": bucket_index * beats_per_bucket,
                    "end_beat": (bucket_index + 1) * beats_per_bucket,
                    "rms_left_dbfs": float(rms_values[0]),
                    "rms_right_dbfs": float(rms_values[-1]),
                    "integrated_lufs": float(lufs_value),
                }
            )
        return summaries

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _instantiate_instrument(
        self,
        engine: OfflineAudioEngine,
        instrument: InstrumentDefinition,
    ) -> MutableMapping[str, SineOscillator | ClipSampler | AmplitudeEnvelope | OnePoleLowPass]:
        modules: MutableMapping[str, SineOscillator | ClipSampler | AmplitudeEnvelope | OnePoleLowPass] = {}

        for module_def in instrument.modules:
            raw_type = module_def.type
            module_type, _, type_suffix = raw_type.partition(":")
            module_type = module_type.lower()
            if module_type in {"sine", "sine_oscillator", "oscillator"}:
                module = SineOscillator(module_def.id, self.config)
                if "frequency_hz" in module_def.parameters:
                    module.set_parameter(
                        "frequency_hz",
                        float(module_def.parameters["frequency_hz"]),
                    )
                if "amplitude" in module_def.parameters:
                    module.set_parameter(
                        "amplitude",
                        float(module_def.parameters["amplitude"]),
                    )
            elif module_type in {"clip_sampler", "sampler"}:
                sample_key: str | None = None
                if type_suffix:
                    sample_key = type_suffix
                elif "sample_name" in module_def.parameters:
                    sample_key = str(module_def.parameters["sample_name"])
                layers_param = module_def.parameters.get("layers", [])
                layer_objects: list[ClipSampleLayer] = []
                if isinstance(layers_param, list):
                    for layer in layers_param:
                        if not isinstance(layer, Mapping):
                            continue
                        layer_name = str(layer.get("sample_name", sample_key or module_def.id))
                        if layer_name not in self.sample_library:
                            raise KeyError(f"Sample '{layer_name}' not found in library")
                        layer_buffer = np.asarray(self.sample_library[layer_name], dtype=np.float32)
                        layer_objects.append(
                            ClipSampleLayer(
                                sample=layer_buffer,
                                min_velocity=int(layer.get("min_velocity", 0)),
                                max_velocity=int(layer.get("max_velocity", 127)),
                                amplitude_scale=float(layer.get("amplitude_scale", 1.0)),
                                start_offset_percent=float(layer.get("start_offset_percent", 0.0)),
                            )
                        )
                sample: np.ndarray | None = None
                if sample_key is None and not layer_objects:
                    sample_key = module_def.id
                if sample_key is not None:
                    if sample_key not in self.sample_library and not layer_objects:
                        raise KeyError(f"Sample '{sample_key}' not found in library")
                    if sample_key in self.sample_library:
                        sample = np.asarray(self.sample_library[sample_key], dtype=np.float32)
                module = ClipSampler(
                    module_def.id,
                    self.config,
                    sample=sample,
                    layers=layer_objects,
                    root_midi_note=int(module_def.parameters.get("root_midi_note", 60)),
                    amplitude=float(module_def.parameters.get("amplitude", 1.0)),
                    start_percent=float(module_def.parameters.get("start_percent", 0.0)),
                    length_percent=float(module_def.parameters.get("length_percent", 1.0)),
                    playback_rate=float(module_def.parameters.get("playback_rate", 1.0)),
                    loop=bool(module_def.parameters.get("loop", False)),
                )
            elif module_type in {"amplitude_envelope", "envelope"}:
                if not module_def.inputs:
                    raise ValueError("Envelope module requires an input reference")
                source_id = module_def.inputs[0]
                if source_id not in modules:
                    raise KeyError(f"Envelope references unknown module '{source_id}'")
                module = AmplitudeEnvelope(
                    module_def.id,
                    self.config,
                    source=modules[source_id],
                    attack_ms=float(module_def.parameters.get("attack_ms", 10.0)),
                    release_ms=float(module_def.parameters.get("release_ms", 120.0)),
                )
            elif module_type in {"one_pole_low_pass", "low_pass", "lp"}:
                if not module_def.inputs:
                    raise ValueError("Low-pass filter requires an input reference")
                source_id = module_def.inputs[0]
                if source_id not in modules:
                    raise KeyError(f"Low-pass filter references unknown module '{source_id}'")
                module = OnePoleLowPass(
                    module_def.id,
                    self.config,
                    source=modules[source_id],
                    cutoff_hz=float(module_def.parameters.get("cutoff_hz", 4_000.0)),
                    mix=float(module_def.parameters.get("mix", 1.0)),
                )
            else:
                raise ValueError(f"Unsupported module type '{module_def.type}'")

            modules[module_def.id] = module
            engine.add_module(module, as_output=module_def is instrument.modules[-1])

        return modules

    def _schedule_steps(
        self,
        engine: OfflineAudioEngine,
        pattern: Pattern,
        instrument: InstrumentDefinition,
        modules: Mapping[str, SineOscillator | ClipSampler | AmplitudeEnvelope | OnePoleLowPass],
        automation_log: List[dict[str, object]],
    ) -> None:
        step_duration_beats = 1.0 / 4.0
        envelope_modules = [mid for mid, mod in modules.items() if isinstance(mod, AmplitudeEnvelope)]
        sampler_modules = [mid for mid, mod in modules.items() if isinstance(mod, ClipSampler)]

        for index, step in enumerate(self._iter_steps(pattern)):
            if step.note is None or step.instrument_id not in {None, instrument.id}:
                continue
            start_beat = index * step_duration_beats
            length_beats = float(step.step_effects.get("length_beats", step_duration_beats))
            end_beat = start_beat + max(length_beats, step_duration_beats / 2.0)
            velocity = step.velocity if step.velocity is not None else 100
            gate_value = velocity / 127.0
            sampler_velocity = max(1, min(127, velocity))

            for module_id in envelope_modules:
                engine.schedule_parameter_change(
                    module_id,
                    "gate",
                    beats=start_beat,
                    value=gate_value,
                    source=f"pattern_step_{index}_on",
                )
                automation_log.append(
                    {
                        "module": module_id,
                        "parameter": "gate",
                        "beats": start_beat,
                        "value": gate_value,
                    }
                )
                engine.schedule_parameter_change(
                    module_id,
                    "gate",
                    beats=end_beat,
                    value=0.0,
                    source=f"pattern_step_{index}_off",
                )
                automation_log.append(
                    {
                        "module": module_id,
                        "parameter": "gate",
                        "beats": end_beat,
                        "value": 0.0,
                    }
                )

            for module_id in sampler_modules:
                transpose = self._transpose_for_note(
                    modules[module_id],
                    step.note,
                )
                engine.schedule_parameter_change(
                    module_id,
                    "velocity",
                    beats=start_beat,
                    value=float(sampler_velocity),
                    source=f"pattern_step_{index}_velocity",
                )
                automation_log.append(
                    {
                        "module": module_id,
                        "parameter": "velocity",
                        "beats": start_beat,
                        "value": float(sampler_velocity),
                    }
                )
                engine.schedule_parameter_change(
                    module_id,
                    "transpose_semitones",
                    beats=start_beat,
                    value=transpose,
                    source=f"pattern_step_{index}_transpose",
                )
                automation_log.append(
                    {
                        "module": module_id,
                        "parameter": "transpose_semitones",
                        "beats": start_beat,
                        "value": transpose,
                    }
                )
                engine.schedule_parameter_change(
                    module_id,
                    "retrigger",
                    beats=start_beat,
                    value=1.0,
                    source=f"pattern_step_{index}_trigger",
                )
                automation_log.append(
                    {
                        "module": module_id,
                        "parameter": "retrigger",
                        "beats": start_beat,
                        "value": 1.0,
                    }
                )

    def _schedule_automation_lanes(
        self,
        engine: OfflineAudioEngine,
        pattern: Pattern,
        automation_log: List[dict[str, object]],
    ) -> None:
        for lane, points in pattern.automation.items():
            if "." not in lane:
                continue
            module, parameter = lane.split(".", 1)
            for point in points:
                if not isinstance(point, AutomationPoint):
                    continue
                engine.schedule_parameter_change(
                    module,
                    parameter,
                    beats=point.position_beats,
                    value=point.value,
                    source="pattern_automation",
                )
                automation_log.append(
                    {
                        "module": module,
                        "parameter": parameter,
                        "beats": point.position_beats,
                        "value": point.value,
                    }
                )

    def _beat_frames(self, duration_beats: float) -> List[int]:
        total_beats = int(math.ceil(duration_beats))
        frames_per_beat = int(round(self.tempo.beats_to_seconds(1.0) * self.config.sample_rate))
        return [min(idx * frames_per_beat, int(duration_beats * frames_per_beat)) for idx in range(total_beats)]

    def _iter_steps(self, pattern: Pattern) -> Iterable[PatternStep]:
        steps: List[PatternStep] = list(pattern.steps)
        missing = max(0, pattern.length_steps - len(steps))
        steps.extend(PatternStep() for _ in range(missing))
        return steps

    def _transpose_for_note(
        self,
        module: SineOscillator | ClipSampler | AmplitudeEnvelope | OnePoleLowPass,
        note: int,
    ) -> float:
        if not isinstance(module, ClipSampler):
            return 0.0
        root = getattr(module, "_root_midi_note", 60)
        return float(note - root)


__all__ = ["PatternPerformanceBridge", "PatternPlayback"]

