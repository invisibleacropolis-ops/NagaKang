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
