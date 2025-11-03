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
- **Starter module** – `SineOscillator` delivers a stereo tone with amplitude and
  pitch controls, providing a concrete template for subsequent instruments.

## Usage Example

```python
from audio.engine import EngineConfig, OfflineAudioEngine
from audio.modules import SineOscillator

engine = OfflineAudioEngine(EngineConfig(sample_rate=48_000, block_size=256))
lead = SineOscillator("lead", engine.config)
engine.add_module(lead, as_output=True)
engine.schedule_parameter_change(
    module="lead",
    parameter="amplitude",
    beats=2.0,
    value=0.8,
    source="chorus entry",
)
audio = engine.render(2.0)
```

The rendered array can be saved to disk, analysed in notebooks, or piped through
existing prototypes for quick sound checks.

## Testing & QA

- `tests/test_audio_engine.py` covers tempo conversions, automation ordering,
  and amplitude automation across rendered buffers.
- `tests/test_run_s3_smoke_test.py` adds coverage for the new `.env` loader so QA
  facilitators can run staging checks without shell gymnastics.
- `poetry run pytest` remains the one-stop validation command.

## Next Steps

1. Expand the module library (envelopes, filters, samplers) using the
   `ParameterSpec` conventions so musicians see familiar control names.
2. Introduce performance meters (RMS, LUFS) on rendered buffers to help artists
   tune dynamics before hooking up real-time outputs.
3. Wire the offline engine into the tracker prototype so pattern automation can
   schedule events in beats/bars without extra conversion utilities.
