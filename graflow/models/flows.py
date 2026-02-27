import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.functional import cached_property
from langgraph.types import Command

from graflow.models.registry import FlowType

logger = logging.getLogger(__name__)

User = get_user_model()

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

    UserType = AbstractUser


class FlowQuerySet(models.QuerySet):
    def for_user(self, user: "UserType"):
        """
        Filter flows by user.

        Args:
            user: User instance to filter by

        Returns:
            FlowQuerySet: Filtered queryset (chainable)
        """
        return self.filter(user=user)

    def for_app(self, app_name: str):
        """
        Filter flows by application name.

        Args:
            app_name: Application name

        Returns:
            FlowQuerySet: Filtered queryset (chainable)
        """
        return self.filter(app_name=app_name)

    def of_type(self, flow_type: str):
        """
        Filter flows by flow type.

        Args:
            flow_type: Flow type (e.g., "workflow_a", "process_b")

        Returns:
            FlowQuerySet: Filtered queryset (chainable)
        """
        return self.filter(flow_type=flow_type)

    def in_progress(self):
        """
        Filter for in-progress (non-terminal) flows only.
        Includes flows that are pending, running, or interrupted.
        Excludes completed, failed, and cancelled flows.

        Returns:
            FlowQuerySet: Filtered queryset (chainable)
        """
        return self.filter(
            status__in=[Flow.STATUS_PENDING, Flow.STATUS_RUNNING, Flow.STATUS_INTERRUPTED]
        )

    def by_recency(self):
        """
        Order flows by most recently resumed first.

        Returns:
            FlowQuerySet: Ordered queryset (chainable)
        """
        return self.order_by("-last_resumed_at")

    def filter_by_state(self, **state_filters):
        """
        Filter flows by state field values.

        Args:
            **state_filters: Keyword arguments where keys are field paths (using double underscores
                           for nested fields) and values are the expected values.

        Returns:
            List of Flow instances that match all state filters.

        Examples:
            # Simple field
            flows.filter_by_state(counter=42)

            # Nested field
            flows.filter_by_state(nested_data__branch="left")

            # Multiple fields (AND logic)
            flows.filter_by_state(counter=43, branch_choice="right")
        """
        if not state_filters:
            return list(self)

        filtered_flows = []
        for flow in self:
            if self._matches_state_filters(flow.state, state_filters):
                filtered_flows.append(flow)
        return filtered_flows

    @staticmethod
    def _matches_state_filters(state: dict, filters: dict) -> bool:
        """
        Check if a flow's state matches all provided filters.

        Args:
            state: The flow's state dictionary
            filters: Dictionary of field_path: expected_value pairs

        Returns:
            bool: True if state matches all filters, False otherwise

        Note:
            - Supports nested field paths using double underscores (e.g., "data__title")
            - Uses string comparison to handle type coercion
            - Returns False if state is None or any field is missing
        """
        if state is None:
            return False

        for field_path, expected_value in filters.items():
            # Navigate nested fields
            current_value: Any = state
            for field in field_path.split("__"):
                if isinstance(current_value, dict):
                    current_value = current_value.get(field)
                else:
                    return False

                if current_value is None:
                    return False

            # Convert to string for comparison to handle different types
            if str(current_value) != str(expected_value):
                return False

        return True

    def filter_by_flow_type_permissions(self, request, view, permission_type: str = "crud"):
        """
        Filter flows to only include those where the user has permission
        based on each flow's flow type permission class.

        Args:
            request: DRF request object
            view: DRF view instance
            permission_type: "crud" or "resume"

        Returns:
            List of Flow instances where user has permission
        """
        from graflow.models.registry import FlowType

        # Convert queryset to list to iterate
        flows_list = list(self)

        # Group flows by (app_name, flow_type) for efficient permission checking
        flow_type_keys = {}
        for flow in flows_list:
            key = (flow.app_name, flow.flow_type)
            if key not in flow_type_keys:
                flow_type_keys[key] = []
            flow_type_keys[key].append(flow)

        # Check permissions for each flow object individually (object-level permission check)
        allowed_flows = []
        for (app_name, flow_type_name), flow_list in flow_type_keys.items():
            try:
                flow_type_obj = FlowType.objects.get_latest(app_name, flow_type_name)
                if flow_type_obj:
                    permission = flow_type_obj.get_permission_instance(permission_type)
                    # Check object-level permission for each flow
                    for flow in flow_list:
                        if permission.has_object_permission(request, view, flow):
                            allowed_flows.append(flow)
            except Exception as e:
                logger.warning(f"Error checking permission for {app_name}:{flow_type_name}: {e}")
                # On error, skip these flows (fail secure)
                continue

        return allowed_flows


