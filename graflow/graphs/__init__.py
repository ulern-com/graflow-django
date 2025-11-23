"""
Graph building utilities and registry for Graflow.
"""

__all__ = [
    "BaseGraphState",
    "data_receiver",
    "FlowStateGraph",
    "register_graph",
    "get_graph",
    "get_graph_state_definition",
    "get_latest_graph_version",
]


def __getattr__(name):
    """Lazy import to avoid circular dependencies."""
    if name == "BaseGraphState" or name == "data_receiver":
        from graflow.graphs.base import BaseGraphState, data_receiver

        if name == "BaseGraphState":
            return BaseGraphState
        return data_receiver
    elif name == "FlowStateGraph":
        from graflow.graphs.flow_state_graph import FlowStateGraph

        return FlowStateGraph
    elif name in (
        "register_graph",
        "get_graph",
        "get_graph_state_definition",
        "get_latest_graph_version",
    ):
        from graflow.graphs.registry import (
            get_graph,
            get_graph_state_definition,
            get_latest_graph_version,
            register_graph,
        )

        return {
            "register_graph": register_graph,
            "get_graph": get_graph,
            "get_graph_state_definition": get_graph_state_definition,
            "get_latest_graph_version": get_latest_graph_version,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
