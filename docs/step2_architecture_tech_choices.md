# Step 2: System Architecture & Technology Choices

This document operationalizes the Comprehensive Development Plan (see README §2) by evaluating architectural options, selecting initial technologies, and outlining integration patterns that will drive implementation during future steps.

## 1. Architectural Principles
1. **Deterministic Real-Time Audio** – Prioritize low-latency execution with predictable scheduling via explicit audio threads and lock-free queues.
2. **Modular Extensibility** – Design DSP modules, sequencer components, and UI widgets as composable services with stable interfaces to support future community contributions.
3. **Separation of Concerns** – Enforce boundaries between audio engine, sequencing logic, persistence, and presentation layers to ease testing and performance tuning.
4. **Cross-Platform Compatibility** – Favor portable libraries and isolate platform-specific code (audio drivers, filesystem) behind adapter interfaces.

## 2. Layered System Overview
1. **Audio Engine Layer**
   - Real-time audio callback hosted via `sounddevice` for prototyping; target migration path to PortAudio or custom C++ host for production.
   - DSP graph executed in block-sized chunks with double-buffering to minimize cache misses.
   - Lock-free command queue receives parameter updates, note events, and automation data from sequencer layer.
2. **Sequencer & Timing Layer**
   - Pattern scheduler maintains tracker state, tick resolution, and swing timing.
   - Event dispatcher batches note and modulation events, timestamped relative to audio buffer boundaries.
   - Provides deterministic undo/redo journal enabling offline rendering.
3. **State & Persistence Layer**
   - Canonical project model serialized to JSON for readability; large sample buffers referenced externally with hashed filenames.
   - Instrument definitions stored as modular graphs; plan for optional binary pack format (zip + manifest) for distribution.
4. **GUI & Interaction Layer**
   - Kivy-based multi-touch interface with MVVM-inspired binding: ViewModels translate engine state into observable properties.
   - UI thread communicates with sequencer via asynchronous message bus; hot parameter tweaks propagate via throttled updates.
5. **Integration & Middleware Layer**
   - MIDI/OSC bridge built atop `mido` (MIDI) and `python-osc`; leverages worker threads to parse messages and feed sequencer queue.
   - Future controller scripting surface exposed through Python sandbox with restricted module imports.

## 3. Technology Evaluations
### Audio & DSP
- **Python Prototyping Stack:** `numpy`, `sounddevice`, `scipy` for FFT/resynthesis; ideal for rapid iteration but limited for heavy DSP.
- **Native Extensions:** Utilize `cython` for performance-critical oscillators/filters in early releases, with roadmap to `rustworkx`/Rust FFI for granular and FM engines.
- **Alternative Engines:** Monitor `pyo` (rich module set, but less flexible for custom graph) and `JUCE` via `pybind11` for long-term portability.

### Graph & Module Framework
- Implement module graph as directed graph using `networkx` during simulation/testing; convert to custom lightweight adjacency lists in production.
- Each node conforms to `process(buffer, state)` signature with metadata describing I/O channels, modulation targets, and latency characteristics.
- Introduce validation passes to prevent unsafe feedback loops and ensure sample-rate consistency.

### Sequencer Infrastructure
- Leverage `sortedcontainers` for event priority queues to maintain temporal ordering at sub-tick resolution.
- Persistent pattern data stored via `pydantic` models to ensure schema validation and documentation generation.

### GUI Technologies
- Core UI: `kivy` with `kivy.garden.graph` for visual modulation curves and `kivymd` for consistent theming.
- Consider optional `pyopengltk` integration for waveform and spectrum visualizations requiring GPU acceleration.

### Tooling & Dev Experience
- Adopt `poetry` for dependency management to accommodate mixed Python/native modules.
- Static analysis via `ruff` + `mypy` per Plan §9.
- Documentation generation handled by `mkdocs` with Material theme; architecture diagrams embedded via `mermaid` Markdown.

## 4. Threading & Concurrency Model
1. **Audio Thread** – High-priority callback processing audio blocks; receives immutable snapshots of module parameters per buffer.
2. **Sequencer Thread** – Maintains musical timeline, quantizes incoming controller events, and prepares event packets for the audio thread.
3. **UI/Main Thread** – Handles rendering and user input; dispatches commands asynchronously.
4. **I/O Worker Pool** – Dedicated workers for sample loading, project serialization, and background rendering to avoid blocking UI/Audio threads.
5. **Inter-thread Communication** – Employ lock-free ring buffers (via `sounddevice` shared memory) and concurrent queues from `janus` to shuttle messages; all operations favor batched updates to reduce contention.

## 5. Data Persistence Strategy
- **Project Files:** JSON manifest referencing external assets stored under `Projects/<ProjectName>/assets/`. Include version metadata and migration hooks.
- **Instrument Presets:** YAML or JSON per instrument, zipped with preview audio for distribution. Maintain semantic versioning of module schemas.
- **Samples:** Managed via hashed filenames with deduplication index; optional embedded metadata (loop points, root note).
- **Automation Data:** Stored as compressed binary (e.g., `numpy` arrays) for efficient interpolation while providing JSON fallbacks for diffability during collaboration.

## 6. Integration Points
- **MIDI/OSC:** Provide device discovery services, mapping storage, and clock synchronization with Ableton Link compatibility as a stretch goal.
- **External Assets:** Implement sandboxed importers with checksum validation to protect against malformed sample libraries.
- **Testing Hooks:** Allow headless engine execution for CI by mocking audio driver and capturing rendered buffers to verify determinism.

## 7. Preliminary API Contracts
- `AudioModule`: abstract base with lifecycle methods `prepare(sample_rate)`, `process(buffer, events)`, `set_parameter(name, value)`.
- `SequencerService`: exposes `schedule_event(event)`, `render_block(num_ticks)`, `get_state_snapshot()` for UI binding.
- `ProjectRepository`: CRUD interface for loading/saving projects, with dependency-injected storage adapters for local/cloud backends.
- `ControllerMapper`: manages device profiles, provides `learn(parameter_id)` and `apply(event)` entry points.

## 8. Risk Assessment & Mitigations
- **Latency Regression:** Mitigate with profiling harness capturing buffer underruns; escalate high-risk modules to native code promptly.
- **Concurrency Bugs:** Enforce message immutability and adopt extensive unit tests around ring buffer implementations.
- **Library Obsolescence:** Track upstream status of Kivy and sounddevice; maintain adapter layer to swap drivers if platform support degrades.
- **Complex Serialization:** Start with human-readable formats, introduce binary packing only after establishing automated migration tests.

## 9. Next Actions
1. Prototype minimal audio engine loop using `sounddevice` and placeholder oscillator modules.
2. Draft `pydantic` models for project, pattern, and instrument schemas in a new `src/domain/` package.
3. Establish `poetry` configuration and baseline CI workflow (lint + docs build).
4. Begin drafting architecture diagrams (component and sequence) for inclusion under `docs/assets/` per documentation guide.

These decisions align the project with the Comprehensive Development Plan and unblock implementation work for Steps 3–5.
