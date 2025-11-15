# Audio Reference Pack – Step 3 Velocity Crossfades

This directory stores high-resolution WAV captures produced while dialling in the
Step 3 sampler defaults. The files themselves live in the shared rehearsal
storage because of their size; this manifest records filenames, capture dates,
and LUFS notes so outside engineers can fetch the right asset on demand.

| Filename | Capture Notes | LUFS | Peak | NAS Location | S3 Mirror |
| -------- | ------------- | ---- | ---- | ------------ | --------- |
| `choir_pad_soft.wav` | 4-bar legato choir pad at MIDI velocities 36➜52, recorded at 48 kHz. | −20.6 LUFS | −3.1 dBFS | `Rehearsal NAS:/NagaKang/velocity/2024-04-choir/` | `s3://nagakang-audio-assets/velocity/2024-04-choir/choir_pad_soft.wav` |
| `choir_pad_bold.wav` | Same choir preset driven at velocities 92➜116 to test layer crossfade tails. | −13.2 LUFS | −0.8 dBFS | `Rehearsal NAS:/NagaKang/velocity/2024-04-choir/` | `s3://nagakang-audio-assets/velocity/2024-04-choir/choir_pad_bold.wav` |
| `strings_vs_choir_blend.wav` | Alternating bars comparing string ensemble default vs. choir set. | −16.4 LUFS | −1.7 dBFS | `Rehearsal NAS:/NagaKang/velocity/2024-04-choir/` | `s3://nagakang-audio-assets/velocity/2024-04-choir/strings_vs_choir_blend.wav` |
| `choir_swell_long.wav` | 32-step swell used in Step 3 listening sessions to confirm LUFS smoothing. | −18.5 LUFS | −7.1 dBFS | `Rehearsal NAS:/NagaKang/velocity/2024-04-choir/` | `s3://nagakang-audio-assets/velocity/2024-04-choir/choir_swell_long.wav` |
| `gospel_stab_short.wav` | 280 ms gospel stabs validating the vocal velocity heuristic changes. | −15.4 LUFS | −4.2 dBFS | `Rehearsal NAS:/NagaKang/velocity/2024-04-vocal-stabs/` | `s3://nagakang-audio-assets/velocity/2024-04-vocal-stabs/gospel_stab_short.wav` |

All files were normalised using the offline render path documented in
`docs/qa/audio_velocity_crossfade_listening.md`. Engineers needing local copies
can now pull from the NAS *or* download directly from the secure mirror detailed
in `sampler_s3_manifest.json`, which also records SHA-256 hashes for QA spot
checks. CI publishes mixer trend snapshots beside this manifest so the audio and
meter data stay discoverable from a single directory.
