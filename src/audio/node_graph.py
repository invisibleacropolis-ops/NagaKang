"""Node-graph primitives for the Step 5 instrument builder prototype."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, MutableMapping, Protocol, Sequence, Set


class NodeGraphCommand(Protocol):
    """Command contract for undoable graph edits."""

    def apply(self, graph: "NodeGraph") -> None:
        """Apply the command to *graph*."""

    def undo(self, graph: "NodeGraph") -> None:
        """Revert the effects of :meth:`apply`."""


@dataclass(frozen=True)
class NodePort:
    """Named port attached to a node definition."""

    name: str
    kind: str = "audio"

    def to_dict(self) -> dict[str, str]:
        """Return a serialisable representation of the port."""

        return {"name": self.name, "kind": self.kind}


@dataclass
class NodeDefinition:
    """Reusable node definition shared across instances."""

    type: str
    label: str
    inputs: Sequence[NodePort] = field(default_factory=tuple)
    outputs: Sequence[NodePort] = field(default_factory=tuple)
    parameter_defaults: Mapping[str, float] = field(default_factory=dict)

    def has_input(self, name: str) -> bool:
        return any(port.name == name for port in self.inputs)

    def has_output(self, name: str) -> bool:
        return any(port.name == name for port in self.outputs)

    def to_dict(self) -> dict[str, object]:
        """Return a serialisable definition description."""

        return {
            "type": self.type,
            "label": self.label,
            "inputs": [port.to_dict() for port in self.inputs],
            "outputs": [port.to_dict() for port in self.outputs],
            "parameter_defaults": dict(self.parameter_defaults),
        }


@dataclass
class NodeInstance:
    """Concrete node placement within a graph."""

    node_id: str
    definition: NodeDefinition
    parameter_values: MutableMapping[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Parameter helpers
    # ------------------------------------------------------------------

    def resolve_parameter(self, name: str) -> float | None:
        """Return the resolved parameter value including defaults."""

        if name in self.parameter_values:
            return float(self.parameter_values[name])
        if name in self.definition.parameter_defaults:
            return float(self.definition.parameter_defaults[name])
        return None

    def resolved_parameters(self) -> dict[str, float]:
        """Return merged parameter values (defaults overridden by instance)."""

        resolved = {key: float(value) for key, value in self.definition.parameter_defaults.items()}
        resolved.update({key: float(value) for key, value in self.parameter_values.items()})
        return resolved

    # ------------------------------------------------------------------
    # Copy helpers
    # ------------------------------------------------------------------
    def clone(
        self,
        *,
        node_id: str | None = None,
        definition: NodeDefinition | None = None,
        parameters: Mapping[str, float] | None = None,
    ) -> "NodeInstance":
        """Return a shallow copy optionally overriding identifiers/attributes."""

        return NodeInstance(
            node_id=node_id or self.node_id,
            definition=definition or self.definition,
            parameter_values=dict(parameters or self.parameter_values),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a serialisable node description."""

        return {
            "id": self.node_id,
            "type": self.definition.type,
            "label": self.definition.label,
            "parameters": self.resolved_parameters(),
        }


@dataclass(frozen=True)
class Connection:
    """Directed edge describing a connection between two node ports."""

    source_node: str
    source_port: str
    target_node: str
    target_port: str

    def to_dict(self) -> dict[str, str]:
        """Return a serialisable connection description."""

        return {
            "source_node": self.source_node,
            "source_port": self.source_port,
            "target_node": self.target_node,
            "target_port": self.target_port,
        }


