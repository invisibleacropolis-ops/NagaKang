# Step 6 Kickoff – Effects, Routing, and Mixer

This note records the first implementation pass for README §6.  The goal
for this session was to unblock downstream DSP and GUI work by defining
clear mixer primitives, proving out auxiliary routing in code, and
capturing the visual layout strategy so Kivy contributors can pick up
from a stable baseline.

## Channel & Bus Architecture

- **Channel abstraction (`audio.mixer.MixerChannel`)**
  - Wraps an instrument/output module and exposes inserts, pan, fader,
    mute, and send slots in musician language (decibels for faders,
    linear pan between -1 ➜ 1).
  - Inserts accept callables so future DSP effects can be introduced
    incrementally while we stabilise the parameter model for tracker
    integration.
  - Sends are keyed by bus name and can be marked pre/post-fader,
    matching the routing language in the product requirements.  Linear
    gain values are derived from dB storage to stay musician-facing.

- **Return buses (`audio.mixer.MixerReturnBus`)**
  - Aggregate per-channel sends, optionally running the sum through a
    processor callable before contributing back to the master mix.
  - Bus output retains a dB-level control so mix engineers can ride
    return intensity without rebalancing channel sends.

- **Mixer graph (`audio.mixer.MixerGraph`)**
  - Owns named channels and return buses, sums blocks in-place, and
    exposes a `render()` helper mirroring the offline engine so unit
    tests and prototypes can scrub through longer buffers.
  - Per-block processing runs the return processors even when a block is
    silent, allowing reverbs/delays to ring out naturally once the DSP
    implementations land.

## Auxiliary Routing Prototype

- Unit tests in `tests/test_audio_mixer.py` cover:
  - Fader and pan interaction, ensuring mono sources distribute as
    expected when pushed hard-left with a -6 dB trim.
  - Pre-fader sends targeting a return bus with a simple gain-doubling
    effect, confirming that the block summation accounts for both the
    dry and processed contributions.
- Expanded coverage now exercises the subgroup/solo signal path plus the
  new insert processors, keeping Step 6 regression confidence high as we
  add more complex routing scenarios.
- Error handling defends against missing return buses so configuration
  bugs surface immediately in tests or during live authoring.

## Insert Library Expansion

- Added `audio.effects.ThreeBandEqInsert`, a stateful three-band EQ that
  applies low-shelf, peaking mid, and high-shelf curves without breaking
  the mixer’s insert contract.  Gains are stored in dB so outside
  engineers can reason about tonal moves using familiar console
  language.
- Added `audio.effects.SoftKneeCompressorInsert`, a feed-forward dynamic
  processor with musical attack/release coefficients, soft-knee control,
  and optional makeup gain.  This gives channel and subgroup strips a
  ready-made way to tame peaks before more advanced DSP modules land.

## Subgroup & Solo Scaffolding

- `audio.mixer.MixerSubgroup` aggregates post-fader channel output,
  exposes its own insert slots, and mirrors fader/mute controls so
  rhythm sections or vocal stacks can be balanced as a single unit.
- `MixerGraph` learned subgroup registration, channel ➜ subgroup
  assignment, and solo propagation.  When any strip or subgroup enters
  solo, the graph constrains processing to the highlighted paths,
  matching the workflow described in README §6.

## Kivy Mixer Layout Strategy

- **Strip layout**: Each mixer strip will stack (top ➜ bottom)
  metering, fader, pan, insert slots, and send knobs.  Inserts remain a
  vertically sortable list with drag handles; sends use rotary controls
  with pre/post indicators and auxiliary meters inline.
- **Bus overview**: Return buses occupy a right-hand column mirroring
  channel strips but with condensed controls (no instrument section) and
  emphasised input metering so musicians can balance ambience quickly.
- **Routing matrix**: A collapsible panel will reveal a grid-based view
  for advanced routing (e.g., channel ➜ subgroup ➜ master).  This panel
  reuses the send data model so the GUI stays synchronised with the
  backend graph defined above.
- **Touch ergonomics**: All rotary controls adopt the existing tracker
  gesture vocabulary (vertical swipes for coarse adjustment, horizontal
  drags for fine) and expose modifier affordances for mouse/pen users.

## Next Steps

1. Implement the spatial effects (reverb/delay) required for the first
   auxiliary presets so return buses can demonstrate real ambience.
2. Surface subgroup metering and nested routing to round out the Step 6
   matrix before GUI integration.
3. Start wiring Kivy prototypes against the new mixer primitives,
   piggy-backing on the node builder command patterns for undo/redo and
   automation hand-off.

