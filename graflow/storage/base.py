"""
Base mixin for Django-specific PostgreSQL connections.
"""

from typing import Any, Protocol, TypeVar, cast
from urllib.parse import quote_plus

from django.conf import settings
from psycopg import Connection, Pipeline
from psycopg.rows import dict_row

# Protocol for context manager cleanup
_Conn = TypeVar("_Conn")


class HasConnectionAndPipeline(Protocol[_Conn]):
    """Protocol for objects with connection and pipeline attributes."""

    conn: _Conn
    pipe: Pipeline | None


class DjangoConnectionMixin:
    """
    Mixin that provides Django database connection setup and context management.

    This mixin handles:
    - Creating PostgreSQL connections from Django settings
    - Supporting both regular connections and Unix socket paths
    - Pipeline mode initialization
    - Context manager support (cleanup of connections and pipelines)

    Classes using this mixin should:
    1. Call `_setup_django_connection()` in their `__init__` method
    2. Set `self.conn` and `self.pipe` attributes (done by the mixin)
    3. Pass `class_name` for error messages
    """

    def _setup_django_connection(self, *, pipeline: bool = False, class_name: str = "") -> None:
        """
        Set up PostgreSQL connection from Django settings.

        Args:
            pipeline: Whether to use pipeline mode. Defaults to False.
            class_name: Class name for error messages (e.g., "DjangoSaver").

        Raises:
            ValueError: If database engine is not PostgreSQL.
        """
        # Get database settings from Django
        db_settings = settings.DATABASES["default"]

        # Validate that we're using PostgreSQL
        engine = db_settings["ENGINE"]
        if "postgresql" not in engine:
            error_msg = (
                f"{class_name} only supports PostgreSQL databases"
                if class_name
                else "Only PostgreSQL databases are supported"
            )
            raise ValueError(error_msg)

        # Build connection string from Django settings
        user = cast(str, db_settings["USER"])
        host = cast(str, db_settings.get("HOST") or "localhost")
        port = cast(str, db_settings.get("PORT") or "5432")
        name = cast(str, db_settings["NAME"])

        if host.startswith("/"):  # Unix socket path (e.g., /cloudsql/...)
            password = cast(str, db_settings.get("PASSWORD") or "")
            self.conn = Connection.connect(  # type: ignore[assignment, misc]
                dbname=name,
                user=user,
                password=password,
                host=host,
                autocommit=True,
                prepare_threshold=0,
                row_factory=dict_row,
            )
        else:
            password = quote_plus(
                cast(str, db_settings.get("PASSWORD") or "")
            )  # URL-encode password
            # Add SSL mode if specified
            options = cast(dict[str, Any], db_settings.get("OPTIONS", {}))
            ssl_mode = cast(str, options.get("sslmode", "disable"))
            conn_string = f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={ssl_mode}"

            # Create connection
            self.conn = Connection.connect(  # type: ignore[assignment, misc]
                conn_string, autocommit=True, prepare_threshold=0, row_factory=dict_row
            )

        # Initialize pipeline if requested
        self.pipe: Pipeline | None = None
        if pipeline:
            self.pipe = self.conn.pipeline()  # type: ignore[assignment, misc]

    def setup(self) -> None:
        """
        Do nothing.

        NOTE: There is no need to call setup() of the parent class because we are
        using Django migrations.
        """
        pass

    def __enter__(self) -> "DjangoConnectionMixin":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup connection and pipeline."""
        if self.pipe:
            self.pipe.close()  # type: ignore[attr-defined]
        self.conn.close()

    @classmethod
    def _cleanup_context_manager(cls, instance: HasConnectionAndPipeline[Any]) -> None:
        """
        Helper method to cleanup connection and pipeline in context managers.

        This is used by class-level context manager methods like `from_django_settings`.

        Args:
            instance: Instance with `conn` and `pipe` attributes.
        """
        if instance.pipe:
            instance.pipe.close()  # type: ignore[attr-defined]
        instance.conn.close()
