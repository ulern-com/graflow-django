"""
Django-specific checkpoint saver that uses Django database settings.
"""

from contextlib import contextmanager
from typing import Iterator, Optional
from urllib.parse import quote_plus

from django.conf import settings
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.base import SerializerProtocol
from psycopg import Connection
from psycopg.rows import dict_row


class DjangoSaver(PostgresSaver):
    """
    Django-specific PostgreSQL checkpoint saver.

    This class inherits all functionality from PostgresSaver but automatically
    gets database connection settings from Django settings instead of requiring
    a connection string to be passed manually.
    """

    def __init__(
        self,
        *,
        serde: Optional[SerializerProtocol] = None,
        pipeline: bool = False,
    ) -> None:
        """
        Initialize DjangoSaver with Django database settings.

        Args:
            serde: Optional serializer protocol.
            pipeline: Whether to use pipeline mode. Defaults to False.
        """
        # Get database settings from Django
        db_settings = settings.DATABASES["default"]

        # Validate that we're using PostgreSQL
        engine = db_settings["ENGINE"]
        if "postgresql" not in engine:
            raise ValueError("DjangoSaver only supports PostgreSQL databases")

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

            # Create connection and initialize parent
            self.conn = Connection.connect(conn_string, autocommit=True, prepare_threshold=0, row_factory=dict_row)

        # Initialize pipeline if requested
        self.pipe = None
        if pipeline:
            self.pipe = self.conn.pipeline()

        # Call parent constructor
        super().__init__(self.conn, self.pipe, serde)

    @classmethod
    @contextmanager
    def from_django_settings(
        cls, *, pipeline: bool = False, serde: Optional[SerializerProtocol] = None
    ) -> Iterator["DjangoSaver"]:
        """
        Create a DjangoSaver instance using Django database settings.

        Args:
            pipeline: Whether to use pipeline mode. Defaults to False.
            serde: Optional serializer protocol. Defaults to None.

        Yields:
            DjangoSaver: A new DjangoSaver instance.
        """
        saver = cls(serde=serde, pipeline=pipeline)
        try:
            yield saver
        finally:
            if saver.pipe:
                saver.pipe.close()
            saver.conn.close()

    def setup(self) -> None:
        """
        Do nothing.

        NOTE: There is no need to call setup() of the parent class because we are using Django migrations.
        """
        pass

    def __enter__(self) -> "DjangoSaver":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        if self.pipe:
            self.pipe.close()
        self.conn.close()
