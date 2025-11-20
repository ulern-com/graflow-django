from typing import Callable, Type

from django.conf import settings
from langgraph.cache.memory import InMemoryCache
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel

# Global registries
_GRAPH_REGISTRY: dict[tuple[str, str, str], Callable[[], StateGraph]] = {}
_GRAPH_STATE_REGISTRY: dict[tuple[str, str, str], Type[BaseModel]] = {}
_LATEST_VERSIONS: dict[tuple[str, str], str] = {}

# Lazy initialization of persistence components
# This ensures they're only created when needed, after Django has set up the database
_node_cache = None
_checkpointer = None
_store = None


def _prepare_persistence():
    """
    Prepare the persistence for the graph.
    This function is defined here to avoid circular imports.
    """
    from dotenv import load_dotenv
    from graflow.storage.cache import DjangoCache
    from graflow.storage.checkpointer import DjangoSaver
    from graflow.storage.store import DjangoStore

    load_dotenv()

    node_cache = DjangoCache()
    checkpointer = DjangoSaver()
    store = DjangoStore()
    return node_cache, checkpointer, store


def _get_persistence():
    """Lazy initialization of persistence components."""
    global _node_cache, _checkpointer, _store
    if _node_cache is None or _checkpointer is None or _store is None:
        # Use getattr with default to safely access settings
        persistence_backend = getattr(settings, 'GRAFLOW_PERSISTENCE_BACKEND', 'django')
        if persistence_backend == "django":
            _node_cache, _checkpointer, _store = _prepare_persistence()
        else:
            _node_cache = InMemoryCache()
            _checkpointer = MemorySaver()
            _store = InMemoryStore()
    return _node_cache, _checkpointer, _store


def list_registered_graphs() -> list[dict[str, str]]:
    """
    Return metadata for all registered graphs.

    Each entry includes app_name, flow_type, and version.
    """
    return [
        {
            "app_name": app_name,
            "flow_type": flow_type,
            "version": version,
        }
        for app_name, flow_type, version in sorted(_GRAPH_REGISTRY.keys())
    ]


def register_graph(
    app_name: str,
    flow_type: str,
    version: str,
    builder_func: Callable[[], StateGraph],
    state_class: Type[BaseModel],
    is_latest: bool = True,
):
    """
    Register a graph with its builder function and state definition.

    Args:
        app_name: The application name
        flow_type: The type of the flow (e.g., "planning", "test_graph")
        version: The version string (e.g., "v1")
        builder_func: Function that builds and returns the StateGraph
        state_class: Pydantic BaseModel class defining the graph state
        is_latest: Whether this is the latest version of the graph
    """

    key = (app_name, flow_type, version)
    _GRAPH_REGISTRY[key] = builder_func
    _GRAPH_STATE_REGISTRY[key] = state_class

    if is_latest:
        _LATEST_VERSIONS[(app_name, flow_type)] = version


def get_latest_graph_version(flow_type: str, app_name: str) -> str | None:
    """
    Get the latest version of a graph.

    Args:
        flow_type: The type of the flow
        app_name: The application name

    Returns:
        The latest version string, or None if not found
    """
    key = (app_name, flow_type)
    return _LATEST_VERSIONS.get(key, None)


def get_graph(flow_type: str, app_name: str, version: str = None) -> StateGraph | None:
    """
    Get the graph with the given name and version.

    Args:
        flow_type: The type of the flow
        version: The version string (uses latest if None)
        app_name: The application name

    Returns:
        The compiled StateGraph, or None if not found

    Raises:
        ValueError: If graph build function is not found or build fails
    """
    if version is None:
        version = _LATEST_VERSIONS.get((app_name, flow_type), None)
    if version is None:
        return None
    key = (app_name, flow_type, version)
    build_func = _GRAPH_REGISTRY.get(key, None)
    if build_func is None:
        raise ValueError(f"No graph build function found for {app_name}:{flow_type}:{version}")
    try:
        # Build and compile the graph when requested
        # Lazy load persistence components to ensure database is ready
        node_cache, checkpointer, store = _get_persistence()
        graph = (
            build_func()
            .compile(
                cache=node_cache,
                checkpointer=checkpointer,
                store=store,
            )
            .with_config({"run_name": f"{app_name}_{flow_type}_{version}"})
        )
        return graph
    except Exception as e:
        raise ValueError(f"Error building graph {app_name}:{flow_type}:{version}: {e}")


def get_graph_state_definition(flow_type: str, app_name: str, version: str = None) -> type[BaseModel] | None:
    """
    Get the graph state definition with the given name and version.

    Args:
        flow_type: The type of the flow
        version: The version string (uses latest if None)
        app_name: The application name

    Returns:
        The Pydantic BaseModel class for the graph state, or None if not found

    Raises:
        ValueError: If graph state definition is not found
    """
    if version is None:
        version = _LATEST_VERSIONS.get((app_name, flow_type), None)
    if version is None:
        return None
    key = (app_name, flow_type, version)
    graph_state_definition = _GRAPH_STATE_REGISTRY.get(key, None)
    if graph_state_definition is None:
        raise ValueError(f"No graph state definition found for {app_name}:{flow_type}:{version}")
    return graph_state_definition
