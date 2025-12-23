import logging
from typing import TYPE_CHECKING

from django.db import models
from langgraph.graph import StateGraph
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


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
        raise ValueError(
            f"Invalid path format '{path}'. Expected 'module.path:attribute'"
        ) from e

    try:
        module = __import__(module_path, fromlist=[attr_name])
        attr = getattr(module, attr_name)
        return attr
    except ImportError as e:
        raise ValueError(f"Failed to import module '{module_path}': {e}") from e
    except AttributeError as e:
        raise ValueError(
            f"Module '{module_path}' has no attribute '{attr_name}'"
        ) from e


class FlowTypeQuerySet(models.QuerySet):
    """Custom QuerySet for FlowType with additional filtering methods."""

    def get_latest(self, app_name: str, flow_type: str) -> "FlowType | None":
        """
        Get the latest active version of a flow type.

        Args:
            app_name: The application name
            flow_type: The type of the flow

        Returns:
            FlowType instance if found, None otherwise
        """
        return self.filter(
            app_name=app_name, flow_type=flow_type, is_latest=True, is_active=True
        ).first()

    def for_app(self, app_name: str):
        """
        Filter flow types by application name.

        Args:
            app_name: The application name

        Returns:
            FlowTypeQuerySet: Filtered queryset (chainable)
        """
        return self.filter(app_name=app_name)

    def active(self):
        """
        Filter for active flow types only.

        Returns:
            FlowTypeQuerySet: Filtered queryset (chainable)
        """
        return self.filter(is_active=True)


class FlowType(models.Model):
    """
    Model-based registry for flow types (graphs).

    Replaces the in-memory registry with database-backed management.
    Supports multi-tenancy via app_name and per-flow-type permissions/throttling.
    """

    # Core identification (unique together)
    app_name = models.CharField(max_length=255, db_index=True, help_text="Application name")
    flow_type = models.CharField(
        max_length=255, db_index=True, help_text="Type of the flow (e.g., 'hello_world')"
    )
    version = models.CharField(
        max_length=50, help_text="Version string (e.g., 'v1', '1.0.0', 'beta')"
    )

    # Graph definition (string paths to import)
    builder_path = models.CharField(
        max_length=500,
        help_text="Path to builder function (e.g., 'myapp.graphs:build_graph')",
    )
    state_path = models.CharField(
        max_length=500,
        help_text="Path to state class (e.g., 'myapp.graphs:GraphState')",
    )

    # Versioning and status
    is_latest = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this is the latest version of this flow type",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this flow type is active and can be used",
    )

    # Metadata
    display_name = models.CharField(
        max_length=255, blank=True, help_text="Human-readable name for this flow type"
    )
    description = models.TextField(blank=True, help_text="Description of this flow type")

    # Permissions (string paths to permission classes)
    crud_permission_class = models.CharField(
        max_length=500,
        default="rest_framework.permissions.IsAuthenticated",
        help_text=(
            "Permission class path for CRUD operations "
            "(e.g., 'myapp.permissions:CustomPermission')"
        ),
    )
    resume_permission_class = models.CharField(
        max_length=500,
        default="rest_framework.permissions.IsAuthenticated",
        help_text=(
            "Permission class path for resume operations "
            "(e.g., 'myapp.permissions:CustomPermission')"
        ),
    )

    # Throttling (string paths to throttle classes)
    crud_throttle_class = models.CharField(
        max_length=500,
        blank=True,
        help_text=(
            "Throttle class path for CRUD operations "
            "(e.g., 'myapp.throttling:PremiumThrottle'). "
            "Optional - uses default viewset throttling if blank."
        ),
    )
    resume_throttle_class = models.CharField(
        max_length=500,
        blank=True,
        help_text=(
            "Throttle class path for resume operations "
            "(e.g., 'myapp.throttling:BasicThrottle'). "
            "Optional - uses default viewset throttling if blank."
        ),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FlowTypeQuerySet.as_manager()

    class Meta:
        db_table = "graflow_flow_type"
        unique_together = [["app_name", "flow_type", "version"]]
        indexes = [
            # For finding latest version when creating flows
            models.Index(
                fields=["app_name", "flow_type", "is_latest", "is_active"],
                name="graflow_flowtype_latest_idx",
            ),
        ]
        constraints = [
            # Ensure only one latest version per (app_name, flow_type)
            models.UniqueConstraint(
                fields=["app_name", "flow_type"],
                condition=models.Q(is_latest=True),
                name="graflow_flowtype_one_latest_per_app_type",
            ),
        ]

    def __str__(self):
        return f"{self.app_name}:{self.flow_type}:{self.version}"

    def get_builder(self) -> "Callable[[], StateGraph]":
        """
        Get the builder function for this flow type.

        Returns:
            Callable that builds and returns a StateGraph

        Raises:
            ValueError: If builder function cannot be imported or is invalid
        """
        builder_func = _import_from_string(self.builder_path)
        if not callable(builder_func):
            raise ValueError(
                f"Builder path '{self.builder_path}' does not resolve to a callable"
            )
        return builder_func

    def get_state_definition(self) -> type[BaseModel]:
        """
        Get the state definition class for this flow type.

        Returns:
            Pydantic BaseModel class defining the graph state

        Raises:
            ValueError: If state class cannot be imported or is invalid
        """
        state_class = _import_from_string(self.state_path)
        if not isinstance(state_class, type) or not issubclass(state_class, BaseModel):
            raise ValueError(
                f"State path '{self.state_path}' does not resolve to a Pydantic BaseModel class"
            )
        return state_class

    def get_graph(self) -> StateGraph:
        """
        Get the compiled graph for this flow type.

        The graph is compiled with storage components (cache, checkpointer, store)
        and configured with a run name based on the flow type identifiers.

        Returns:
            Compiled StateGraph ready for execution

        Raises:
            ValueError: If graph build function is not found or build fails
        """
        from graflow.storage import get_storage_components

        try:
            builder_func = self.get_builder()
            node_cache, checkpointer, store = get_storage_components()

            graph = (
                builder_func()
                .compile(
                    cache=node_cache,
                    checkpointer=checkpointer,
                    store=store,
                )
                .with_config({"run_name": f"{self.app_name}_{self.flow_type}_{self.version}"})
            )
            return graph  # type: ignore[return-value]
        except Exception as e:
            raise ValueError(
                f"Error building graph {self.app_name}:{self.flow_type}:{self.version}: {e}"
            ) from e
