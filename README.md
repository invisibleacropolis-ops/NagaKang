# NagaKang
Comprehensive Development Plan
1. Vision & Requirements Elaboration
Define product goals, target users (musicians, sound designers), and UX priorities.
Enumerate functional requirements:
Tracker-style sequencing interface with multi-track pattern editor.
Modular instrument designer with node-based routing of sound sources and processors.
Audio engine supporting subtractive, granular, additive, FM, and resynthesis modules.
Effects processing (inserts/sends), global mixer, automation, and parameter modulation.
Multi-touch Kivy GUI with responsive layouts for tablets/desktops.
Capture non-functional requirements:
Low audio latency, high performance.
Cross-platform support (Windows/macOS/Linux, possibly mobile).
Extensibility for future module types, scripting, and community content.
Produce a detailed PRD, UX flow diagrams, and backlog of user stories.
2. System Architecture & Technology Choices
Select audio DSP engine architecture:
Core audio processing in Python with C/C++ accelerated modules via Cython/pybind11 or Rust FFI.
Evaluate libraries (e.g., pyo, sounddevice, numpy) for prototyping vs. custom engine for performance.
Design module graph architecture:
Directed acyclic graph for signal flow, supporting feedback safely.
Standardized interfaces (inputs/outputs, modulation, parameter metadata).
Decide on state management and data persistence:
Project file format (JSON with binary blobs for samples? HDF5?).
Serialization for instruments, patterns, and automation.
Define application layers:
Audio engine (real-time processing threads).
Sequencer/timeline engine (event scheduling, pattern playback).
GUI layer (Kivy components).
Middleware for engine-GUI communication (observer pattern, message queues).
Plan integration with MIDI/OSC and external controllers.
Draft architecture diagrams and API contracts.
3. Audio Engine & Module Framework
Implement core audio engine scaffold:
Real-time audio callback with buffer processing.
Thread-safe parameter updates and event scheduling.
Build module base classes:
Source modules (oscillators, samplers, granular players).
Processor modules (filters, envelopes, effects).
Utility modules (mixers, splitters, modulators).
Develop first batch of modules:
Subtractive synth oscillator + filter + envelope.
Granular sampler (grain scheduling, windowing).
Additive partials engine.
FM operator graph.
Basic resynthesis (FFT-based with phase vocoder).
Create modulation system (LFOs, envelopes, parameter automation).
Establish preset/parameter system with interpolation and randomization.
Optimize DSP routines (vectorization, C extensions, GPU offload where useful).
Add unit/integration tests for DSP correctness (offline renders, golden files).
4. Sequencer & Tracker Interface Logic
Design data structures for patterns, tracks, steps, and automation lanes.
Implement pattern editor logic:
Note entry, velocity, instrument assignment.
Step effects (e.g., slide, retrigger).
Pattern chaining, song arrangement.
Build timing engine:
Tempo management, tick resolution, swing.
Scheduling of notes/events into audio engine.
Enable undo/redo, clipboard, pattern duplication.
Add scripting hooks for advanced pattern generation (future enhancement).
5. Node-Based Instrument Builder
Create visual node graph editor in Kivy:
Drag-and-drop modules, connect wires, configure parameters.
Zoom, pan, multi-touch gestures.
Sync node graph with underlying engine:
Graph serialization/deserialization.
Live editing with audio engine hot-reload.
Provide module library browser with categories, search, and preview.
Implement macros and grouped modules for reusable instrument templates.
6. Effects, Routing, and Mixer
Design mixer architecture:
Track channels with inserts, sends, and return buses.
Master channel with global effects.
Implement effects modules:
Reverb, delay, distortion, chorus, EQ, compression.
Provide routing matrix UI:
Drag-and-drop bus routing, send levels.
Add automation lanes for mixer parameters and global modulation sources.
7. GUI/UX Implementation with Kivy
Establish overall app structure:
Main window layout (tracker view, instrument builder, mixer).
Navigation (tabs, split views, floating panels).
Customize tracker grid widgets optimized for multi-touch input.
Implement multi-touch gestures:
Pinch/zoom, multi-select, parameter tweaking, piano-roll style gestures.
Create consistent theming (light/dark modes, scalable vector graphics).
Implement responsive layout logic for different screen sizes.
Add onboarding tutorials, tooltips, context-sensitive help.
Status: Completed – see `docs/step7_gui_shell.md` for the orchestrator, widget
contracts, mixer insert gesture QA plan, and links to the regression suites
that now gate GUI releases.
8. Project & Asset Management
Define project directory structure and asset pipeline (samples, presets).
Implement file dialogs, import/export (instruments, patterns, audio files).
Support sample recording and editing (basic waveform editor).
Create versioned autosave, crash recovery, and backup system.
The manifest schema, sampler transfer workflow, and autosave expectations for
this milestone now live in `docs/step8_project_manifest.md` alongside references
to `src/domain/project_manifest.py`. The accompanying export CLI
(`tools/export_project_bundle.py`) and GUI autosave hooks described below keep
the README §8 deliverables actionable for outside engineers preparing bundles
for QA. The inverse import workflow is now covered by
`src/domain/project_import_service.py` plus the
 `tools/import_project_bundle.py` CLI, giving testers a checksum-verified path to
 hydrate bundles, copy manifests, and confirm sampler asset parity before
 launching the tracker shell. Reliability drills are supported by
 `tools/autosave_stress_harness.py`, which simulates sustained preview activity
 and reports checkpoint/pruning metrics referenced in the Step 8 QA hand-off pack.
  `TrackerMixerRoot.import_project_bundle(...)` now wires
  :class:`ProjectImportService` summaries straight into the tracker shell so GUI
  operators can hydrate exported bundles, inherit manifest digests, and surface
  asset availability without leaving the rehearsal build. The transport
  widgets echo the imported manifest SHA alongside autosave prompts, giving QA
  immediate confirmation that a crash log references the intended bundle. Real
  autosave drills for the choir demo live under `docs/qa/autosave/`, pairing the
  stress-harness JSON summaries with the generated `.autosave/` checkpoints that
  remote testers will use during the musician pilot.
9. Performance & Quality Assurance
Establish benchmarking suite (buffer underrun tests, CPU usage profiling).
Stress harness outputs are catalogued in `docs/qa/audio_engine_benchmarks.md`, linking benchmark evidence back to this Plan §9 milestone.
Integrate CI/CD pipeline:
Automated unit tests (DSP modules, sequencer logic).
GUI smoke tests (Kivy headless runs).
Setup static analysis, linting (flake8, mypy), documentation builds (Sphinx).
Conduct usability testing with musicians; iterate on UX.
10. Documentation & Developer Experience
Produce comprehensive developer docs:
Architecture overview, module APIs, contribution guide.
Generate user manual/tutorials (written, video).
Provide example projects, presets, and templates.
Establish community channels (issue tracker, discussion forums).
11. Roadmap & Release Strategy
Prioritize MVP feature set:
Core tracker sequencing.
Basic set of sound modules.
Node-based instrument builder.
Mixer with essential effects.
Plan iterative milestones with demoable increments.
Prepare beta program, gather feedback, and schedule stable release.
Plan post-launch features (collaboration, cloud sync, plug-in hosting, scripting).