def filter_flows_by_permissions(flows, request, view, permission_type: str = "crud"):
    """
    Filter flows (queryset or list) to only include those where the user has permission
    based on each flow's flow type permission class.

    Args:
        flows: FlowQuerySet or list of Flow instances
        request: DRF request object
        view: DRF view instance
        permission_type: "crud" or "resume"

    Returns:
        List of Flow instances where user has permission
    """
    # If it's a queryset, use its method
    if hasattr(flows, "filter_by_flow_type_permissions"):
        return flows.filter_by_flow_type_permissions(request, view, permission_type)

    # If it's already a list, use the same logic
    from graflow.models.registry import FlowType

    # Group flows by (app_name, flow_type) for efficient permission checking
    flow_type_keys = {}
    for flow in flows:
        key = (flow.app_name, flow.flow_type)
        if key not in flow_type_keys:
            flow_type_keys[key] = []
        flow_type_keys[key].append(flow)

    # Check permissions for each flow object individually (object-level permission check)
    allowed_flows = []
    for (app_name, flow_type_name), flow_list in flow_type_keys.items():
        try:
            flow_type_obj = FlowType.objects.get_latest(app_name, flow_type_name)
            if flow_type_obj:
                permission = flow_type_obj.get_permission_instance(permission_type)
                # Check object-level permission for each flow
                for flow in flow_list:
                    if permission.has_object_permission(request, view, flow):
                        allowed_flows.append(flow)
        except Exception as e:
            logger.warning(f"Error checking permission for {app_name}:{flow_type_name}: {e}")
            # On error, skip these flows (fail secure)
            continue

    return allowed_flows


