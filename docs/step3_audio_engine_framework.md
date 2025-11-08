# Step 3 Kickoff – Musician-Centered Audio Engine Scaffold

This note captures the first production code dedicated to Plan §3 (Audio Engine &
Module Framework) with a deliberate focus on musicians and facilitators rather
than software engineers. The new `audio/` package provides the foundation that
future tracker features, live performance tools, and module designers will build
upon.

## Highlights

- **Musician-friendly parameter metadata** – `ParameterSpec` stores display
  names, ranges, and musical context tags (pitch, dynamics, etc.) so UI layers
  can present controls without translation work.
- **Tempo-aware automation** – `AutomationTimeline` understands beats/bars via
  `TempoMap`, letting rehearsal leads schedule sweeps in musical time instead of
  raw seconds.
- **Offline rendering loop** – `OfflineAudioEngine` renders blocks while applying
  automation events, giving sound designers an immediate way to audition module
  behaviour without real-time drivers.
- **Module library growth** – `ClipSampler` now supports velocity-aware
  dynamics, per-note start gestures, multi-layer sample selection, and
  `velocity_crossfade_width` smoothing so keyboardists can dig into expressive
  chops without juggling extra routing. It joins `SineOscillator`,
  `AmplitudeEnvelope`, and `OnePoleLowPass`, letting
  musicians audition vocal chops or drum slices alongside tone-shaping
  envelopes and filters without leaving the engine scaffold.
- **Render loudness helpers** – `audio.metrics` surfaces RMS (per channel) and a
  lightweight LUFS estimate so setlist curators can check headroom without
  leaving the notebook workflow.
- **Tracker-aware pattern bridge** – `PatternPerformanceBridge` wires domain
  patterns into the offline engine, schedules sampler retriggers in beat time,
  and returns per-beat loudness tables for tracker dashboards. The new
  `tracker_loudness_rows` helper formats those metrics into label/text payloads
  that slot directly into rehearsal notebooks.
- **Instrument family crossfades** – When tracker instruments tag a sampler with
  `instrument_family` metadata (strings/pads, keys, or plucked), the bridge now
  applies musician-tested defaults for `velocity_crossfade_width` so multi-layer
  programs glide by default even before fine-tuning.
- **Automation smoothing tokens** – Automation lanes can append `|smooth=5ms`
  (or `|smooth=0.02beats`) to request a micro fade. The bridge expands those
  requests into linear ramps across prior values and logs the applied window so
  facilitators can troubleshoot envelope bumps.
- **Automation curve metadata** – Tracker lanes can now append
  `|curve=exponential`, `|curve=log`, or `|curve=s_curve` so rehearsal leaders
  can design expressive fades without leaving the normalized lane workflow.

## Usage Example

```python
from audio.engine import EngineConfig, OfflineAudioEngine
from audio.modules import AmplitudeEnvelope, ClipSampler, OnePoleLowPass, SineOscillator

config = EngineConfig(sample_rate=48_000, block_size=128)
engine = OfflineAudioEngine(config)
osc = SineOscillator("lead", config)
env = AmplitudeEnvelope("lead_env", config, source=osc)
filt = OnePoleLowPass("lead_filter", config, source=env)
engine.add_module(osc)
engine.add_module(env)
engine.add_module(filt, as_output=True)

engine.schedule_parameter_change("lead", "amplitude", beats=0.0, value=0.6)
engine.schedule_parameter_change("lead_env", "gate", beats=0.0, value=0.0)
engine.schedule_parameter_change("lead_env", "gate", beats=1.0, value=1.0)
engine.schedule_parameter_change("lead_filter", "cutoff_hz", beats=0.0, value=400.0)
engine.schedule_parameter_change("lead_filter", "cutoff_hz", beats=3.0, value=4_000.0)

audio = engine.render(4.0)

from audio.metrics import integrated_lufs, rms_dbfs

print(rms_dbfs(audio))
print(integrated_lufs(audio, sample_rate=config.sample_rate))
```

The rendered array can be saved to disk, analysed in notebooks, or piped through
existing prototypes for quick sound checks.

### Layering with the sampler

