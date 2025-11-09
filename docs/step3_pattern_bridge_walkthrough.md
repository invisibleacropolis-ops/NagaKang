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
  staged quickly. The sampler now blends adjacent layers with
  `velocity_crossfade_width` so legato passages feel natural when sliding across
  dynamic layers.
- **Instrument-family crossfades:** Tag a sampler module with
  `instrument_family` (`strings`, `pads`, `keys`, `plucked`, or `vocal`) and the
  bridge applies the listening-tested default (`12`, `8`, `6`, or `10` MIDI
  steps) for `velocity_crossfade_width`. Musicians still override manually, but
  the baseline now matches the curated velocity notes in the sampler guide.
- **Vocal amplitude heuristics:** Gospel stab renders raised the vocal defaults
  to `velocity_amplitude_min=0.48` / `velocity_amplitude_max=1.05` so short
  release clips stay audible without flattening bold hits. The bridge applies
  those values automatically when `instrument_family="vocal"` and leaves manual
  overrides intact for edge cases.
- **Pattern-aware scheduling:** `audio.tracker_bridge.PatternPerformanceBridge`
  reads `domain.models.Pattern` data, converts step events into beat-aligned
  automation, and reuses the offline engine to produce renders.
- **Per-beat loudness summaries:** The bridge packages beat buckets with RMS and
  LUFS metrics, letting notebook dashboards surface dynamics trends at a glance.
- **Tracker dashboard helpers:** `PatternPerformanceBridge.tracker_loudness_rows`
  formats the loudness table into label/text pairs (plus a dynamic grade) ready
  for tracker widgets or rehearsal notebook dashboards.
- **Notebook widget integration:** `docs/step3_tracker_notebook_widget.py`
  renders those rows with colour-coded dynamics badges, giving rehearsal leads a
  drop-in component for Jupyter notebooks.
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
   [INFO] Smoothing filter.cutoff_hz@0.0000#11: filter.cutoff_hz|smooth=6ms:5=5 segments over 0.01 beats (pending)
   [INFO] Smoothing filter.cutoff_hz@2.0000#12: filter.cutoff_hz|smooth=6ms:5=5 segments over 0.01 beats (applied)
   [INFO] Smoothing summary: 2 rows, 10 segments
   ```

   Use the RMS/LUFS swings to decide whether the second hit needs extra layering
   or whether the envelope release should stretch. The smoothing lines highlight
   how many intermediate points were inserted on each contributing lane so Step 4
   undo/redo tooling can reconcile notebook dashboards with tracker playback. The
   optional `--export-json` flag writes the same payload (including
   `event_id`-tagged automation entries and `segment_breakdown` totals) for QA
   packaging into rehearsal notes or cloud dashboards.

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
                    "velocity_crossfade_width": 10.0,
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
dashboard_rows = bridge.tracker_loudness_rows(playback)
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
- Append `|curve=exponential` (or `log`, `s_curve`) to reshape the normalized
  lane values before scaling. `exponential` eases in softly, `log` eases out,
  and `s_curve` provides a smooth midpoint-focused transition useful for
  swell-style fades. Add an optional intensity (e.g. `curve=exponential:3.0`) to
  tighten or relax the curvature without rewriting lane data.
- Append `|smooth=5ms` (or `|smooth=0.02beats`) when a lane should fan out over
  a micro fade. Add an optional segment count (`|smooth=5ms:5` or
  `|smooth_segments=7`) to control how many intermediate automation points the
  bridge inserts. The automation log now records the applied strategy, window,
  and final segment count.
- When multiple lanes collide on the same module parameter and beat, the bridge
  averages their resolved values and logs `smoothing_sources` so notebook UIs
  can show which lanes contributed to a combined move. This prevents double-
  loudness jumps while keeping the audit trail intact.

The automation log records both the normalized `source_value` and the resolved
`value`, along with the parsed `lane_metadata`, so rehearsal leads can audit how
their tracker gestures were translated into engine parameters. When smoothing is
requested the log also carries a `smoothing` dict (window, segments, strategy,
previous value, and whether the ramp was applied) so facilitators can quickly
spot automation clashes that were gently massaged during rendering. Feed
`automation_smoothing_rows` into the updated notebook widget to turn those
payloads into musician-friendly dashboard badges.

Running `python prototypes/audio_engine_skeleton.py --pattern-demo --export-json demo.json`
now writes an `automation_smoothing_summary` alongside the raw rows. The summary
tracks how many smoothing entries were generated and the total segment count so
remote QA can diff CLI exports against notebook screenshots without replaying
audio renders.

## Next Steps

- Layer additional sampler voices by instantiating multiple `ClipSampler`
  modules inside the instrument and referencing them from the pattern.
- Extend the bridge with beat-aligned mixer automation so rehearsal directors
  can preview send effects without exporting stems.
- Capture screenshots of the loudness dashboard once the tracker UI consumes
  `beat_loudness` to close the musician feedback loop. The interim notebook
  widget in `docs/step3_tracker_notebook_widget.py` is ready for screenshotting
  during rehearsals.