class NodeGraph:
    """Mutable node graph supporting Step 5 node-builder experiments."""

    def __init__(self) -> None:
        self._nodes: Dict[str, NodeInstance] = {}
        self._connections: Set[Connection] = set()

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------
    def add_node(self, node: NodeInstance) -> None:
        """Insert a node instance into the graph."""

        if node.node_id in self._nodes:
            raise ValueError(f"Node {node.node_id!r} already exists")
        self._nodes[node.node_id] = node

    def remove_node(self, node_id: str) -> None:
        """Remove a node and any attached connections."""

        if node_id not in self._nodes:
            raise KeyError(f"Unknown node {node_id!r}")
        del self._nodes[node_id]
        self._connections = {
            connection
            for connection in self._connections
            if connection.source_node != node_id and connection.target_node != node_id
        }

    def node(self, node_id: str) -> NodeInstance:
        """Return a node instance by identifier."""

        return self._nodes[node_id]

    def nodes(self) -> List[NodeInstance]:
        """Return all nodes sorted by identifier."""

        return [self._nodes[node_id] for node_id in sorted(self._nodes.keys())]

    def duplicate_node(
        self,
        node_id: str,
        new_node_id: str,
        *,
        copy_connections: bool = False,
        include_incoming: bool = True,
        include_outgoing: bool = True,
    ) -> tuple[NodeInstance, List[Connection]]:
        """Duplicate *node_id* and optionally mirror its connections.

        Returns the newly inserted node and any additional connections created as
        part of the duplication. The caller can feed the returned artefacts into
        undo stacks or inspector views.
        """

        if node_id not in self._nodes:
            raise KeyError(f"Unknown node {node_id!r}")
        if new_node_id in self._nodes:
            raise ValueError(f"Node {new_node_id!r} already exists")

        original = self._nodes[node_id]
        duplicate = original.clone(node_id=new_node_id)
        self.add_node(duplicate)

        created_connections: List[Connection] = []
        if copy_connections:
            if include_outgoing:
                for connection in self.downstream(node_id):
                    if duplicate.definition.has_output(connection.source_port):
                        created_connections.append(
                            self.connect(new_node_id, connection.source_port, connection.target_node, connection.target_port)
                        )
            if include_incoming:
                for connection in self.upstream(node_id):
                    if duplicate.definition.has_input(connection.target_port):
                        created_connections.append(
                            self.connect(connection.source_node, connection.source_port, new_node_id, connection.target_port)
                        )

        return duplicate, created_connections

    def replace_node_definition(
        self,
        node_id: str,
        new_definition: NodeDefinition,
        *,
        parameter_overrides: Mapping[str, float] | None = None,
        port_mapping: Mapping[str, str] | None = None,
    ) -> tuple[NodeDefinition, Mapping[str, float], List[Connection]]:
        """Swap a node definition while preserving compatible connections.

        Returns a tuple containing the previous definition, previous parameter
        overrides, and the full list of connections impacted by the change.
        """

        if node_id not in self._nodes:
            raise KeyError(f"Unknown node {node_id!r}")

        node = self._nodes[node_id]
        old_definition = node.definition
        old_parameters = dict(node.parameter_values)
        overrides = dict(parameter_overrides or {})
        mapping = dict(port_mapping or {})

        updated_connections: Set[Connection] = set()
        touched_connections: List[Connection] = []

        for connection in self._connections:
            source_node = connection.source_node
            source_port = connection.source_port
            target_node = connection.target_node
            target_port = connection.target_port

            changed = False
            if connection.source_node == node_id:
                mapped_port = mapping.get(source_port, source_port)
                if not new_definition.has_output(mapped_port):
                    raise KeyError(
                        f"Node {node_id!r} has no output port {mapped_port!r} in new definition"
                    )
                if mapped_port != source_port:
                    source_port = mapped_port
                    changed = True

            if connection.target_node == node_id:
                mapped_port = mapping.get(target_port, target_port)
                if not new_definition.has_input(mapped_port):
                    raise KeyError(
                        f"Node {node_id!r} has no input port {mapped_port!r} in new definition"
                    )
                if mapped_port != target_port:
                    target_port = mapped_port
                    changed = True

            new_connection = Connection(source_node, source_port, target_node, target_port)
            updated_connections.add(new_connection)
            if changed:
                touched_connections.append(new_connection)

        # Update node parameters, preserving values that still exist on the new definition.
        preserved_parameters = {
            name: float(value)
            for name, value in node.parameter_values.items()
            if name in new_definition.parameter_defaults
        }
        preserved_parameters.update({name: float(value) for name, value in overrides.items()})

        node.definition = new_definition
        node.parameter_values = preserved_parameters
        self._connections = updated_connections

        return old_definition, old_parameters, touched_connections

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> Connection:
        """Connect two node ports, returning the created connection."""

        if source_node not in self._nodes:
            raise KeyError(f"Unknown source node {source_node!r}")
        if target_node not in self._nodes:
            raise KeyError(f"Unknown target node {target_node!r}")
        if not self._nodes[source_node].definition.has_output(source_port):
            raise KeyError(f"Node {source_node!r} has no output port {source_port!r}")
        if not self._nodes[target_node].definition.has_input(target_port):
            raise KeyError(f"Node {target_node!r} has no input port {target_port!r}")
        connection = Connection(source_node, source_port, target_node, target_port)
        if connection in self._connections:
            return connection
        self._connections.add(connection)
        return connection

    def disconnect(self, connection: Connection) -> None:
        """Remove a previously created connection."""

        self._connections.discard(connection)

    def connections(self) -> List[Connection]:
        """Return all connections sorted for deterministic serialisation."""

        return sorted(
            self._connections,
            key=lambda conn: (conn.source_node, conn.source_port, conn.target_node, conn.target_port),
        )

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------
    def downstream(self, node_id: str) -> List[Connection]:
        """Return all connections sourced from the given node."""

        return [connection for connection in self._connections if connection.source_node == node_id]

    def upstream(self, node_id: str) -> List[Connection]:
        """Return all connections targeting the given node."""

        return [connection for connection in self._connections if connection.target_node == node_id]

    def topological_order(self) -> List[NodeInstance]:
        """Return nodes ordered by dependency, raising on cycles."""

        indegree: Dict[str, int] = {node_id: 0 for node_id in self._nodes}
        adjacency: Dict[str, Set[str]] = {node_id: set() for node_id in self._nodes}
        for connection in self._connections:
            adjacency[connection.source_node].add(connection.target_node)
            indegree[connection.target_node] += 1

        queue: List[str] = [node_id for node_id, count in indegree.items() if count == 0]
        order: List[NodeInstance] = []
        while queue:
            node_id = queue.pop(0)
            order.append(self._nodes[node_id])
            for neighbour in adjacency[node_id]:
                indegree[neighbour] -= 1
                if indegree[neighbour] == 0:
                    queue.append(neighbour)

        if len(order) != len(self._nodes):
            raise ValueError("Graph contains a cycle")
        return order

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    def serialize(self) -> dict[str, object]:
        """Return a serialisable snapshot of the graph."""

        return {
            "nodes": [node.to_dict() for node in self.nodes()],
            "connections": [connection.to_dict() for connection in self.connections()],
        }

    def parameter_matrix(self) -> dict[str, dict[str, float]]:
        """Return resolved parameter values keyed by node identifier."""

        return {node.node_id: node.resolved_parameters() for node in self.nodes()}


