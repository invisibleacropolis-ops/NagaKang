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

## Return Bus Spatial Effects

- Added `audio.effects.StereoFeedbackDelayInsert`, a feedback delay tuned
  for send/return workflows.  It keeps per-channel state so echoes ring
  out over multiple mixer blocks and exposes straightforward musician
  controls (delay milliseconds, feedback, dry/wet mix).
- Added `audio.effects.PlateReverbInsert`, a lightweight diffused delay
  network that captures the plate-style ambience promised in README §6.
  The insert processes pre-delay and diffusion in separate stages so
  future GUI sliders map directly to the documented parameters.
- Return bus processors in `audio.mixer.MixerReturnBus` now run these
  spatial effects, letting Step 6 demonstrations showcase send/return
  presets instead of placeholder gain-only processors.

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
- Nested subgroup routing lets engineers layer buses (e.g., drums →
  band → master) while keeping inserts and fader logic intact.  Each
  subgroup now tracks a `MeterReading` so the GUI and QA dashboards can
  surface peak/RMS information without reprocessing buffers.
- `MixerGraph.channel_groups` exposes the channel → subgroup mapping so
  UI layers can reflect routing assignments, and
  `MixerGraph.subgroup_meters` returns the latest meter snapshot for
  display.

## Kivy Mixer Mock Binding

- Authored `docs/step6_mixer_kivy_mock.py`, introducing
  `MixerBoardAdapter` and `MixerStripWidget` prototypes that translate
  `MixerGraph` state (faders, subgroup meters, send assignments) into a
  touch-friendly strip model.
- The demo graph inside the mock exercises the new reverb/delay return
  buses and nested routing so UI contributors can see the expected data
  flow while the full Kivy implementation comes together.
- The adapter uses the new subgroup metering API to feed peak/RMS values
  directly into `NumericProperty` fields, establishing the pattern Kivy
  contributors will follow for the production mixer layout.

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

## Mixer Automation & QA Diagnostics

- Tracker automation lanes targeting `mixer:channel:*` and
  `mixer:subgroup:*` endpoints now schedule events directly against
  :class:`audio.mixer.MixerGraph`.  Normalised curves and `|range=`
  overrides map cleanly onto send levels, subgroup faders, and mute
  toggles so tracker envelopes can drive real routing gestures.
- `MixerGraph` exposes a musician-friendly automation timeline, replaying
  events on block boundaries and logging them for downstream tooling. The
  tracker bridge resets the graph between renders and logs the mixer
  events alongside instrument automation for audit trails.
- New CLI: ``poetry run python tools/mixer_diagnostics.py`` renders the
  demo graph, prints subgroup meters, return levels, and the scheduled
  automation events (``--json``/``--pretty`` available for QA exports).

## Kivy Mock Enhancements

- `docs/step6_mixer_kivy_mock.py` gained insert reordering helpers and
  return-strip state so UI contributors can simulate drag-and-drop insert
  moves plus dedicated return bus columns without booting full Kivy
  builds.
- `MixerStripWidget` now tracks insert order and return-state hints,
  while ``MixerBoardAdapter`` exposes ``return_state`` and
  ``reorder_channel_inserts`` helpers mirroring the new backend
  capabilities.

## Next Steps

1. Expand mixer automation hooks so tracker envelopes can target send
   levels and subgroup faders alongside existing channel parameters.
2. Integrate the metering snapshots into CLI/QA diagnostics, ensuring
   regression runs capture Step 6 routing levels without launching the
   GUI.
3. Flesh out the Kivy mock with drag-and-drop insert reordering and
   return bus strips, paving the way for the full multi-touch layout.

