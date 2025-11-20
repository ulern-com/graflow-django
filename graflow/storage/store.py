"""
Django-specific PostgreSQL store that uses Django database settings.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Callable, Optional, Union
from urllib.parse import quote_plus

import orjson
from django.conf import settings
from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig, TTLConfig
from psycopg import Connection
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


class DjangoStore(PostgresStore):
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
        deserializer: Optional[Callable[[Union[bytes, orjson.Fragment]], dict[str, Any]]] = None,
        index: Optional[PostgresIndexConfig] = None,
        ttl: Optional[TTLConfig] = None,
    ) -> None:
        """
        Initialize DjangoStore with Django database settings.

        Args:
            pipeline: Whether to use pipeline mode. Defaults to False.
            deserializer: Optional deserializer function. Defaults to None.
            index: Optional index configuration for vector search. Defaults to None.
            ttl: Optional TTL configuration. Defaults to None.
        """
        # Get database settings from Django
        db_settings = settings.DATABASES["default"]

        # Validate that we're using PostgreSQL
        engine = db_settings["ENGINE"]
        if "postgresql" not in engine:
            raise ValueError("DjangoStore only supports PostgreSQL databases")

        # Build connection string from Django settings
        user = db_settings["USER"]
        host = db_settings["HOST"] or "localhost"
        port = db_settings["PORT"] or "5432"
        name = db_settings["NAME"]

        if host.startswith("/"):  # Unix socket path (e.g., /cloudsql/...)
            password = db_settings["PASSWORD"]
            self.conn = Connection.connect(
                dbname=name,
                user=user,
                password=password,
                host=host,
                autocommit=True,
                prepare_threshold=0,
                row_factory=dict_row,
            )
        else:
            password = quote_plus(db_settings["PASSWORD"])  # URL-encode password
            # Add SSL mode if specified
            ssl_mode = db_settings.get("OPTIONS", {}).get("sslmode", "disable")
            conn_string = f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={ssl_mode}"

            # Create connection
            self.conn = Connection.connect(conn_string, autocommit=True, prepare_threshold=0, row_factory=dict_row)

        # Initialize pipeline if requested
        self.pipe = None
        if pipeline:
            self.pipe = self.conn.pipeline()

        # Call parent constructor
        super().__init__(self.conn, pipe=self.pipe, deserializer=deserializer, index=index, ttl=ttl)

    @classmethod
    @contextmanager
    def from_django_settings(
        cls,
        *,
        pipeline: bool = False,
        deserializer: Optional[Callable[[Union[bytes, orjson.Fragment]], dict[str, Any]]] = None,
        index: Optional[PostgresIndexConfig] = None,
        ttl: Optional[TTLConfig] = None,
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
            if store.pipe:
                store.pipe.close()
            store.conn.close()

    def setup(self) -> None:
        """
        Do nothing.

        NOTE: There is no need to call setup() of the parent class because we are using Django migrations.
        """
        pass

    def __enter__(self) -> "DjangoStore":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        if self.pipe:
            self.pipe.close()
        self.conn.close()
