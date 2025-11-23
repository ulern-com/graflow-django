"""
LangGraph storage components for Django.
"""

__all__ = [
    "DjangoCache",
    "DjangoSaver",
    "DjangoStore",
    "create_cache_key",
    "create_cache_key_from_fields",
]


def __getattr__(name):
    """Lazy import to avoid circular dependencies."""
    if name in ("DjangoCache", "create_cache_key", "create_cache_key_from_fields"):
        from graflow.storage.cache import (
            DjangoCache,
            create_cache_key,
            create_cache_key_from_fields,
        )

        return {
            "DjangoCache": DjangoCache,
            "create_cache_key": create_cache_key,
            "create_cache_key_from_fields": create_cache_key_from_fields,
        }[name]
    elif name == "DjangoSaver":
        from graflow.storage.checkpointer import DjangoSaver

        return DjangoSaver
    elif name == "DjangoStore":
        from graflow.storage.store import DjangoStore

        return DjangoStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
