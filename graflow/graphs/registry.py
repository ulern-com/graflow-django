import logging
from collections.abc import Callable

from django.conf import settings
from dotenv import load_dotenv
from langgraph.cache.memory import InMemoryCache
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel

from graflow.storage.cache import DjangoCache
from graflow.storage.checkpointer import DjangoSaver
from graflow.storage.store import DjangoStore

logger = logging.getLogger(__name__)

# Global registries
_GRAPH_REGISTRY: dict[tuple[str, str, str], Callable[[], StateGraph]] = {}
_GRAPH_STATE_REGISTRY: dict[tuple[str, str, str], type[BaseModel]] = {}
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
        persistence_backend = getattr(settings, "GRAFLOW_PERSISTENCE_BACKEND", "django")
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
    state_class: type[BaseModel],
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


def get_graph(flow_type: str, app_name: str, version: str | None = None) -> StateGraph | None:
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
        return graph  # type: ignore[return-value]
    except Exception as e:
        raise ValueError(f"Error building graph {app_name}:{flow_type}:{version}: {e}") from e


def get_graph_state_definition(
    flow_type: str, app_name: str, version: str | None = None
) -> type[BaseModel] | None:
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


def _import_from_string(path: str):
    """
    Import a class or function from a string path.

    Args:
        path: String in format "module.path:attribute"

    Returns:
        The imported class or function

    Raises:
        ValueError: If path format is invalid or import fails
    """
    try:
        module_path, attr_name = path.rsplit(":", 1)
    except ValueError as e:
        raise ValueError(f"Invalid path format '{path}'. Expected 'module.path:attribute'") from e

    try:
        module = __import__(module_path, fromlist=[attr_name])
        attr = getattr(module, attr_name)
        return attr
    except ImportError as e:
        raise ValueError(f"Failed to import module '{module_path}': {e}") from e
    except AttributeError as e:
        raise ValueError(f"Module '{module_path}' has no attribute '{attr_name}'") from e


def register_graphs_from_settings():
    """
    Register graphs defined in Django settings.

    Expects GRAFLOW_GRAPHS setting to be a list of dictionaries, each containing:
        - app_name: Application name
        - flow_type: Flow type identifier
        - version: Version string
        - builder: String path to builder function (e.g., "myapp.graphs:build_graph")
        - state: String path to state class (e.g., "myapp.graphs:GraphState")
        - is_latest: Boolean, whether this is the latest version (default: True)

    Example:
        GRAFLOW_GRAPHS = [
            {
                'app_name': 'myflows',
                'flow_type': 'workflow_a',
                'version': 'v1',
                'builder': 'myapp.graphs.workflow:build_workflow_a',
                'state': 'myapp.graphs.workflow:WorkflowAState',
                'is_latest': True,
            },
        ]
    """
    graphs_config = getattr(settings, "GRAFLOW_GRAPHS", [])
    if not graphs_config:
        return

    registered = []
    errors = []

    for config in graphs_config:
        try:
            app_name = config["app_name"]
            flow_type = config["flow_type"]
            version = config["version"]
            builder_path = config["builder"]
            state_path = config["state"]
            is_latest = config.get("is_latest", True)

            # Import builder function and state class
            builder_func = _import_from_string(builder_path)
            state_class = _import_from_string(state_path)

            # Register the graph
            register_graph(
                app_name=app_name,
                flow_type=flow_type,
                version=version,
                builder_func=builder_func,
                state_class=state_class,
                is_latest=is_latest,
            )

            registered.append(f"{app_name}:{flow_type}:{version}")
            logger.info(f"Registered graph from settings: {app_name}:{flow_type}:{version}")

        except KeyError as e:
            errors.append(f"Missing required key in graph config: {e}")
        except ValueError as e:
            errors.append(f"Invalid graph config: {e}")
        except Exception as e:
            errors.append(f"Error registering graph: {e}")
            logger.exception(f"Failed to register graph from config {config}")

    if errors:
        error_msg = "Errors registering graphs from settings:\n" + "\n".join(
            f"  - {e}" for e in errors
        )
        logger.error(error_msg)
        # Raise if in strict mode, or just log in development
        if getattr(settings, "GRAFLOW_STRICT_GRAPH_REGISTRATION", False):
            raise ValueError(error_msg)

    if registered:
        logger.info(
            f"Successfully registered {len(registered)} graph(s) from settings: "
            f"{', '.join(registered)}"
        )
