"""Node-graph primitives for the Step 5 instrument builder prototype."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Set


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


__all__ = [
    "NodePort",
    "NodeDefinition",
    "NodeInstance",
    "Connection",
    "NodeGraph",
]
