import pytest

from audio.node_graph import Connection, NodeDefinition, NodeGraph, NodeInstance, NodePort


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
