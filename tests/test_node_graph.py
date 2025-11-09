import pytest

from audio.node_graph import (
    AddNodeCommand,
    Connection,
    ConnectNodesCommand,
    DuplicateNodeCommand,
    NodeDefinition,
    NodeGraph,
    NodeGraphEditor,
    NodeInstance,
    NodePort,
    RemoveNodeCommand,
    ReplaceNodeCommand,
)


def _make_definition(type_: str, *, inputs=None, outputs=None, defaults=None) -> NodeDefinition:
    return NodeDefinition(
        type=type_,
        label=type_.replace("_", " ").title(),
        inputs=tuple(inputs or []),
        outputs=tuple(outputs or []),
        parameter_defaults=dict(defaults or {}),
    )


def test_node_graph_orders_nodes_topologically():
    osc = _make_definition("osc", outputs=[NodePort("audio")], defaults={"frequency": 440.0})
    filter_def = _make_definition(
        "filter", inputs=[NodePort("signal")], outputs=[NodePort("audio")], defaults={"cutoff": 1200.0}
    )
    amp = _make_definition("amp", inputs=[NodePort("signal")])

    graph = NodeGraph()
    graph.add_node(NodeInstance("osc1", osc))
    graph.add_node(NodeInstance("filter1", filter_def, {"cutoff": 800.0}))
    graph.add_node(NodeInstance("amp1", amp))

    graph.connect("osc1", "audio", "filter1", "signal")
    graph.connect("filter1", "audio", "amp1", "signal")

    order = [node.node_id for node in graph.topological_order()]
    assert order == ["osc1", "filter1", "amp1"]

    matrix = graph.parameter_matrix()
    assert matrix["osc1"]["frequency"] == 440.0
    assert matrix["filter1"]["cutoff"] == 800.0

    payload = graph.serialize()
    assert {node["id"] for node in payload["nodes"]} == {"osc1", "filter1", "amp1"}
    assert len(payload["connections"]) == 2


def test_node_graph_rejects_invalid_connections():
    osc = _make_definition("osc", outputs=[NodePort("audio")])
    amp = _make_definition("amp", inputs=[NodePort("signal")])

    graph = NodeGraph()
    graph.add_node(NodeInstance("osc1", osc))
    graph.add_node(NodeInstance("amp1", amp))

    connection = graph.connect("osc1", "audio", "amp1", "signal")
    assert isinstance(connection, Connection)

    duplicate = graph.connect("osc1", "audio", "amp1", "signal")
    assert duplicate == connection

    graph.disconnect(connection)
    assert graph.connections() == []

    graph.connect("osc1", "audio", "amp1", "signal")
    with pytest.raises(KeyError):
        graph.connect("osc1", "missing", "amp1", "signal")
    with pytest.raises(KeyError):
        graph.connect("osc1", "audio", "amp1", "missing")


def test_node_graph_detects_cycles():
    osc = _make_definition("osc", inputs=[NodePort("audio")], outputs=[NodePort("audio")])
    amp = _make_definition("amp", inputs=[NodePort("signal")], outputs=[NodePort("audio")])

    graph = NodeGraph()
    graph.add_node(NodeInstance("osc1", osc))
    graph.add_node(NodeInstance("amp1", amp))

    graph.connect("osc1", "audio", "amp1", "signal")
    graph.connect("amp1", "audio", "osc1", "audio")

    with pytest.raises(ValueError):
        graph.topological_order()


def test_duplicate_node_with_connection_copy():
    osc = _make_definition("osc", outputs=[NodePort("audio")])
    amp = _make_definition("amp", inputs=[NodePort("signal")])

    graph = NodeGraph()
    graph.add_node(NodeInstance("osc1", osc))
    graph.add_node(NodeInstance("amp1", amp))
    graph.connect("osc1", "audio", "amp1", "signal")

    duplicate, connections = graph.duplicate_node("osc1", "osc2", copy_connections=True)

    assert duplicate.node_id == "osc2"
    assert duplicate.definition.type == "osc"
    assert connections[0].source_node == "osc2"
    assert connections[0].target_node == "amp1"
    assert len(graph.downstream("osc2")) == 1


def test_replace_node_definition_with_mapping():
    osc_v1 = _make_definition(
        "osc",
        outputs=[NodePort("audio")],
        defaults={"frequency": 440.0, "detune": 0.0},
    )
    osc_v2 = _make_definition(
        "osc",
        outputs=[NodePort("signal")],
        defaults={"frequency": 220.0, "detune": 0.0, "phase": 0.25},
    )
    amp = _make_definition("amp", inputs=[NodePort("signal")])

    graph = NodeGraph()
    graph.add_node(NodeInstance("osc1", osc_v1, {"frequency": 330.0}))
    graph.add_node(NodeInstance("amp1", amp))
    graph.connect("osc1", "audio", "amp1", "signal")

    previous_definition, previous_parameters, _ = graph.replace_node_definition(
        "osc1",
        osc_v2,
        parameter_overrides={"phase": 0.5},
        port_mapping={"audio": "signal"},
    )

    assert previous_definition is osc_v1
    assert previous_parameters == {"frequency": 330.0}

    connection = graph.downstream("osc1")[0]
    assert connection.source_port == "signal"
    assert graph.node("osc1").resolve_parameter("phase") == 0.5
    assert graph.node("osc1").resolve_parameter("frequency") == 330.0


def test_node_graph_editor_tracks_undo_redo():
    osc = _make_definition("osc", outputs=[NodePort("audio")])
    amp = _make_definition("amp", inputs=[NodePort("signal")])

    editor = NodeGraphEditor()
    editor.apply(AddNodeCommand(NodeInstance("osc1", osc)))
    editor.apply(AddNodeCommand(NodeInstance("amp1", amp)))
    editor.apply(
        ConnectNodesCommand(
            source_node="osc1",
            source_port="audio",
            target_node="amp1",
            target_port="signal",
        )
    )

    assert editor.graph.connections() != []
    assert editor.can_undo()

    editor.undo()
    assert editor.graph.connections() == []
    assert editor.can_redo()

    editor.redo()
    assert editor.graph.connections() != []


def test_editor_duplicate_and_remove_commands():
    osc = _make_definition("osc", outputs=[NodePort("audio")], defaults={"frequency": 440.0})
    amp = _make_definition("amp", inputs=[NodePort("signal")])

    editor = NodeGraphEditor()
    editor.apply(AddNodeCommand(NodeInstance("osc1", osc)))
    editor.apply(AddNodeCommand(NodeInstance("amp1", amp)))
    editor.apply(ConnectNodesCommand("osc1", "audio", "amp1", "signal"))

    editor.apply(DuplicateNodeCommand("osc1", "osc2", copy_connections=True, include_incoming=False))
    assert len(editor.graph.nodes()) == 3
    assert len(editor.graph.downstream("osc2")) == 1

    editor.apply(RemoveNodeCommand("osc2"))
    assert len(editor.graph.nodes()) == 2

    editor.undo()
    assert len(editor.graph.nodes()) == 3
    assert editor.graph.node("osc2").resolve_parameter("frequency") == 440.0

    editor.undo()
    assert len(editor.graph.nodes()) == 2
