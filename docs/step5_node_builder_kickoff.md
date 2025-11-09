# Step 5 Node Builder Kickoff – Graph Primitives

Step 5 shifts focus to the node-based instrument builder. This session establishes
lightweight data structures that map directly to the Comprehensive Development Plan
(README §5), ensuring upcoming Kivy graph prototypes have a stable foundation.

## Node graph building blocks

- `audio.node_graph.NodePort` captures reusable metadata for input/output ports,
  keeping port type descriptors close to the definitions that expose them.
- `audio.node_graph.NodeDefinition` stores the shared module blueprint (label,
  ports, and default parameters) so editor tooling can instantiate consistent
  nodes across graphs.
- `audio.node_graph.NodeInstance` merges definition defaults with per-instance
  overrides, exposing `resolved_parameters()` for inspector panels and engine
  serialization.
- `audio.node_graph.Connection` represents directed edges between node ports,
  providing deterministic serialization for upcoming project saves.
- `audio.node_graph.NodeGraph` tracks node instances, validates connections, and
  produces topological ordering / parameter matrices that align with the
  real-time engine scheduler planned in README §5.

## Next steps

1. Layer graph editing commands on top of `NodeGraph` (duplicate node, replace
   connections, mass parameter edits) so UI gestures can reuse battle-tested
   helpers.
2. Bind the graph primitives to a minimal Kivy view, rendering nodes, ports, and
   patch cables while feeding updates back into `NodeGraph`.
3. Integrate parameter automation scaffolding so the node builder can reflect
   envelope/LFO routings alongside audio/control connections.

## Graph editing helpers

With `audio.node_graph.NodeGraphEditor` the node builder now exposes
undo-friendly editing commands that keep UI gestures deterministic:

- `AddNodeCommand`, `RemoveNodeCommand`, and `ConnectNodesCommand` mirror core
  graph primitives while storing enough state to reverse the action.
- `DuplicateNodeCommand` clones node instances and can mirror incoming/outgoing
  connections, allowing quick instrument layering.
- `ReplaceNodeCommand` swaps definitions in place, remapping ports and
  parameter overrides so sound designers can iterate on module variants without
  rewiring the graph.

These commands will back the forthcoming Kivy gestures (tap-to-add, drag-to-wire,
context-menu duplicate) while keeping the underlying graph authoritative for
serialization.

## Kivy node-canvas binding plan

The first UI binding will wrap `NodeGraphEditor` inside a lightweight Kivy
controller:

1. **Data binding** – expose the editor's node/connection collections through a
   `ListProperty`/`DictProperty` bridge so Kivy widgets react to graph changes.
2. **Gesture translation** – map drag/drop gestures to command objects (e.g.
   connecting ports issues a `ConnectNodesCommand`, delete gestures trigger
   `RemoveNodeCommand`).
3. **Undo/redo chrome** – attach keyboard shortcuts and toolbar buttons to the
   editor's `undo()`/`redo()` helpers, surfacing stack state indicators in the
   UI for confidence during live editing.
4. **Inspector integration** – feed `NodeInstance.resolved_parameters()` into a
   property sheet widget so parameter tweaks stay in sync with command history
   and future automation overlays.

This plan keeps the editing workflow in line with the Comprehensive Development
Plan (README §5) while remaining approachable for remote collaborators.
