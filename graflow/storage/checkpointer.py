"""
Django-specific checkpoint saver that uses Django database settings.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.base import SerializerProtocol

from graflow.storage.base import DjangoConnectionMixin


class DjangoSaver(DjangoConnectionMixin, PostgresSaver):  # type: ignore[misc]
    """
    Django-specific PostgreSQL checkpoint saver.

    This class inherits all functionality from PostgresSaver but automatically
    gets database connection settings from Django settings instead of requiring
    a connection string to be passed manually.
    """

    def __init__(
        self,
        *,
        serde: SerializerProtocol | None = None,
        pipeline: bool = False,
    ) -> None:
        """
        Initialize DjangoSaver with Django database settings.

        Args:
            serde: Optional serializer protocol.
            pipeline: Whether to use pipeline mode. Defaults to False.
        """
        # Set up connection using mixin
        self._setup_django_connection(pipeline=pipeline, class_name="DjangoSaver")

        # Call parent constructor
        super().__init__(self.conn, self.pipe, serde)

    @classmethod
    @contextmanager
    def from_django_settings(
        cls, *, pipeline: bool = False, serde: SerializerProtocol | None = None
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
            cls._cleanup_context_manager(saver)
