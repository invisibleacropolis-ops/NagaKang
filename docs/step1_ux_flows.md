# UX Flows and Experience Notes

The following flows describe critical end-to-end journeys for the NagaKang MVP. Each flow highlights user motivations, UI entry points, core interactions, and completion criteria. These descriptions will guide later diagramming and prototyping efforts.

## Flow 1: Creating a New Project and Sequencing a Pattern
1. **Launch & Onboarding**
   - User opens NagaKang and is greeted by a start screen with recent projects and tutorial links.
   - Quick-start tips highlight tracker grid navigation and gesture hints.
2. **Create Project**
   - User taps "New Project" and selects a default template (empty project or demo setup).
   - App initializes default BPM, time signature, and an empty song arrangement.
3. **Add Instrument**
   - User opens the instrument library and selects "Create Instrument" to enter the node-based builder.
   - A starter subtractive synth template appears with oscillator, filter, envelope, and output modules connected.
   - User tweaks basic parameters (waveform, filter cutoff) and saves as "Bassline A".
4. **Sequence Pattern**
   - Back in the tracker view, the user selects Track 1 and inserts a new pattern.
   - Using keyboard shortcuts or touch gestures, they enter notes, velocities, and slide effects.
   - Real-time audition plays each step during entry; undo/redo enables quick adjustments.
5. **Arrange Song**
   - User copies the pattern to create variations and chains them on the timeline.
   - Loop markers allow continuous playback for refinement.
6. **Save Project**
   - Autosave runs in the background; user chooses "Save As" to set project name and location.

**Completion Criteria:** User can hear a looped bassline pattern using the newly created instrument and has a saved project file.

## Flow 2: Designing a Custom Instrument with Modulation
1. **Instrument Browser**
   - User opens the instrument builder from the main navigation and selects "New Instrument".
2. **Node Graph Assembly**
   - They drag in a granular sampler module and load a sample from local storage.
   - Add envelope, LFO, filter, and effects nodes; connect them to define modulation paths.
   - Graph canvas supports pinch-to-zoom and drag gestures for organization.
3. **Parameter Configuration**
   - Parameter inspector shows contextual controls with multi-touch sliders and fine-tune modes.
   - User assigns LFO to grain position with modulation depth and rate controls.
4. **Macro Assignment**
   - Macro panel allows mapping multiple parameters to a single control for performance tweaking.
   - User maps grain density, filter cutoff, and reverb mix to Macro 1 with scaling curves.
5. **Preset Management**
   - Instrument is saved as a preset with metadata (tags, author, preview audio).
   - Optionally export preset for sharing.

**Completion Criteria:** User can trigger the instrument from the tracker and hear modulation-responsive playback; preset appears in the library.

## Flow 3: Mixing and Applying Effects
1. **Mixer Access**
   - User switches to the mixer tab where tracks and buses are displayed with meters and send knobs.
2. **Insert Effects**
   - On Track 1, user inserts a compressor and adjusts threshold and ratio while monitoring gain reduction meters.
   - Adds a delay effect on Track 2 with tempo-synced feedback settings.
3. **Send/Return Routing**
   - User creates a reverb return bus and sets send levels from relevant tracks.
   - Routing matrix visualizes signal flow; drag-and-drop wires adjust connections.
4. **Automation**
   - User enables automation lane for Track 1 volume, drawing a fade-in curve synced to pattern playback.
   - Macro assignments can automate send levels for dynamic transitions.
5. **Performance Monitoring**
   - Performance HUD shows CPU/DSP usage; user toggles low-latency mode if dropouts occur.

**Completion Criteria:** User has a balanced mix with insert and send effects applied, automation recorded, and no audio glitches during playback.

## Flow 4: Live Performance and Controller Integration (Stretch Goal)
1. **Controller Setup**
   - User connects a MIDI controller; app detects device and opens mapping assistant.
2. **Mapping Learn Mode**
   - User taps a parameter (e.g., filter cutoff) and moves a controller knob; mapping is saved with scaling options.
3. **Performance View**
   - Live performance layout emphasizes macros, mixer faders, and clip launching pads.
   - User triggers patterns, tweaks macros, and records parameter automation in real time.
4. **Session Capture**
   - Performance is recorded as a new arrangement snapshot with notes, automation, and mix settings.

**Completion Criteria:** User can manipulate key parameters from the controller and capture an expressive performance.

## UX Considerations for Prototyping
- Provide skeletal wireframes for tracker view, node editor, and mixer to validate layout density.
- Test multi-touch gestures on actual devices early to ensure ergonomic spacing.
- Ensure accessibility features (high-contrast theme toggle, font scaling) are present in prototypes.
- Document empty states, error messages, and loading indicators for asset-heavy operations.

## Artifacts to Produce in Later Steps
- Low-fidelity wireframes covering each flow.
- Interactive prototype demonstrating pattern editing and node manipulation.
- Updated UX documentation capturing feedback from usability tests.