class Flow(models.Model):
    STATUS_PENDING = "pending"  # Created, not yet invoked
    STATUS_RUNNING = "running"  # Graph actively executing
    STATUS_INTERRUPTED = "interrupted"  # At interrupt point, awaiting user input
    STATUS_COMPLETED = "completed"  # Finished successfully
    STATUS_FAILED = "failed"  # Execution error
    STATUS_CANCELLED = "cancelled"  # Hard cancelled by user, no resume possible

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_INTERRUPTED, "Interrupted"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="flows", null=True, blank=True
    )
    app_name = models.CharField(max_length=255, help_text="Application name")
    flow_type = models.CharField(max_length=255, help_text="Type of the flow (i.e. graph name)")
    graph_version = models.CharField(
        max_length=50, help_text="Version of the graph defining the flow"
    )

    # User-friendly fields
    display_name = models.CharField(
        max_length=255, blank=True, null=True, help_text="User-friendly name for this flow"
    )
    cover_image_url = models.URLField(null=True, blank=True, help_text="Image URL for this flow")

    status = models.CharField(max_length=255, default=STATUS_PENDING, choices=STATUS_CHOICES)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_resumed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "graflow_flow"
        indexes = [
            models.Index(fields=["user", "app_name", "flow_type"]),
        ]

    objects = FlowQuerySet.as_manager()

    def __str__(self):
        flow_info = f"{self.app_name}:{self.flow_type}:{self.graph_version}"
        user_info = f", user={self.user.username}" if self.user else ", background flow"
        return f"Flow({flow_info}{user_info})"

    def is_terminal(self):
        """Check if flow is in a terminal state (i.e. cannot be resumed)."""
        return self.status in [Flow.STATUS_COMPLETED, Flow.STATUS_FAILED, Flow.STATUS_CANCELLED]

    def cancel(self):
        """
        Cancel the flow (hard cancellation - cannot be resumed).

        Raises:
            ValueError: If flow is already in a terminal state
        """
        if self.is_terminal():
            raise ValueError(f"Cannot cancel flow in terminal state: {self.status}")
        self.status = Flow.STATUS_CANCELLED
        self.save()

    def mark_cancelled(self):
        """
        Idempotently mark the flow as cancelled without raising errors.

        This is used by DELETE operations where we simply want to hide the flow
        from the user regardless of its terminal state.
        """
        if self.status != Flow.STATUS_CANCELLED:
            self.status = Flow.STATUS_CANCELLED
            self.save(update_fields=["status"])

    @cached_property
    def graph(self):
        flow_type_obj = FlowType.objects.get(
            app_name=self.app_name, flow_type=self.flow_type, version=self.graph_version
        )
        return flow_type_obj.get_graph()

    @cached_property
    def graph_state_definition(self):
        flow_type_obj = FlowType.objects.get(
            app_name=self.app_name, flow_type=self.flow_type, version=self.graph_version
        )
        return flow_type_obj.get_state_definition()

    @property
    def state(self):
        """
        Retrieve the state snapshot without invoking the graph.
        """
        try:
            config = {"configurable": {"thread_id": str(self.pk)}}

            # Get state from graph (includes interrupt metadata)
            graph_state = self.graph.get_state(config)

            if graph_state and graph_state.values:
                # Convert any Pydantic models in the state to proper JSON objects
                current_state = self._convert_pydantic_models(graph_state.values)

                # Extract interrupt data from checkpoint metadata and get current_state_name
                current_state_name = self._infer_current_state_name_from_snapshot(graph_state)

                # Merge interrupt values from tasks (useful for Postgres checkpointer)
                if hasattr(graph_state, "tasks") and graph_state.tasks:
                    for task in graph_state.tasks:
                        if hasattr(task, "interrupts") and task.interrupts:
                            # Fallback to task.name if we still don't have a node
                            if current_state_name is None:
                                current_state_name = getattr(task, "name", None)
                            for interrupt in task.interrupts:
                                # Extract node name from interrupt for backwards compatibility
                                if current_state_name is None:
                                    current_state_name = (
                                        self._extract_current_state_name_from_interrupt(interrupt)
                                    )
                                # Merge interrupt value into state
                                if hasattr(interrupt, "value") and isinstance(
                                    interrupt.value, dict
                                ):
                                    current_state.update(interrupt.value)
                                    break

                # If we didn't get current_state_name from tasks, try extracting from raw state
                # values (for memory backend, interrupts are stored in state values as
                # __interrupt__)
                if current_state_name is None:
                    # Check raw state values before conversion
                    raw_values = graph_state.values
                    if isinstance(raw_values, dict) and "__interrupt__" in raw_values:
                        interrupt_data = raw_values["__interrupt__"]
                        if isinstance(interrupt_data, (list, tuple)) and len(interrupt_data) > 0:
                            interrupt = interrupt_data[0]
                            current_state_name = self._extract_current_state_name_from_interrupt(
                                interrupt
                            )

                    # Fallback: try extracting from converted state
                    if current_state_name is None:
                        current_state_name = self._get_current_state_name_from_state(current_state)

                current_state = self._prepare_state(
                    current_state,
                    skip_interrupt_extraction=True,
                    current_state_name=current_state_name,
                )
                self._current_state_name_cache = current_state_name
                return current_state
            else:
                self._current_state_name_cache = None
                return None
        except Exception as e:
            logger.error(f"Error retrieving graph state for flow {self.pk}: {e}", exc_info=True)
            self._current_state_name_cache = None
            return None

    def get_current_state_name(self):
        """
        Get the current state name inferred from the latest graph snapshot.
        """
        try:
            if hasattr(self, "_current_state_name_cache"):
                return self._current_state_name_cache

            current_state = self.state
            if hasattr(self, "_current_state_name_cache"):
                return self._current_state_name_cache

            if current_state is None:
                return None

            current_state_name = self._get_current_state_name_from_state(current_state)
            self._current_state_name_cache = current_state_name
            return current_state_name
        except Exception as e:
            logger.error(f"Error getting current state name for flow {self.pk}: {e}", exc_info=True)
            return None

    def _get_current_state_name_from_state(self, current_state):
        """
        Extract current state name from a state dict without calling self.state.
        This avoids recursion when called from the state property.
        """
        if current_state is None:
            return None

        # Check for interrupts in the state (current_state is a dict)
        if isinstance(current_state, dict):
            # Check for interrupts in the values
            if "__interrupt__" in current_state:
                interrupt_data = current_state["__interrupt__"]
                if isinstance(interrupt_data, (list, tuple)) and len(interrupt_data) > 0:
                    interrupt = interrupt_data[0]
                    current_state_name = self._extract_current_state_name_from_interrupt(interrupt)
                    if current_state_name:
                        return current_state_name

            # Check for other possible patterns
            for key, value in current_state.items():
                if key.startswith("branch:to:") and value is None:
                    current_state_name = key.replace("branch:to:", "")
                    return current_state_name

        # Fallback: check if current_state has interrupts attribute (for object-like state)
        if hasattr(current_state, "interrupts") and current_state.interrupts:
            for interrupt in current_state.interrupts:
                current_state_name = self._extract_current_state_name_from_interrupt(interrupt)
                if current_state_name:
                    return current_state_name

        return None

    def resume(self, submitted_state):
        """
        Resume the flow execution.

        Raises:
            Exception: If graph execution fails (status set to FAILED)
        """
        # Atomically transition to RUNNING if currently pending or interrupted.
        updated = Flow.objects.filter(
            pk=self.pk, status__in=[Flow.STATUS_PENDING, Flow.STATUS_INTERRUPTED]
        ).update(status=Flow.STATUS_RUNNING)
        if updated == 0:
            self.refresh_from_db()
            if self.is_terminal():
                raise ValueError(f"Cannot resume flow in terminal state: {self.status}")
            if self.status == Flow.STATUS_RUNNING:
                raise ValueError("Cannot resume flow while it is running")
            raise ValueError(f"Cannot resume flow from state: {self.status}")

        config = {
            "configurable": {"thread_id": str(self.pk)},
            "recursion_limit": 100,
        }

        try:
            # Store previous status before changing
            was_interrupted = self.status == Flow.STATUS_INTERRUPTED

            # Status already updated in DB; keep in-memory in sync
            self.status = Flow.STATUS_RUNNING

            # Invoke the graph based on previous state
            if was_interrupted:
                # Resuming from an interrupt point
                result_state = self.graph.invoke(Command(resume=submitted_state), config=config)
            else:
                # First invocation (from pending state)
                result_state = self.graph.invoke(submitted_state, config=config)

            # Check if the graph was interrupted and update status accordingly
            has_interrupt = result_state is not None and "__interrupt__" in result_state
            if has_interrupt:
                self.status = Flow.STATUS_INTERRUPTED
            else:
                self.status = Flow.STATUS_COMPLETED

            self.save()

            current_state_name = None
            if has_interrupt:
                # Fetch latest snapshot to determine the current state name
                graph_state = self.graph.get_state(config)
                current_state_name = self._infer_current_state_name_from_snapshot(graph_state)
            self._current_state_name_cache = current_state_name

            # When there's an interrupt, return only interrupt data (not full state)
            result_state = self._prepare_state(
                result_state, interrupt_only=has_interrupt, current_state_name=current_state_name
            )
            return result_state

        except Exception as e:
            # Mark flow as failed and store error message
            self.status = Flow.STATUS_FAILED
            self.error_message = str(e)
            self.save()
            raise

    def _convert_pydantic_models(self, data):
        """
        Recursively convert Pydantic models to dictionaries.
        """
        if hasattr(data, "model_dump"):
            # It's a Pydantic model, convert to dict with mode='python'
            # to ensure proper serialization
            return data.model_dump(mode="python")
        elif isinstance(data, dict):
            # Convert all values in the dict
            return {k: self._convert_pydantic_models(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            # Convert all items in the list/tuple
            return [self._convert_pydantic_models(item) for item in data]
        else:
            # Return as-is for primitive types
            return data

    def _prepare_state(
        self, state, skip_interrupt_extraction=False, interrupt_only=False, current_state_name=None
    ):
        """
        Prepare the state for the flow.

        Args:
            state: The raw state from the graph
            skip_interrupt_extraction: If True, skip extracting interrupt from __interrupt__ key
            interrupt_only: If True and there's an interrupt, return ONLY interrupt "
            "data (don't merge with full state)
            current_state_name: Pre-computed current state name (to avoid recursion)
        """
        # Check for interrupt and extract its value (only if not already extracted)
        if not skip_interrupt_extraction and state and "__interrupt__" in state:
            interrupts = state.get("__interrupt__", [])
            if isinstance(interrupts, tuple):
                interrupts = list(interrupts)
            if interrupts and len(interrupts) > 0:
                interrupt_value = interrupts[0].value if hasattr(interrupts[0], "value") else {}
                if isinstance(interrupt_value, dict):
                    if interrupt_only:
                        # Return ONLY interrupt data, not merged with full state
                        state = interrupt_value.copy()
                    else:
                        # Merge interrupt value into the state
                        state.update(interrupt_value)

        # Clean up LangGraph internal fields
        state = self._clean_internal_fields(state)

        # LangGraph is not aware of current_state_name; it is exposed separately
        # via Flow.get_current_state_name().
        return state

    @staticmethod
    def _clean_internal_fields(state):
        """
        Remove LangGraph internal fields and flow level fields from the state.
        """
        if not isinstance(state, dict):
            return state

        # Filter out internal LangGraph keys and application-specific fields
        cleaned_state = {
            k: v
            for k, v in state.items()
            if k != "__interrupt__"
            and not k.startswith("branch:to:")
            and not k.startswith("_")  # Remove internal fields with underscore prefix
            and k
            not in [
                "user_id",
                "flow_id",
                "initial_input_received",
            ]  # Remove flow-level and internal tracking fields
        }

        return cleaned_state

    def _extract_current_state_name_from_interrupt(self, interrupt) -> str | None:
        """Extract the current state name from the interrupt."""
        if hasattr(interrupt, "ns") and interrupt.ns:
            # Extract node name from namespace (e.g., "select_topic:uuid" -> "select_topic")
            node_namespace = interrupt.ns[0] if interrupt.ns else ""
            if ":" in node_namespace:
                return node_namespace.split(":")[0]
            else:
                return node_namespace
        return None

    def _infer_current_state_name_from_snapshot(self, graph_state: Any) -> str | None:
        """
        Infer the current state name from a StateSnapshot returned by LangGraph.

        Newer LangGraph versions no longer expose the namespace on Interrupt objects,
        so we rely on snapshot metadata such as `next` or task information.
        """

        if graph_state is None:
            return None

        next_nodes = getattr(graph_state, "next", None)
        if next_nodes:
            for node in next_nodes:
                if isinstance(node, str) and node:
                    return node

        tasks = getattr(graph_state, "tasks", None)
        if tasks:
            for task in tasks:
                if getattr(task, "interrupts", None):
                    task_name = getattr(task, "name", None)
                    if task_name:
                        return task_name
                    task_path = getattr(task, "path", None)
                    if task_path:
                        for part in reversed(task_path):
                            if isinstance(part, str) and part:
                                return part

        return None
