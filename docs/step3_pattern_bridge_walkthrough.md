# Step 3 Pattern Bridge Walkthrough – Musicians First

This walkthrough expands on the Step 3 audio engine foundation by showing how
tracker patterns now flow directly into the production-grade offline renderer.
The goal is to give rehearsal directors and session musicians a repeatable way
to check clip samplers, envelopes, and filters without leaving their familiar
pattern grid.

## What Landed

- **Clip sampler defaults:** `audio.modules.ClipSampler` exposes start/length
  gestures, velocity-sensitive gain/start offsets, multi-layer sample selection,
  retriggers, and semitone transposition so vocal chops or drum hits can be
  staged quickly.
- **Pattern-aware scheduling:** `audio.tracker_bridge.PatternPerformanceBridge`
  reads `domain.models.Pattern` data, converts step events into beat-aligned
  automation, and reuses the offline engine to produce renders.
- **Per-beat loudness summaries:** The bridge packages beat buckets with RMS and
  LUFS metrics, letting notebook dashboards surface dynamics trends at a glance.
- **Prototype CLI:** `python prototypes/audio_engine_skeleton.py --pattern-demo`
  prints the loudness table and automation counts so QA can sanity-check new
  patterns before shipping stems.

## Trying the Demo

1. Ensure dependencies are installed (`poetry install`).
2. Run the pattern demo from the repository root:

   ```bash
   poetry run python prototypes/audio_engine_skeleton.py --pattern-demo --duration 4 --tempo 128
   ```

3. The CLI prints rows like:

   ```
   [INFO] Pattern beats 0.0–1.0: RMS L/R -14.2/-14.1 dBFS, -13.6 LUFS
   [INFO] Pattern beats 1.0–2.0: RMS L/R -26.5/-26.4 dBFS, -28.3 LUFS
   [INFO] Pattern beats 2.0–3.0: RMS L/R -11.8/-11.7 dBFS, -11.2 LUFS
   [INFO] Pattern demo automation events: 8
   ```

   Use the RMS/LUFS swings to decide whether the second hit needs extra layering
   or whether the envelope release should stretch.

## Layering Your Own Pattern

The bridge works with the production `Pattern` and `InstrumentDefinition`
schemas. A minimal sampler chain can be described in JSON or Python:

```python
from domain.models import AutomationPoint, InstrumentDefinition, InstrumentModule, Pattern, PatternStep
import numpy as np

config = EngineConfig(sample_rate=48_000, block_size=128, channels=2)
tempo = TempoMap(tempo_bpm=124.0)
sample_buffer = np.sin(2 * np.pi * 220.0 * np.linspace(0, 1, config.sample_rate, dtype=np.float32))
library = {
    "vox_soft": np.stack([sample_buffer * 0.7, sample_buffer * 0.7], axis=1),
    "vox_hard": np.stack([sample_buffer, sample_buffer], axis=1),
}

instrument = InstrumentDefinition(
    id="vox",
    name="Vocal Chop",
    modules=[
        InstrumentModule(
            id="sampler",
            type="clip_sampler:vox",
            parameters={
                "start_percent": 0.2,
                "length_percent": 0.5,
                "velocity_start_offset_percent": 0.25,
                "layers": [
                    {"sample_name": "vox_soft", "max_velocity": 80, "amplitude_scale": 0.75},
                    {"sample_name": "vox_hard", "min_velocity": 81, "amplitude_scale": 1.1},
                ],
            },
        ),
        InstrumentModule(id="env", type="amplitude_envelope", inputs=["sampler"], parameters={"attack_ms": 12.0}),
        InstrumentModule(id="lp", type="one_pole_low_pass", inputs=["env"], parameters={"cutoff_hz": 3_000.0}),
    ],
)

pattern = Pattern(
    id="vox_pattern",
    name="Vox Pattern",
    length_steps=16,
    steps=[
        PatternStep(note=60, velocity=70, instrument_id="vox"),
        *[PatternStep() for _ in range(7)],
        PatternStep(note=67, velocity=120, instrument_id="vox"),
        *[PatternStep() for _ in range(7)],
    ],
    automation={"lp.cutoff_hz": [AutomationPoint(position_beats=0.0, value=1_600.0), AutomationPoint(position_beats=3.0, value=4_000.0)]},
)

bridge = PatternPerformanceBridge(config, tempo, sample_library=library)
playback = bridge.render_pattern(pattern, instrument)
loudness = bridge.loudness_trends(playback)
```

Feed the returned `loudness` table into a notebook plot or tracker UI to show
musicians how dynamics evolve across the phrase. The automation log now lists
per-step velocity events alongside gates and retriggers, making it easy to
double-check how expressive MIDI data mapped into sampler playback.

### Automation lane scaling for musicians

Automation lanes now accept musician-friendly scaling hints baked into the lane
name so notebooks and tracker UIs can stay normalized while the bridge resolves
real parameter ranges:

- `module.parameter|normalized` (default) maps values `0.0 ➜ 1.0` into the
  parameter's declared `ParameterSpec.minimum` ➜ `maximum` range.
- `module.parameter|percent` treats lane values as `0 ➜ 100` percentages before
  mapping into the declared range. This is useful when teaching workshop
  participants with "percentage" vocabulary.
- `module.parameter|raw` bypasses scaling entirely so advanced users can push
  absolute numbers straight into the engine.
- Append `|range=min:max` to clamp the mapped range for that lane (e.g.
  `filter.cutoff_hz|normalized|range=200:8000`).

The automation log records both the normalized `source_value` and the resolved
`value`, along with the parsed `lane_metadata`, so rehearsal leads can audit how
their tracker gestures were translated into engine parameters.

## Next Steps

- Layer additional sampler voices by instantiating multiple `ClipSampler`
  modules inside the instrument and referencing them from the pattern.
- Extend the bridge with beat-aligned mixer automation so rehearsal directors
  can preview send effects without exporting stems.
- Capture screenshots of the loudness dashboard once the tracker UI consumes
  `beat_loudness` to close the musician feedback loop.