```python
import numpy as np

from audio.modules import ClipSampler, ClipSampleLayer

time = np.linspace(0, 1, config.sample_rate, dtype=np.float32)
base = np.sin(2 * np.pi * 220.0 * time, dtype=np.float32)
bright = np.sin(2 * np.pi * 440.0 * time, dtype=np.float32)

sampler = ClipSampler(
    "vox",
    config,
    layers=[
        ClipSampleLayer(sample=np.stack([base, base], axis=1), max_velocity=80, amplitude_scale=0.7),
        ClipSampleLayer(sample=np.stack([bright, bright], axis=1), min_velocity=81, amplitude_scale=1.1),
    ],
    start_percent=0.2,
    length_percent=0.4,
)
sampler.set_parameter("velocity_amplitude_min", 0.3)
sampler.set_parameter("velocity_amplitude_max", 1.0)
sampler.set_parameter("velocity_start_offset_percent", 0.25)

env = AmplitudeEnvelope("vox_env", config, source=sampler, attack_ms=15.0, release_ms=120.0)
lp = OnePoleLowPass("vox_lp", config, source=env, cutoff_hz=3_200.0)

engine.add_module(sampler)
engine.add_module(env)
engine.add_module(lp, as_output=True)

engine.schedule_parameter_change("vox", "velocity", beats=0.0, value=60.0)
engine.schedule_parameter_change("vox", "retrigger", beats=0.0, value=1.0)
engine.schedule_parameter_change("vox_env", "gate", beats=0.0, value=1.0)
engine.schedule_parameter_change("vox_env", "gate", beats=1.0, value=0.0)
audio = engine.render(2.0)
```

Use the `velocity` parameter to match incoming MIDI data, tweak
`velocity_amplitude_min`/`_max` to shape dynamics, and lean on
`velocity_start_offset_percent` to soften soft hits by skipping into the body
of the clip. The optional `ClipSampleLayer` list picks the right buffer for each
velocity range, so a single module can cover soft-to-hard articulations.

### Velocity crossfade listening notes

- **Strings & pads** – map soft articulations to MIDI `1–64`, body layers to
  `65–104`, and bold swells to `105–127`. Set
  `velocity_crossfade_width=12` to keep legato tails breathing without audible
  layer seams. The new regression test
  (`tests/test_audio_modules.py::test_sampler_velocity_crossfade_preserves_decay_tails`)
  confirms the mid-layer tail stays present even when hammering the bold layer.
- **Keys (EP/organ)** – target `velocity_crossfade_width=8` so fast riffs stay
  articulate. Use the mid layer for `55–100` and bold layer above `101` to align
  with typical drawbar and pickup responses.
- **Plucked textures** – favour a narrower `velocity_crossfade_width=6` and
  reserve the boldest layer for `97+` so rhythm sections can comp quietly while
  still accessing aggressive strums.

Capture subjective listening notes during rehearsals and drop them into the
EngineerLog so upcoming patches can fine-tune the weighting heuristics.

See `docs/qa/audio_velocity_crossfade_listening.md` for direct comparison notes
from the latest sampler bounce sessions, including LUFS deltas and recommended
default crossfades for each captured instrument family.

## Prototype Bridge (Step 3 Focus)

`prototypes/audio_engine_skeleton.py` now exposes the existing
`AudioEngine.render_with_musician_engine`, the new `--musician-demo` tone flag,
and a tracker-facing `--pattern-demo` CLI flag. The pattern demo spins up the
production `OfflineAudioEngine`, routes a sampler/envelope/filter chain through
`PatternPerformanceBridge`, and prints per-beat LUFS/RMS snapshots so rehearsal
directors can compare dynamics without exporting stems.

Run the tracker demo directly:

```bash
poetry run python prototypes/audio_engine_skeleton.py --pattern-demo --duration 4 --tempo 128
```

The CLI prints a beat-by-beat loudness table along with the number of automation
events scheduled from the pattern definition, making it easy to sanity check
tracker exports in notebooks.

## Testing & QA

- `tests/test_audio_engine.py` covers tempo conversions, automation ordering,
  and amplitude automation across rendered buffers.
- `tests/test_audio_modules.py` verifies the envelope/filter chain reacts to
  beat automation and that loudness metrics stay musician friendly.
- `tests/test_run_s3_smoke_test.py` adds coverage for the new `.env` loader so QA
  facilitators can run staging checks without shell gymnastics.
- `poetry run pytest` remains the one-stop validation command.

## Next Steps

1. Expand the module library (samplers, modulation) using the `ParameterSpec`
   conventions so musicians see familiar control names.
2. Broaden the loudness toolkit with crest-factor and peak hold displays to
   complement the RMS/LUFS baseline captured here.
3. Feed the offline engine metrics back into tracker UI prototypes so rehearsal
   leaders can audition dynamics without exporting stems.
