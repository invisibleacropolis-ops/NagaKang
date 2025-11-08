# Step 3 Tracker Notebook Loudness Widget

The Step 3 musician enablement goal calls for beat-level loudness feedback right
inside rehearsal notebooks so performers never leave the tracker grid. This
widget consumes `PatternPerformanceBridge.tracker_loudness_rows` and presents a
color-coded dashboard that coaches ensembles on dynamics at a glance.

## Quick start in a Jupyter notebook

```python
from audio.engine import EngineConfig, TempoMap
from audio.tracker_bridge import PatternPerformanceBridge
from docs.step3_tracker_notebook_widget import show_loudness_widget

# Existing pattern render
bridge = PatternPerformanceBridge(config, tempo, sample_library=library)
playback = bridge.render_pattern(pattern, instrument)
rows = bridge.tracker_loudness_rows(playback, beats_per_bucket=1.0)

show_loudness_widget(rows)
```

- Rows marked **Bold** highlight passages averaging louder than −10 dBFS (good
  for choruses or big drops).
- **Balanced** spans −10 dBFS ➜ −18 dBFS, ideal for verse textures.
- **Soft** flags sections below −18 dBFS so arrangers can thicken pads or
  nudge sampler layers without exporting stems.

When `ipywidgets` or `IPython.display` is unavailable the helper falls back to a
plain-text summary so musicians rehearsing on minimal machines still get useful
insight.

## Facilitator notes

- Capture a screenshot of the widget after rehearsals and drop it into
  `docs/assets/` with annotations on which beats felt either overpowering or too
  timid. These visuals will guide Step 3 feedback rounds.
- Encourage performers to dial in sampler velocity ranges according to the
  guidance below so the loudness widget lines up with what they hear on stage.
- Collect 2–3 quotes from musicians using the widget and log them in the next
  EngineerLog session to keep the dynamic grading scheme honest.

## Recommended velocity bands for multi-layer samplers

| Instrument family | Soft layer | Medium layer | Bold layer |
| ----------------- | ---------- | ------------ | ---------- |
| Strings / Pads    | 1–64       | 65–104       | 105–127    |
| Keys (EP/Organ)   | 1–54       | 55–100       | 101–127    |
| Plucked (Guitars) | 1–50       | 51–96        | 97–127     |

Use a `velocity_crossfade_width` of **10–14** for strings/pads and **6–8** for
keys to keep note tails breathing without smearing fast riffs.

## TODO (for future sessions)

- Add a screenshot gallery referencing different ensemble types (choir, synth
  trio, rhythm section).
- Wire the widget into the forthcoming Kivy tracker prototype once the UI layer
  lands in Step 4 so Windows installer builds ship with the same loudness view.
