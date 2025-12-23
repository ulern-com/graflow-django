"""
Storage components for LangGraph graphs.

This module provides utilities to get storage components (cache, checkpointer, store)
needed for compiling LangGraph graphs with persistence.
"""

from django.conf import settings
from dotenv import load_dotenv
from langgraph.cache.memory import InMemoryCache
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from graflow.storage.cache import DjangoCache
from graflow.storage.checkpointer import DjangoSaver
from graflow.storage.store import DjangoStore

# Lazy initialization of storage components
# This ensures they're only created when needed, after Django has set up the database
_node_cache = None
_checkpointer = None
_store = None


def _prepare_storage():
    """
    Prepare the storage components for the graph.

    This function creates Django-based storage components (cache, checkpointer, store).
    """
    load_dotenv()

    node_cache = DjangoCache()
    checkpointer = DjangoSaver()
    store = DjangoStore()
    return node_cache, checkpointer, store


def get_storage_components():
    """
    Get storage components (cache, checkpointer, store) for LangGraph graphs.

    Returns a tuple of (node_cache, checkpointer, store) that can be used
    to compile LangGraph graphs with persistence.

    The components are lazily initialized and cached for performance.
    The backend (Django or in-memory) is determined by the
    GRAFLOW_PERSISTENCE_BACKEND setting.

    Returns:
        tuple: (node_cache, checkpointer, store) - The three storage components
               needed to compile LangGraph graphs with persistence.

    Example:
        >>> node_cache, checkpointer, store = get_storage_components()
        >>> graph = builder_func().compile(
        ...     cache=node_cache,
        ...     checkpointer=checkpointer,
        ...     store=store,
        ... )
    """
    global _node_cache, _checkpointer, _store
    if _node_cache is None or _checkpointer is None or _store is None:
        # Use getattr with default to safely access settings
        persistence_backend = getattr(settings, "GRAFLOW_PERSISTENCE_BACKEND", "django")
        if persistence_backend == "django":
            _node_cache, _checkpointer, _store = _prepare_storage()
        else:
            _node_cache = InMemoryCache()
            _checkpointer = MemorySaver()
            _store = InMemoryStore()
    return _node_cache, _checkpointer, _store

