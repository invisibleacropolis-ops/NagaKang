# Audio Engine Stress Harness Benchmarks

These measurements document the Step 2 instrumentation follow-up described in the Comprehensive Development Plan (README §9). The harness exercises `AudioEngine.run_stress_test` under a few deterministic configurations so we can track latency envelopes and CPU headroom as we iterate on DSP modules.

## Methodology
- Execute `prototypes/audio_engine_skeleton.AudioEngine.run_stress_test` in offline mode to avoid audio device variability.
- Capture callback timing using the enhanced `AudioMetrics` aggregation helpers (`avg_callback_ms`, `p95_callback_ms`).
- Report CPU load as the ratio of callback duration to buffer duration; loads >1.0 indicate underruns at the given configuration.
- Scenarios cover nominal processing, moderate simulated work (`processing_overhead`), and an intentionally overloaded case for alert calibration.

Command snippet:

```bash
python - <<'PY'
from prototypes.audio_engine_skeleton import AudioEngine, AudioSettings

scenarios = [
    {"name": "Baseline", "duration": 0.5, "overhead": 0.0, "settings": AudioSettings(block_size=256, test_tone_hz=440.0)},
    {"name": "ModerateLoad", "duration": 0.5, "overhead": 0.0008, "settings": AudioSettings(block_size=128, test_tone_hz=440.0)},
    {"name": "Overloaded", "duration": 0.25, "overhead": 0.0025, "settings": AudioSettings(block_size=64, test_tone_hz=440.0)},
]

rows = []
for scenario in scenarios:
    engine = AudioEngine(settings=scenario["settings"], processing_overhead=0.0)
    metrics = engine.run_stress_test(scenario["duration"], processing_overhead=scenario["overhead"])
    snapshot = metrics.snapshot()
    rows.append((scenario["name"], scenario["settings"].block_size, snapshot))

for name, block_size, snapshot in rows:
    print(name, block_size, snapshot)
PY
```

## Results

| Scenario | Block Size | Processing Overhead (s) | Callbacks | Underruns | Avg Callback (ms) | P95 Callback (ms) | Avg CPU Load | Max CPU Load |
|----------|------------|--------------------------|-----------|-----------|-------------------|-------------------|--------------|--------------|
| Baseline | 256        | 0.0000                   | 94        | 0         | 0.0207            | 0.0329            | 0.0039       | 0.0323       |
| ModerateLoad | 128    | 0.0008                   | 188       | 0         | 0.9244            | 0.9764            | 0.3487       | 0.7862       |
| Overloaded | 64       | 0.0025                   | 188       | 188       | 2.6462            | 2.6985            | 1.9959       | 4.2376       |

## Observations
- The baseline configuration maintains generous headroom (avg CPU load <0.01) confirming the harness overhead is negligible.
- Moderate simulated processing raises CPU load to ~35% but still avoids underruns, validating the alert threshold set at >1.0.
- The overloaded profile intentionally exceeds realtime budgets, driving underruns and surfacing peak CPU load >4× the buffer window—ideal for verifying alert telemetry wiring in `docs/assets/audio_failure_modes.mmd`.

## Next Steps
- Re-run these scenarios when adding new DSP modules or modifying processing pipelines; append dated tables to this document for regression tracking.
- Integrate automated CSV exports so CI can attach benchmark artifacts once native modules are introduced in later roadmap steps.