@dataclass
class AddNodeCommand:
    """Insert a node instance into a graph."""

    node: NodeInstance

    def apply(self, graph: NodeGraph) -> None:
        graph.add_node(self.node)

    def undo(self, graph: NodeGraph) -> None:
        graph.remove_node(self.node.node_id)


@dataclass
class RemoveNodeCommand:
    """Remove a node while capturing its previous state for undo."""

    node_id: str
    _snapshot: NodeInstance | None = field(default=None, init=False, repr=False)
    _connections: List[Connection] = field(default_factory=list, init=False, repr=False)

    def apply(self, graph: NodeGraph) -> None:
        node = graph.node(self.node_id)
        self._snapshot = node.clone()
        attached = {
            connection
            for connection in graph.connections()
            if connection.source_node == self.node_id or connection.target_node == self.node_id
        }
        self._connections = sorted(
            attached,
            key=lambda conn: (conn.source_node, conn.source_port, conn.target_node, conn.target_port),
        )
        graph.remove_node(self.node_id)

    def undo(self, graph: NodeGraph) -> None:
        if self._snapshot is None:
            raise RuntimeError("Command has not been applied")
        graph.add_node(self._snapshot.clone())
        for connection in self._connections:
            graph.connect(
                connection.source_node,
                connection.source_port,
                connection.target_node,
                connection.target_port,
            )


