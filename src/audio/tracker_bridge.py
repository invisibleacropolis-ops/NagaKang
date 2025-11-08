"""Helpers that translate tracker patterns into offline engine renders."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, MutableMapping

import numpy as np

from domain.models import AutomationPoint, InstrumentDefinition, Pattern, PatternStep

from .engine import EngineConfig, OfflineAudioEngine, ParameterSpec, TempoMap
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
        self._schedule_automation_lanes(engine, pattern, modules, automation_log)

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

    def tracker_loudness_rows(
        self,
        playback: PatternPlayback,
        *,
        beats_per_bucket: float = 1.0,
    ) -> List[dict[str, object]]:
        """Format loudness summaries for tracker-facing widgets."""

        summaries = self.loudness_trends(playback, beats_per_bucket=beats_per_bucket)
        rows: List[dict[str, object]] = []
        for summary in summaries:
            start = float(summary["start_beat"])
            end = float(summary["end_beat"])
            rms_left = float(summary["rms_left_dbfs"])
            rms_right = float(summary["rms_right_dbfs"])
            lufs_value = float(summary["integrated_lufs"])
            average_rms = (rms_left + rms_right) / 2.0
            if average_rms >= -10.0:
                grade = "bold"
            elif average_rms >= -18.0:
                grade = "balanced"
            else:
                grade = "soft"
            rows.append(
                {
                    "label": f"Beats {start:.1f}–{end:.1f}",
                    "start_beat": start,
                    "end_beat": end,
                    "average_rms_dbfs": average_rms,
                    "rms_text": f"{rms_left:.1f}/{rms_right:.1f} dBFS",
                    "lufs_text": f"{lufs_value:.1f} LUFS",
                    "dynamic_grade": grade,
                }
            )
        return rows

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
                crossfade_param = module_def.parameters.get("velocity_crossfade_width")
                if crossfade_param is not None:
                    module.set_parameter("velocity_crossfade_width", float(crossfade_param))
                else:
                    family_raw = module_def.parameters.get("instrument_family")
                    default_crossfade = self._default_crossfade_width(
                        str(family_raw) if family_raw is not None else None
                    )
                    if default_crossfade is not None:
                        module.set_parameter("velocity_crossfade_width", default_crossfade)
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

    def _default_crossfade_width(self, family: str | None) -> float | None:
        if not family:
            return None
        family = family.strip().lower()
        if not family:
            return None
        if family in {"string", "strings", "pad", "pads", "string_section"}:
            return 12.0
        if family in {"keys", "keyboard", "ep", "organ"}:
            return 8.0
        if family in {"pluck", "plucked", "guitar", "strum"}:
            return 6.0
        return None

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
        modules: Mapping[str, SineOscillator | ClipSampler | AmplitudeEnvelope | OnePoleLowPass],
        automation_log: List[dict[str, object]],
    ) -> None:
        pending: dict[tuple[str, str, float], list[dict[str, object]]] = {}
        last_values: dict[tuple[str, str], float | None] = {}
        for lane_index, (lane, points) in enumerate(pattern.automation.items()):
            module_name, parameter_name, metadata = self._parse_lane_metadata(lane)
            if module_name is None or parameter_name is None:
                continue
            if module_name not in modules:
                raise KeyError(f"Automation lane references unknown module '{module_name}'")
            module = modules[module_name]
            spec = self._resolve_parameter_spec(module, parameter_name)
            if spec is None:
                raise KeyError(
                    f"Automation lane '{lane}' references unknown parameter '{parameter_name}'"
                )
            value_mapper = self._automation_value_mapper(spec, metadata)
            for point in points:
                if not isinstance(point, AutomationPoint):
                    continue
                resolved_value = value_mapper(point.value)
                key = (module_name, parameter_name, float(point.position_beats))
                bucket = pending.setdefault(key, [])
                bucket.append(
                    {
                        "module": module_name,
                        "parameter": parameter_name,
                        "beats": float(point.position_beats),
                        "value": resolved_value,
                        "source_value": point.value,
                        "lane_metadata": metadata,
                        "lane_name": lane,
                        "lane_index": lane_index,
                    }
                )

        for (module_name, parameter_name, beat), events in sorted(
            pending.items(), key=lambda item: (item[0][2], item[0][0], item[0][1])
        ):
            values = [event["value"] for event in events]
            has_none = any(value is None for value in values)
            numeric_values = [float(value) for value in values if value is not None]
            if has_none and not numeric_values:
                aggregated_value: float | None = None
            elif has_none:
                aggregated_value = None
            elif not numeric_values:
                aggregated_value = None
            else:
                aggregated_value = sum(numeric_values) / len(numeric_values)

            key = (module_name, parameter_name)
            if key not in last_values:
                try:
                    last_values[key] = modules[module_name].get_parameter(parameter_name)  # type: ignore[arg-type]
                except KeyError:
                    last_values[key] = None
            previous_value = last_values.get(key)

            smoothing_beats_candidates = [
                self._metadata_smoothing_beats(event.get("lane_metadata", {}))
                for event in events
            ]
            smoothing_beats = max(smoothing_beats_candidates) if smoothing_beats_candidates else 0.0
            smoothing_applied = False
            smoothing_info: dict[str, object] | None = None

            if (
                smoothing_beats > 0.0
                and aggregated_value is not None
                and previous_value is not None
            ):
                start_beat = max(0.0, beat - smoothing_beats)
                window_beats = max(0.0, beat - start_beat)
                if window_beats > 0.0:
                    window_seconds = self.tempo.beats_to_seconds(window_beats)
                    segments = max(
                        3,
                        int(
                            math.ceil(
                                window_seconds
                                * self.config.sample_rate
                                / max(self.config.block_size, 1)
                            )
                        )
                        + 1,
                    )
                    step_beats = window_beats / (segments - 1)
                    for idx in range(segments):
                        ratio = idx / (segments - 1)
                        event_beat = start_beat + step_beats * idx
                        value = previous_value + (aggregated_value - previous_value) * ratio
                        source = "pattern_automation" if idx == segments - 1 else "pattern_automation_smooth"
                        engine.schedule_parameter_change(
                            module_name,
                            parameter_name,
                            beats=event_beat,
                            value=value,
                            source=source,
                        )
                    smoothing_applied = True
                    smoothing_info = {
                        "window_beats": window_beats,
                        "window_seconds": window_seconds,
                        "segments": segments,
                        "previous_value": previous_value,
                        "strategy": "linear_ramp",
                    }
            if not smoothing_applied:
                engine.schedule_parameter_change(
                    module_name,
                    parameter_name,
                    beats=beat,
                    value=aggregated_value,
                    source="pattern_automation",
                )
                if smoothing_beats > 0.0:
                    smoothing_info = {
                        "window_beats": min(smoothing_beats, beat if beat > 0 else smoothing_beats),
                        "window_seconds": self.tempo.beats_to_seconds(
                            min(smoothing_beats, beat if beat > 0 else smoothing_beats)
                        ),
                        "previous_value": previous_value,
                        "strategy": "none",
                    }

            last_values[key] = aggregated_value

            events.sort(key=lambda event: (event["lane_index"], event["lane_name"]))
            log_entry: dict[str, object] = {
                "module": module_name,
                "parameter": parameter_name,
                "beats": beat,
                "value": aggregated_value,
            }
            metadata_payloads = [event["lane_metadata"] for event in events if event["lane_metadata"]]
            if metadata_payloads:
                if len(metadata_payloads) == 1:
                    log_entry["lane_metadata"] = metadata_payloads[0]
                else:
                    log_entry["lane_metadata"] = metadata_payloads
            source_values = [event["source_value"] for event in events]
            if len(source_values) == 1:
                log_entry["source_value"] = source_values[0]
            else:
                log_entry["source_value"] = source_values
                log_entry["smoothing_sources"] = [event["lane_name"] for event in events]
                log_entry["smoothed_values"] = values
                log_entry["smoothing_mode"] = "average"
            if smoothing_info is not None:
                smoothing_info["applied"] = smoothing_applied
                log_entry["smoothing"] = smoothing_info
            automation_log.append(log_entry)

    def _parse_lane_metadata(self, lane: str) -> tuple[str | None, str | None, dict[str, object]]:
        if "." not in lane:
            return None, None, {}
        head, parameter_part = lane.split(".", 1)
        parts = parameter_part.split("|")
        parameter = parts[0]
        metadata: dict[str, object] = {}
        for token in parts[1:]:
            token = token.strip().lower()
            if token in {"normalized", "normalised"}:
                metadata["mode"] = "normalized"
            elif token in {"raw", "absolute"}:
                metadata["mode"] = "raw"
            elif token in {"percent", "percentage"}:
                metadata["mode"] = "percent"
            elif token.startswith("range="):
                _, _, payload = token.partition("=")
                if ":" in payload:
                    min_str, _, max_str = payload.partition(":")
                    try:
                        metadata["range"] = (float(min_str), float(max_str))
                    except ValueError:
                        continue
            elif token.startswith("curve="):
                _, _, payload = token.partition("=")
                if payload:
                    curve_name, _, intensity_str = payload.partition(":")
                    curve_name = curve_name.strip().lower()
                    if curve_name:
                        metadata["curve"] = curve_name
                    if intensity_str:
                        try:
                            metadata["curve_intensity"] = float(intensity_str)
                        except ValueError:
                            continue
            elif token.startswith("smooth=") or token.startswith("smoothing="):
                _, _, payload = token.partition("=")
                payload = payload.strip().lower()
                if not payload:
                    continue
                try:
                    if payload.endswith("ms"):
                        metadata["smooth_seconds"] = max(0.0, float(payload[:-2]) / 1_000.0)
                    elif payload.endswith("s"):
                        metadata["smooth_seconds"] = max(0.0, float(payload[:-1]))
                    elif payload.endswith("beats"):
                        metadata["smooth_beats"] = max(0.0, float(payload[:-5]))
                    elif payload.endswith("beat"):
                        metadata["smooth_beats"] = max(0.0, float(payload[:-4]))
                    else:
                        metadata["smooth_beats"] = max(0.0, float(payload))
                except ValueError:
                    continue
        return head, parameter, metadata

    def _resolve_parameter_spec(
        self,
        module: SineOscillator | ClipSampler | AmplitudeEnvelope | OnePoleLowPass,
        parameter: str,
    ) -> ParameterSpec | None:
        for spec in module.describe_parameters():
            if spec.name == parameter:
                return spec
        return None

    def _automation_value_mapper(
        self,
        spec: ParameterSpec,
        metadata: Mapping[str, object],
    ) -> Callable[[float], float | None]:
        mode = str(metadata.get("mode", "normalized"))
        range_override = metadata.get("range")
        if isinstance(range_override, tuple) and len(range_override) == 2:
            try:
                min_override = float(range_override[0])
                max_override = float(range_override[1])
            except (TypeError, ValueError):
                min_override = spec.minimum
                max_override = spec.maximum
        else:
            min_override = spec.minimum
            max_override = spec.maximum

        min_value = min(min_override, max_override)
        max_value = max(min_override, max_override)

        def clamp_from_spec(value: float | None) -> float | None:
            return spec.clamp(value)

        curve_name = str(metadata.get("curve", "linear")).lower()
        curve_intensity = metadata.get("curve_intensity")

        def apply_curve(normalized: float) -> float:
            normalized = max(0.0, min(1.0, normalized))
            if curve_name in {"exponential", "exp", "ease_in"}:
                exponent = float(curve_intensity) if curve_intensity is not None else 2.0
                exponent = max(1e-3, exponent)
                return normalized**exponent
            if curve_name in {"logarithmic", "log", "ease_out"}:
                exponent = float(curve_intensity) if curve_intensity is not None else 2.0
                exponent = max(1e-3, exponent)
                return normalized ** (1.0 / exponent)
            if curve_name in {"s_curve", "s-curve", "smooth"}:
                strength = float(curve_intensity) if curve_intensity is not None else 1.0
                if strength <= 0.0:
                    return normalized
                base = normalized * normalized * (3.0 - 2.0 * normalized)
                if math.isclose(strength, 1.0, rel_tol=1e-6, abs_tol=1e-6):
                    return base
                base = min(max(base, 1e-6), 1.0 - 1e-6)
                power = max(1e-3, strength)
                numerator = base**power
                denominator = numerator + (1.0 - base) ** power
                if denominator == 0.0:
                    return base
                return numerator / denominator
            return normalized

        if mode == "raw":
            return lambda raw: clamp_from_spec(float(raw))
        if mode == "percent":
            def mapper_percent(raw: float) -> float | None:
                percent = max(0.0, min(100.0, float(raw))) / 100.0
                curved = apply_curve(percent)
                scaled = min_value + (max_value - min_value) * curved
                return clamp_from_spec(scaled)

            return mapper_percent

        # Default to normalized mapping.
        def mapper_normalized(raw: float) -> float | None:
            normalized = max(0.0, min(1.0, float(raw)))
            curved = apply_curve(normalized)
            scaled = min_value + (max_value - min_value) * curved
            return clamp_from_spec(scaled)

        return mapper_normalized

    def _metadata_smoothing_beats(self, metadata: Mapping[str, object] | None) -> float:
        if not metadata:
            return 0.0
        beats = 0.0
        smooth_beats = metadata.get("smooth_beats")
        if smooth_beats is not None:
            try:
                beats = max(beats, float(smooth_beats))
            except (TypeError, ValueError):
                pass
        smooth_seconds = metadata.get("smooth_seconds")
        if smooth_seconds is not None:
            try:
                seconds = float(smooth_seconds)
                seconds_per_beat = max(self.tempo.beats_to_seconds(1.0), 1e-6)
                beats = max(beats, seconds / seconds_per_beat)
            except (TypeError, ValueError):
                pass
        return beats

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

