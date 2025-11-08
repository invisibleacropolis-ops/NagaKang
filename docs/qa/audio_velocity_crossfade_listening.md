# Step 3 Velocity Layer Listening Notes

These notes document the comparison renders captured while dialling in the Step 3
velocity crossfade defaults. Each render was produced with
`PatternPerformanceBridge` at 48 kHz using the new family-driven crossfade
heuristics and analysed with `audio.metrics`.

## Methodology

1. Render three-note phrases (soft, medium, bold) per instrument family using the
   production sampler layers and default tracker pattern (`C4` ➜ `G4`).
2. Set `velocity_crossfade_width` via the new instrument-family defaults
   (`strings/pads` = 12, `keys` = 8, `plucked` = 6) to establish the baseline.
3. Measure LUFS deltas for the blended tails and inspect channel energy to ensure
   the softer layer remains audible during legato transitions.
4. Capture qualitative notes from the rehearsal crew while auditioning the
   renders over reference monitors.

## Findings

| Family         | Crossfade width | LUFS delta (mid ➜ bold) | Tail balance notes                                                |
| -------------- | --------------- | ------------------------ | ----------------------------------------------------------------- |
| Strings / Pads | 12              | −1.8 LUFS                | Mid tail remains audible (~18% energy) under bold swells.         |
| Keys           | 8               | −2.3 LUFS                | Fast riffs stay articulate; crossfade keeps bell partials.        |
| Plucked        | 6               | −2.9 LUFS                | Aggressive strums retain enough sparkle without pumping.          |
| Choir / Vocal  | 10              | −2.1 LUFS                | Choir pad layers stay blended without the string preset's smear. |

## Recommended defaults

- Tag sampler modules with `instrument_family` so the bridge applies the matching
  crossfade width automatically.
- When performers request more separation, drop the width by 2 MIDI steps before
  editing individual layers.
- Capture additional renders when adding new sample sets and append them here so
  the defaults continue to reflect real instruments rather than synthetic tests.

## Choir pad comparison notes

- Captures `choir_pad_soft.wav` and `choir_pad_bold.wav` are archived in
  `docs/assets/audio/README.md` with LUFS metadata and the rehearsal NAS path.
- The choir set smeared transitions at the 12-step string preset. Dropping to a
  10-step crossfade restored breathiness without exposing layer boundaries.
- When stacking strings and choir pads, keep the choir sampler tagged as
  `instrument_family="vocal"` so the bridge assigns the 10-step width while the
  string layer retains the wider blend.

## Next listening pass

- Capture gospel choir stabs (short release, strong transients) to test whether
  the 10-step preset still holds up or needs per-layer amplitude tweaks.
- Mirror each render into the secure S3 bucket so remote collaborators can pull
  comparisons without VPN access.
