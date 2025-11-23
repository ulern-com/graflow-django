"""
Django-specific PostgreSQL store that uses Django database settings.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig, TTLConfig

from graflow.storage.base import DjangoConnectionMixin

logger = logging.getLogger(__name__)


class DjangoStore(DjangoConnectionMixin, PostgresStore):  # type: ignore[misc]
    """
    Django-specific PostgreSQL store.

    This class inherits all functionality from PostgresStore but automatically
    gets database connection settings from Django settings instead of requiring
    a connection string to be passed manually.
    """

    def __init__(
        self,
        *,
        pipeline: bool = False,
        deserializer: Callable[[bytes], dict[str, Any]] | None = None,
        index: PostgresIndexConfig | None = None,
        ttl: TTLConfig | None = None,
    ) -> None:
        """
        Initialize DjangoStore with Django database settings.

        Args:
            pipeline: Whether to use pipeline mode. Defaults to False.
            deserializer: Optional deserializer function. Defaults to None.
            index: Optional index configuration for vector search. Defaults to None.
            ttl: Optional TTL configuration. Defaults to None.
        """
        # Set up connection using mixin
        self._setup_django_connection(pipeline=pipeline, class_name="DjangoStore")

        # Call parent constructor
        super().__init__(self.conn, pipe=self.pipe, deserializer=deserializer, index=index, ttl=ttl)

    @classmethod
    @contextmanager
    def from_django_settings(
        cls,
        *,
        pipeline: bool = False,
        deserializer: Callable[[bytes], dict[str, Any]] | None = None,
        index: PostgresIndexConfig | None = None,
        ttl: TTLConfig | None = None,
    ) -> Iterator["DjangoStore"]:
        """
        Create a DjangoStore instance using Django database settings.

        Args:
            pipeline: Whether to use pipeline mode. Defaults to False.
            deserializer: Optional deserializer function. Defaults to None.
            index: Optional index configuration for vector search. Defaults to None.
            ttl: Optional TTL configuration. Defaults to None.

        Yields:
            DjangoStore: A new DjangoStore instance.
        """
        store = cls(pipeline=pipeline, deserializer=deserializer, index=index, ttl=ttl)
        try:
            yield store
        finally:
            cls._cleanup_context_manager(store)
