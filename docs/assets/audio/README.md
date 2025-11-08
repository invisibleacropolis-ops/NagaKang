# Audio Reference Pack – Step 3 Velocity Crossfades

This directory stores high-resolution WAV captures produced while dialling in the
Step 3 sampler defaults. The files themselves live in the shared rehearsal
storage because of their size; this manifest records filenames, capture dates,
and LUFS notes so outside engineers can fetch the right asset on demand.

| Filename | Capture Notes | LUFS | Peak | Location |
| -------- | ------------- | ---- | ---- | -------- |
| `choir_pad_soft.wav` | 4-bar legato choir pad at MIDI velocities 36➜52, recorded at 48 kHz. | −20.6 LUFS | −3.1 dBFS | `Rehearsal NAS:/NagaKang/velocity/2024-04-choir/` |
| `choir_pad_bold.wav` | Same choir preset driven at velocities 92➜116 to test layer crossfade tails. | −13.2 LUFS | −0.8 dBFS | `Rehearsal NAS:/NagaKang/velocity/2024-04-choir/` |
| `strings_vs_choir_blend.wav` | Alternating bars comparing string ensemble default vs. choir set. | −16.4 LUFS | −1.7 dBFS | `Rehearsal NAS:/NagaKang/velocity/2024-04-choir/` |

All files were normalised using the offline render path documented in
`docs/qa/audio_velocity_crossfade_listening.md`. Engineers needing local copies
should request the `2024-04-choir` bundle from the rehearsal NAS or the secure
S3 mirror referenced in the release checklist.
