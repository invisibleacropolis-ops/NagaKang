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
- Added `mixer:return:*` automation endpoints so tracker envelopes can
  ride return-bus levels during breakdowns without bespoke macros.
- :class:`audio.tracker_bridge.PatternPerformanceBridge` now pipes pattern
  renders through :class:`audio.mixer.MixerGraph` whenever instruments
  declare a ``mixer_channel`` macro.  Mixer automation replays inside the
  offline engine, snapshots land on ``PatternPlayback`` objects, and
  preview buffers inherit subgroup/return processing.
- `MixerGraph` exposes a musician-friendly automation timeline, replaying
  events on block boundaries and logging them for downstream tooling. The
  tracker bridge resets the graph between renders and logs the mixer
  events alongside instrument automation for audit trails.
- Mixer snapshots now include the master bus meter so QA dashboards can
  pair subgroup levels with the final mix headroom.
- New CLI: ``poetry run python tools/mixer_diagnostics.py`` renders the
  demo graph, prints subgroup meters, return levels, and the scheduled
  automation events (``--json``/``--pretty`` available for QA exports).
- Diagnostics CLI learned ``--output`` for CI runs so automation/meter
  snapshots land in JSON artifacts without extra scripting.
- CLI summary now includes master-peak/RMS telemetry to surface headroom
  trends during regression runs.

## Kivy Mock Enhancements

- `docs/step6_mixer_kivy_mock.py` gained insert reordering helpers and
  return-strip state so UI contributors can simulate drag-and-drop insert
  moves plus dedicated return bus columns without booting full Kivy
  builds.
- `MixerStripWidget` now tracks insert order and return-state hints,
  while ``MixerBoardAdapter`` exposes ``return_state`` and
  ``reorder_channel_inserts`` helpers mirroring the new backend
  capabilities.
- Adapter now exposes ``update_channel_meter`` and ``bind_return_to_widget``
  so docs can demonstrate live meter polling alongside return-strip
  level controls.
- Adapter exposes ``set_return_level`` and ``master_meter`` helpers to
  mirror the new automation hooks in mock UIs.

## QA Trend Exports & Return-Solo Workflow

- `audio.mixer.MixerChannel` now tracks post-fader meters and
  `MixerGraph.channel_post_meters` surfaces the latest readings for each
  strip.  Pattern previews include the post-fader data inside
  `MixerPlaybackSnapshot` so tracker exports can compare individual strip
  dynamics against subgroup and master headroom.
- `tools/mixer_diagnostics.py` gained a `--compare` flag plus JSON diff
  helpers.  QA can point the CLI at a previous capture and immediately
  read the per-strip/subgroup deltas in both JSON and human-readable
  form, removing spreadsheet work when auditing automation sweeps.
- Return-bus rehearsal flow: when auditioning ambience automation,
  freeze channel faders, solo the desired return via the existing send
  level automation helpers, and capture successive CLI snapshots with
  ``--compare``.  The diff highlights return-level changes alongside
  channel post meters so automation rehearsals can focus on how reverb
  tails evolve without losing sight of dry headroom.  Documented in
  ``docs/step6_mixer_kivy_mock.py`` via new widget properties for post-
  fader and subgroup meters, giving UI contributors a reference layout
  for the rehearsal view.

## Next Steps

1. Thread the new meter deltas into the CI QA harness so nightly runs
   surface mixer regressions automatically.
2. Extend the Kivy mock to chart per-strip peak history using the post-
   fader meter snapshots for real-time visualisation.
3. Wire the tracker notebook exports to persist the diff metadata so
   rehearsal notes can link directly to automation trend evidence.

