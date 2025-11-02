# Step 2 Architecture Diagrams

This document supplements `docs/step2_architecture_tech_choices.md` by providing visual assets that align with the Comprehensive Development Plan outlined in the repository README. Each diagram is stored as a Mermaid source file within `docs/assets/` to keep version control diff-friendly and allow automated rendering in future documentation tooling.

## Component Overview

```mermaid
%%{init: {"theme": "neutral"}}%%
flowchart TD
    subgraph Client[Client Layer]
        GUI[Kivy Multi-touch GUI]
        Controllers[MIDI/OSC Controllers]
    end

    subgraph AppCore[Application Core]
        Sequencer[Sequencer & Pattern Engine]
        NodeBuilder[Node-based Instrument Builder]
        Mixer[Mixer & Routing]
        ProjectState[State & Persistence]
    end

    subgraph AudioEngine[Real-time Audio Engine]
        Dispatcher[Event Dispatcher]
        ModuleGraph[Module Graph]
        DSP[DSP Modules]
    end

    Storage[(Project Files / Assets)]
    ExternalIO[(External Services / Plugins / Sample Libraries)]

    GUI --> Sequencer
    GUI --> NodeBuilder
    GUI --> Mixer
    Controllers -->|MIDI/OSC| Dispatcher
    Sequencer -->|Events| Dispatcher
    Dispatcher --> ModuleGraph
    ModuleGraph --> DSP
    DSP -->|Audio Buffers| Mixer
    Mixer -->|Rendered Audio| Client
    ProjectState --> Storage
    ProjectState --> Sequencer
    ProjectState --> NodeBuilder
    ProjectState --> Mixer
    Storage -->|Load/Save| ProjectState
    ExternalIO -->|Import/Export| ProjectState
    ExternalIO -->|Controller Mapping| Controllers
```

*Source:* `docs/assets/component_overview.mmd`

## Sequencer to Audio Callback Sequence

```mermaid
sequenceDiagram
    participant GUI as Kivy GUI
    participant Seq as Sequencer Engine
    participant Disp as Event Dispatcher
    participant AE as Audio Engine
    participant SD as Sound Backend

    GUI->>Seq: Edit pattern / transport events
    Seq-->>Disp: Schedule note/automation events
    loop Audio Block
        AE->>Disp: Pull due events (buffer horizon)
        Disp-->>AE: Batched events
        AE->>AE: Apply parameter updates
        AE->>AE: Render module graph
        AE-->>SD: Submit audio buffer
        SD-->>AE: Callback confirmation
    end
    SD-->>GUI: Metering / transport feedback
```

*Source:* `docs/assets/sequence_audio_callback.mmd`

## Next Steps

- Export these Mermaid diagrams to SVG/PNG assets when preparing external documentation bundles.
- Extend the sequence diagram set with failure scenarios (buffer underruns, module hot-swap) as prototypes mature.
- Keep controller routing visuals aligned with hardware mapping discoveries during Plan §5 prototyping.

## Audio Engine Failure Modes

```mermaid
%%{init: {"theme": "neutral"}}%%
flowchart TD
    subgraph Monitoring
        Metrics[Audio Metrics]
        Alerts[Alert Dispatcher]
    end

    subgraph Callback[Audio Callback]
        Render[Render Module Graph]
        Sleep[Simulated Load]
    end

    Dispatcher[Event Dispatcher]
    Sequencer[Sequencer Thread]
    Recovery[Recovery Actions]

    Sequencer -->|Events| Dispatcher
    Dispatcher --> Render
    Render --> Sleep
    Sleep --> Metrics
    Metrics -->|Underrun Threshold| Alerts
    Alerts --> Recovery
    Recovery -->|Adjust Block Size / Notify UI| Sequencer
```

*Source:* `docs/assets/audio_failure_modes.mmd`

## Controller Routing Overview

```mermaid
%%{init: {"theme": "neutral"}}%%
flowchart LR
    Controllers[MIDI / OSC Controllers]
    Discovery[Device Discovery]
    Mapper[Controller Mapper]
    Profiles[Profile Library]
    Sequencer[Sequencer Commands]
    Instrument[Instrument Parameters]
    Feedback[Visual / Haptic Feedback]

    Controllers --> Discovery
    Discovery --> Mapper
    Mapper --> Profiles
    Profiles --> Mapper
    Mapper --> Sequencer
    Mapper --> Instrument
    Sequencer --> Feedback
    Instrument --> Feedback
    Feedback --> Controllers
```

*Source:* `docs/assets/controller_routing.mmd`