@dataclass
class ConnectNodesCommand:
    """Create a connection between two node ports."""

    source_node: str
    source_port: str
    target_node: str
    target_port: str
    _connection: Connection | None = field(default=None, init=False, repr=False)

    def apply(self, graph: NodeGraph) -> None:
        self._connection = graph.connect(
            self.source_node,
            self.source_port,
            self.target_node,
            self.target_port,
        )

    def undo(self, graph: NodeGraph) -> None:
        if self._connection is None:
            raise RuntimeError("Command has not been applied")
        graph.disconnect(self._connection)


@dataclass
class DuplicateNodeCommand:
    """Duplicate an existing node, optionally mirroring connections."""

    source_node: str
    new_node_id: str
    copy_connections: bool = False
    include_incoming: bool = True
    include_outgoing: bool = True
    _created_connections: List[Connection] = field(default_factory=list, init=False, repr=False)
    _snapshot: NodeInstance | None = field(default=None, init=False, repr=False)

    def apply(self, graph: NodeGraph) -> None:
        node, connections = graph.duplicate_node(
            self.source_node,
            self.new_node_id,
            copy_connections=self.copy_connections,
            include_incoming=self.include_incoming,
            include_outgoing=self.include_outgoing,
        )
        self._created_connections = connections
        self._snapshot = node

    def undo(self, graph: NodeGraph) -> None:
        graph.remove_node(self.new_node_id)
        self._created_connections.clear()
        self._snapshot = None


@dataclass
class ReplaceNodeCommand:
    """Swap a node definition with undo support."""

    node_id: str
    new_definition: NodeDefinition
    parameter_overrides: Mapping[str, float] | None = None
    port_mapping: Mapping[str, str] | None = None
    _previous_definition: NodeDefinition | None = field(default=None, init=False, repr=False)
    _previous_parameters: Mapping[str, float] | None = field(default=None, init=False, repr=False)
    _forward_mapping: Dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def apply(self, graph: NodeGraph) -> None:
        mapping = dict(self.port_mapping or {})
        previous_definition, previous_parameters, _ = graph.replace_node_definition(
            self.node_id,
            self.new_definition,
            parameter_overrides=self.parameter_overrides,
            port_mapping=mapping,
        )
        self._previous_definition = previous_definition
        self._previous_parameters = previous_parameters
        self._forward_mapping = mapping

    def undo(self, graph: NodeGraph) -> None:
        if self._previous_definition is None or self._previous_parameters is None:
            raise RuntimeError("Command has not been applied")
        reverse_mapping = {new: old for old, new in self._forward_mapping.items()}
        graph.replace_node_definition(
            self.node_id,
            self._previous_definition,
            parameter_overrides=self._previous_parameters,
            port_mapping=reverse_mapping,
        )


class NodeGraphEditor:
    """Undo/redo manager around :class:`NodeGraph`."""

    def __init__(self, graph: NodeGraph | None = None) -> None:
        self.graph = graph or NodeGraph()
        self._undo_stack: List[NodeGraphCommand] = []
        self._redo_stack: List[NodeGraphCommand] = []

    def apply(self, command: NodeGraphCommand) -> None:
        command.apply(self.graph)
        self._undo_stack.append(command)
        self._redo_stack.clear()

    def undo(self) -> NodeGraphCommand | None:
        if not self._undo_stack:
            return None
        command = self._undo_stack.pop()
        command.undo(self.graph)
        self._redo_stack.append(command)
        return command

    def redo(self) -> NodeGraphCommand | None:
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        command.apply(self.graph)
        self._undo_stack.append(command)
        return command

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)


__all__ = [
    "NodePort",
    "NodeDefinition",
    "NodeInstance",
    "Connection",
    "NodeGraph",
    "NodeGraphCommand",
    "AddNodeCommand",
    "RemoveNodeCommand",
    "ConnectNodesCommand",
    "DuplicateNodeCommand",
    "ReplaceNodeCommand",
    "NodeGraphEditor",
]
