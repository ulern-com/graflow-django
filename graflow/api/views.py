import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import decorators, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from graflow.api.serializers import (
    FlowCreateSerializer,
    FlowDetailSerializer,
    FlowListSerializer,
    FlowStateSerializer,
    FlowStateUpdateSerializer,
    FlowStatsSerializer,
    FlowTypeSerializer,
)
from graflow.models.flows import Flow, filter_flows_by_permissions
from graflow.models.registry import FlowType

logger = logging.getLogger(__name__)


def get_permissions():
    """
    Get the permissions for the viewset based on the GRAFLOW_REQUIRE_AUTHENTICATION setting.
    """
    require_auth = getattr(settings, "GRAFLOW_REQUIRE_AUTHENTICATION", True)
    if require_auth:
        return [IsAuthenticated()]
    return [AllowAny()]


class FlowViewSet(viewsets.GenericViewSet):
    serializer_class = FlowDetailSerializer
    lookup_field = "pk"

    def get_permissions(self):
        """
        Get permissions dynamically based on the flow type.

        - CRUD operations (list, retrieve, create, destroy, cancel, most_recent):
          Use flow type's crud_permission_class
        - Resume operation: Use flow type's resume_permission_class
        - Stats: Admin only (IsAdminUser)
        """
        from rest_framework.permissions import IsAdminUser

        action = self.action
        app_name = getattr(settings, "GRAFLOW_APP_NAME", "graflow")

        # Stats endpoint is admin-only
        if action == "stats":
            return [IsAdminUser()]

        # Resume uses resume permission
        if action == "resume":
            # Get flow directly from database using pk (can't use get_object() here)
            pk = self.kwargs.get("pk")
            if pk:
                try:
                    flow = Flow.objects.get(pk=pk)
                    flow_type_obj = FlowType.objects.get_latest(flow.app_name, flow.flow_type)
                    if flow_type_obj:
                        return [flow_type_obj.get_permission_instance("resume")]
                except Flow.DoesNotExist:
                    pass
            return get_permissions()  # Fallback

        # For create action, get flow_type from request data
        if action == "create":
            flow_type = (
                self.request.data.get("flow_type") if hasattr(self.request, "data") else None
            )
            if flow_type:
                flow_type_obj = FlowType.objects.get_latest(app_name, flow_type)
                if flow_type_obj:
                    return [flow_type_obj.get_permission_instance("crud")]
            return get_permissions()  # Fallback

        # For retrieve, destroy, cancel - get from flow
        if action in ["retrieve", "destroy", "cancel"]:
            # Get flow directly from database using pk (can't use get_object() here)
            pk = self.kwargs.get("pk")
            if pk:
                try:
                    flow = Flow.objects.get(pk=pk)
                    flow_type_obj = FlowType.objects.get_latest(flow.app_name, flow.flow_type)
                    if flow_type_obj:
                        return [flow_type_obj.get_permission_instance("crud")]
                except Flow.DoesNotExist:
                    pass
            return get_permissions()  # Fallback

        # For list and most_recent: if flow_type query param exists, use that FlowType's permission
        if action in ["list", "most_recent"]:
            flow_type = (
                self.request.query_params.get("flow_type")
                if hasattr(self.request, "query_params")
                else None
            )
            if flow_type:
                flow_type_obj = FlowType.objects.get_latest(app_name, flow_type)
                if flow_type_obj:
                    return [flow_type_obj.get_permission_instance("crud")]
            # If no flow_type param, use default (we'll filter queryset in the action method)
            return get_permissions()

        # Default fallback
        return get_permissions()

    def get_throttles(self):
        """
        Get throttles dynamically based on the flow type.

        - CRUD operations (list, retrieve, create, destroy, cancel, most_recent):
          Use flow type's crud_throttle_class if configured, otherwise use default
        - Resume operation: Use flow type's resume_throttle_class if configured,
          otherwise use default
        - Stats: No special throttling (uses default or none)
        """
        from graflow.api.throttling import FlowCreationThrottle, FlowResumeThrottle

        action = self.action
        app_name = getattr(settings, "GRAFLOW_APP_NAME", "graflow")

        # Resume uses resume throttle
        if action == "resume":
            pk = self.kwargs.get("pk")
            if pk:
                try:
                    flow = Flow.objects.get(pk=pk)
                    flow_type_obj = FlowType.objects.get_latest(flow.app_name, flow.flow_type)
                    if flow_type_obj:
                        throttle = flow_type_obj.get_throttle_instance("resume")
                        if throttle:
                            return [throttle]
                except Flow.DoesNotExist:
                    pass
            # Fallback to default
            return [FlowResumeThrottle()]

        # For create action, get flow_type from request data
        if action == "create":
            flow_type = (
                self.request.data.get("flow_type") if hasattr(self.request, "data") else None
            )
            if flow_type:
                flow_type_obj = FlowType.objects.get_latest(app_name, flow_type)
                if flow_type_obj:
                    throttle = flow_type_obj.get_throttle_instance("crud")
                    if throttle:
                        return [throttle]
            # Fallback to default
            return [FlowCreationThrottle()]

        # For retrieve, destroy, cancel - get from flow
        if action in ["retrieve", "destroy", "cancel"]:
            pk = self.kwargs.get("pk")
            if pk:
                try:
                    flow = Flow.objects.get(pk=pk)
                    flow_type_obj = FlowType.objects.get_latest(flow.app_name, flow.flow_type)
                    if flow_type_obj:
                        throttle = flow_type_obj.get_throttle_instance("crud")
                        if throttle:
                            return [throttle]
                except Flow.DoesNotExist:
                    pass
            # Fallback to default (no specific throttle for these actions)
            return []

        # For list and most_recent: if flow_type query param exists, use that FlowType's throttle
        if action in ["list", "most_recent"]:
            flow_type = (
                self.request.query_params.get("flow_type")
                if hasattr(self.request, "query_params")
                else None
            )
            if flow_type:
                flow_type_obj = FlowType.objects.get_latest(app_name, flow_type)
                if flow_type_obj:
                    throttle = flow_type_obj.get_throttle_instance("crud")
                    if throttle:
                        return [throttle]
            # If no flow_type param, use default (no specific throttle)
            return []

        # Default: no throttling (or could return default throttles)
        return []

    def get_base_queryset(self, *, include_cancelled: bool = False):
        """
        Ensure users can only access their own flows.
        When authentication is disabled, return all flows with user=None.
        """
        if not self.request.user.is_authenticated:
            queryset = Flow.objects.filter(user=None)
        else:
            queryset = Flow.objects.filter(user=self.request.user)

        if include_cancelled:
            return queryset
        return queryset.exclude(status=Flow.STATUS_CANCELLED)

    def get_queryset(self):
        return self.get_base_queryset()

    def get_object(self):
        """
        Get the flow object, ensuring it belongs to the requesting user.
        """
        queryset = self.get_queryset()
        obj = get_object_or_404(queryset, pk=self.kwargs.get("pk"))
        return obj

    def _resume_flow(self, flow: Flow, state: dict) -> dict:
        """
        Resume the flow with the given state.

        Raises:
            ValidationError: If state validation fails
            Exception: If flow resumption fails
        """
        serializer = FlowStateSerializer(
            data=state, context={"graph_state_definition": flow.graph_state_definition}
        )
        serializer.is_valid(raise_exception=True)
        validated_state = serializer.validated_data
        result_state = flow.resume(validated_state)
        return result_state

    @extend_schema(
        summary="List flows",
        description="""
        List flows with optional filtering.
        
        By default, returns only in-progress flows (pending, running, interrupted).
        Use `status=all` to include all statuses, or specify a specific status.
        
        **State Filtering:**
        You can filter flows by their state values using the `state__*` query parameter pattern.
        Use dot notation for nested fields: `state__counter=5` or `state__nested_data__field=value`.
        Multiple state filters are combined with AND logic.
        
        **Examples:**
        - List all interrupted flows: `/flows/?status=interrupted`
        - List flows of specific type: `/flows/?flow_type=hello_world`
        - Filter by state: `/flows/?state__counter=5`
        - Combine filters: `/flows/?flow_type=hello_world&status=interrupted&state__counter=42`
        - Get detailed info: `/flows/?is_detailed=true`
        """,
        parameters=[
            OpenApiParameter(
                name="flow_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by flow type (e.g., 'hello_world')",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Filter by status. Options: 'pending', 'running', 'interrupted', "
                    "'completed', 'failed', 'cancelled', or 'all'. "
                    "Defaults to in-progress flows if not specified."
                ),
                enum=[
                    "pending",
                    "running",
                    "interrupted",
                    "completed",
                    "failed",
                    "cancelled",
                    "all",
                ],
            ),
            OpenApiParameter(
                name="is_detailed",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Return detailed flow information including state. Default: false",
            ),
            OpenApiParameter(
                name="state__*",
                type=dict,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Filter by state fields. Use dot notation for nested fields "
                    "(e.g., state__counter=5, state__nested_data__field=value). "
                    "Multiple filters are combined with AND."
                ),
                style="deepObject",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=FlowListSerializer(many=True),
                description=(
                    "List of flows. Returns FlowListSerializer by default, "
                    "or FlowDetailSerializer if is_detailed=true"
                ),
            ),
        },
        examples=[
            OpenApiExample(
                "List in-progress flows",
                value=[],
                response_only=True,
            ),
            OpenApiExample(
                "List with filters",
                description="Filter by type and state",
                value=[],
                response_only=True,
            ),
        ],
    )
    def list(self, request):
        """
        List flows with optional filtering.

        Query params:
            - flow_type: Filter by graph name (e.g., "workflow_a", "process_b")
            - status: Filter by status (e.g., "pending", "interrupted", "completed")
                     Defaults to in-progress flows if not specified, "all" to show all flows
            - state__*: Filter by state fields (e.g., state__counter=5, state__data__field=value)
            - is_detailed: Return detailed flow information (default false)

        Example: GET /flows/?flow_type=workflow_a&status=interrupted&state__data__id=123
        """
        flow_type = request.query_params.get("flow_type")
        status_filter = request.query_params.get("status")
        is_detailed = request.query_params.get("is_detailed", "false").lower() == "true"

        # Start with user's flows
        include_cancelled = status_filter in ["all", "cancelled"]
        flows = self.get_base_queryset(include_cancelled=include_cancelled)

        # Filter by status (default to in-progress flows)
        if status_filter:
            if status_filter == "all":
                flows = flows.all()
            else:
                flows = flows.filter(status=status_filter)
        else:
            flows = flows.in_progress()

        # Filter by flow_type if provided
        if flow_type:
            flows = flows.of_type(flow_type)

        # Order by recency
        flows = flows.by_recency()

        # Extract and apply state filters
        state_filters = {}
        for key, value in request.query_params.items():
            if key.startswith("state__"):
                field_path = key[7:]  # Remove "state__" prefix
                state_filters[field_path] = value

        if state_filters:
            flows = flows.filter_by_state(**state_filters)
        else:
            flows = list(flows)

        # Filter by permissions (object-level)
        flows = filter_flows_by_permissions(flows, request, self, permission_type="crud")

        if is_detailed:
            serializer = FlowDetailSerializer(flows, many=True)
        else:
            serializer = FlowListSerializer(flows, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Retrieve a flow",
        description="""
        Get detailed information about a specific flow.
        
        Returns the full flow object including state, current_state_name, and error_message.
        Automatically filters to ensure users can only access their own flows.
        """,
        responses={
            200: FlowDetailSerializer,
            404: OpenApiResponse(
                description="Not Found",
                examples=[OpenApiExample("Not Found", value={"detail": "Not found."})],
            ),
        },
    )
    def retrieve(self, request, pk=None):
        """
        Retrieve a specific flow by ID.

        Returns detailed information including current state and current state name.
        """
        # This now automatically filters by user due to get_object()
        flow = self.get_object()
        serializer = FlowDetailSerializer(flow)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Create a new flow",
        description="""
        Create and start a new flow instance.
        
        The flow will be initialized with the provided state (if any) and
        will execute until it reaches a completion or interrupt point.
        
        **Required:**
        - `flow_type`: Must be a registered flow type (check `/api/graflow/flow-types/`)
        
        **Optional:**
        - `state`: Initial state dictionary matching the flow type's state schema
        - `display_name`: Human-readable name for the flow
        - `cover_image_url`: URL to a cover image for the flow
        
        Returns the created flow with its current state and status.
        """,
        request=FlowCreateSerializer,
        responses={
            201: FlowDetailSerializer,
            400: OpenApiResponse(
                description="Validation Error",
                examples=[
                    OpenApiExample(
                        "Validation Error",
                        value={
                            "error": "No graph found for flow_type 'invalid_type' in app 'myflows'"
                        },
                    )
                ],
            ),
        },
        examples=[
            OpenApiExample(
                "Create Hello World Flow",
                value={
                    "flow_type": "hello_world",
                    "display_name": "My First Flow",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create Flow with State",
                value={
                    "flow_type": "hello_world",
                    "state": {"message": "Hello from API"},
                    "display_name": "Greeting Flow",
                },
                request_only=True,
            ),
        ],
    )
    def create(self, request):
        """
        Create a new flow instance.

        Validates the flow_type, creates the flow, and executes it until
        completion or an interrupt point. If initialization fails, the flow
        is automatically cancelled and an error is returned.
        """
        # Use serializer for input validation and schema
        serializer = FlowCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        flow_type = validated_data["flow_type"]

        try:
            app_name = getattr(settings, "GRAFLOW_APP_NAME", "graflow")
            flow_type_obj = FlowType.objects.get_latest(app_name, flow_type)
            if flow_type_obj is None:
                return Response(
                    {"error": f"No graph found for flow_type '{flow_type}' in app '{app_name}'"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            flow = Flow.objects.create(
                user=request.user if request.user.is_authenticated else None,
                app_name=app_name,
                flow_type=flow_type,
                graph_version=flow_type_obj.version,
                display_name=validated_data.get("display_name") or None,
                cover_image_url=validated_data.get("cover_image_url") or None,
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Start the flow with a single initial state (merge metadata + optional input)
            user_id = request.user.id if request.user.is_authenticated else None
            state = {"user_id": user_id, "flow_id": flow.id}
            if validated_data.get("state"):
                state.update(validated_data["state"])
            self._resume_flow(flow, state)
        except Exception as e:
            # Clean up the flow if initialization fails
            logger.error(f"Error initializing flow {flow.id}: {str(e)}", exc_info=True)
            flow.refresh_from_db()
            return Response(
                {
                    "error": f"Failed to initialize flow: {str(e)}",
                    "flow_id": flow.id,
                    "flow_type": flow_type,
                    "flow_status": flow.status,
                    "error_message": flow.error_message,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = FlowDetailSerializer(flow)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Delete a flow",
        description="""
        Delete a flow (cancels it).
        
        This is idempotent - succeeds even if the flow is already in a terminal state.
        For stricter validation that returns errors on invalid states, "
        "use the `/cancel/` endpoint instead.
        """,
        responses={
            204: None,
            404: OpenApiResponse(
                description="Not Found",
                examples=[OpenApiExample("Not Found", value={"detail": "Not found."})],
            ),
        },
    )
    def destroy(self, request, pk=None):
        """
        Soft-delete a flow by marking it cancelled.

        This hides the flow from list/detail responses even if it has already
        completed. Unlike the `/cancel/` action, this never raises and is fully
        idempotent.
        """
        flow = self.get_object()
        flow.mark_cancelled()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Cancel a flow",
        description="""
        Cancel a flow (hard cancellation - cannot be resumed).
        
        This endpoint enforces business rules: attempting to cancel a flow that
        has already completed, failed, or been cancelled yields a 400. Use this
        when you want the API to surface "already finished" errors instead of
        silently hiding the flow.
        """,
        request=None,
        responses={
            200: OpenApiResponse(
                description="Success",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={"message": "Flow cancelled successfully", "flow_id": 123},
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Already Terminated",
                examples=[
                    OpenApiExample(
                        "Already Terminated",
                        value={
                            "error": "Flow is already in a terminal state",
                            "flow_id": 123,
                            "flow_status": "completed",
                        },
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Not Found",
                examples=[OpenApiExample("Not Found", value={"detail": "Not found."})],
            ),
        },
    )
    @decorators.action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """
        Cancel a flow (hard cancellation - cannot be resumed).

        Returns 400 if flow is already in a terminal state.
        """
        flow = self.get_object()

        try:
            flow.cancel()
            return Response(
                {"message": "Flow cancelled successfully", "flow_id": flow.id},
                status=status.HTTP_200_OK,
            )
        except ValueError as e:
            return Response(
                {
                    "error": str(e),
                    "flow_id": flow.id,
                    "flow_status": flow.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        summary="Resume a flow",
        description="""
        Resume flow execution with updated state.
        
        Use this endpoint to continue a flow from an interrupt point or to update
        the flow's state. The request body is the state dictionary itself - its structure
        must match the flow type's state definition.
        
        **Important:** The request body structure varies by flow type. Check the flow type's
        state definition or use the `/flow-types/` endpoint to understand the expected structure.
        
        **Returns 400 if:**
        - Flow is in a terminal state (completed, failed, cancelled)
        - Flow is currently running
        - State validation fails (structure doesn't match flow type)
        
        **Response Structure:**
        The response includes:
        - Flow metadata (id, status, error_message, last_resumed_at, current_state_name)
        - state_update: Incremental state changes (delta) from this resume operation
        
        This allows the frontend to update both the flow metadata and the flow state
        without needing an additional GET request, while keeping response payloads small.
        """,
        request={
            "application/json": {
                "type": "object",
                "description": (
                    "State dictionary matching the flow type's state schema. "
                    "Structure varies by flow_type."
                ),
                "additionalProperties": True,
            }
        },
        responses={
            200: FlowStateUpdateSerializer,
            400: OpenApiResponse(
                description="Validation Error",
                examples=[
                    OpenApiExample(
                        "Validation Error",
                        value={
                            "error": "Flow cannot be resumed: already in terminal state",
                            "flow_id": 123,
                            "flow_status": "completed",
                        },
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Not Found",
                examples=[OpenApiExample("Not Found", value={"detail": "Not found."})],
            ),
        },
        examples=[
            OpenApiExample(
                "Resume Hello World Flow",
                description="Example for hello_world flow type",
                value={"message": "Hello from resume"},
                request_only=True,
            ),
            OpenApiExample(
                "Resume with Complex State",
                description="Example for flows with nested state",
                value={"counter": 5, "branch_choice": "right", "data": {"id": 123}},
                request_only=True,
            ),
            OpenApiExample(
                "Resume Response",
                description="Example response showing flow metadata + state_update",
                value={
                    "id": 123,
                    "status": "interrupted",
                    "error_message": None,
                    "last_resumed_at": "2024-01-15T10:30:00Z",
                    "current_state_name": "request_topic",
                    "state_update": {
                        "conversation": ["Hello! What topic would you like to discuss?"],
                        "required_data": ["topic"],
                    },
                },
                response_only=True,
            ),
        ],
    )
    @decorators.action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        """
        Resume flow execution with updated state.

        Returns flow metadata (status, error_message, last_resumed_at, current_state_name)
        along with the state_update delta. This allows the frontend to update both
        the flow metadata and the flow state without needing an additional GET request.

        Returns 400 if flow cannot be resumed (terminal state or running).
        """
        # This now automatically filters by user due to get_object()
        flow = self.get_object()

        try:
            result_state = self._resume_flow(flow, request.data)
            # Refresh flow to get updated status, last_resumed_at, etc.
            flow.refresh_from_db()
            # Pass both flow and state_update to serializer
            serializer = FlowStateUpdateSerializer(
                {"flow": flow, "state_update": result_state},
                context={"graph_state_definition": flow.graph_state_definition},
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            # Flow model validation error (e.g., can't resume)
            logger.warning(f"Validation error resuming flow {flow.id}: {str(e)}")
            return Response(
                {
                    "error": str(e),
                    "flow_id": flow.id,
                    "flow_status": flow.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            # Graph execution error
            logger.error(f"Error resuming flow {flow.id}: {str(e)}", exc_info=True)
            flow.refresh_from_db()  # Get updated status (may be FAILED)
            return Response(
                {
                    "error": f"Failed to resume flow: {str(e)}",
                    "flow_id": flow.id,
                    "flow_status": flow.status,
                    "error_message": flow.error_message,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        summary="Get flow statistics",
        description="""
        Get flow statistics for the authenticated user.
        
        Returns counts grouped by:
        - **Total**: Total number of flows (excluding cancelled)
        - **by_status**: Counts for each status "
        "(pending, running, interrupted, completed, failed, cancelled)
        - **by_type**: Counts grouped by flow_type
        
        Only includes flows accessible to the current user "
        "(user's own flows, or all flows with user=None if authentication is disabled).
        """,
        responses={
            200: FlowStatsSerializer,
        },
        examples=[
            OpenApiExample(
                "Stats Response",
                value={
                    "total": 10,
                    "by_status": {
                        "pending": 2,
                        "running": 1,
                        "interrupted": 3,
                        "completed": 3,
                        "failed": 1,
                        "cancelled": 0,
                    },
                    "by_type": {
                        "hello_world": 8,
                        "workflow_a": 2,
                    },
                },
                response_only=True,
            ),
        ],
    )
    @decorators.action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """
        Get flow statistics for the authenticated user.

        Returns counts by status and by flow type.
        """
        flows = self.get_base_queryset()

        # Get distinct flow types for this user
        flow_types = flows.values_list("flow_type", flat=True).distinct()

        stats_data = {
            "total": flows.count(),
            "by_status": {
                "pending": flows.filter(status=Flow.STATUS_PENDING).count(),
                "running": flows.filter(status=Flow.STATUS_RUNNING).count(),
                "interrupted": flows.filter(status=Flow.STATUS_INTERRUPTED).count(),
                "completed": flows.filter(status=Flow.STATUS_COMPLETED).count(),
                "failed": flows.filter(status=Flow.STATUS_FAILED).count(),
                "cancelled": flows.filter(status=Flow.STATUS_CANCELLED).count(),
            },
            "by_type": {
                flow_type: flows.filter(flow_type=flow_type).count() for flow_type in flow_types
            },
        }

        return Response(stats_data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Get most recent flow",
        description="""
        Return the most recently modified flow for the authenticated user.
        
        By default, returns the most recent in-progress flow. You can filter by
        flow_type and/or status to get the most recent flow matching those criteria.
        """,
        parameters=[
            OpenApiParameter(
                name="flow_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by flow type",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Filter by status. Use 'all' to include all statuses. "
                    "Defaults to in-progress flows."
                ),
                enum=[
                    "pending",
                    "running",
                    "interrupted",
                    "completed",
                    "failed",
                    "cancelled",
                    "all",
                ],
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=FlowDetailSerializer,
                description="Most recent flow details",
            ),
            404: OpenApiResponse(
                description="No flows found",
                examples=[OpenApiExample("Not Found", value={"detail": "No flows found"})],
            ),
        },
    )
    @decorators.action(detail=False, methods=["get"], url_path="most-recent")
    def most_recent(self, request):
        """
        Return the most recently modified flow for the authenticated user.

        Optional query params:
          - flow_type: filter by graph name
          - status: filter by status (defaults to in-progress flows if omitted; "
          "use \"all\" for no status filter)
        """
        flow_type = request.query_params.get("flow_type")
        status_filter = request.query_params.get("status")
        include_cancelled = status_filter in ["all", "cancelled"]
        flows = self.get_base_queryset(include_cancelled=include_cancelled)

        # Apply status filter (default: in-progress)
        if status_filter:
            if status_filter == "all":
                flows = flows.all()
            else:
                flows = flows.filter(status=status_filter)
        else:
            flows = flows.in_progress()

        # Apply type filter
        if flow_type:
            flows = flows.of_type(flow_type)

        # Order by most recently interacted/updated
        flows = flows.by_recency()

        # Convert to list if needed for permission filtering
        if not isinstance(flows, list):
            flows = list(flows)

        # Filter by permissions (object-level)
        flows = filter_flows_by_permissions(flows, request, self, permission_type="crud")

        # Get the first (most recent)
        most_recent_flow = flows[0] if flows else None

        if not most_recent_flow:
            return Response({"detail": "No flows found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = FlowDetailSerializer(most_recent_flow)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FlowTypeViewSet(viewsets.ViewSet):
    """
    Read-only viewset exposing the registered flow types.
    """

    def get_permissions(self):
        return get_permissions()

    @extend_schema(
        summary="List available flow types",
        description="""
        Get a list of all registered flow types available in the system.
        
        Each entry includes:
        - `app_name`: The application namespace
        - `flow_type`: The flow type identifier (use this when creating flows)
        - `version`: The version string
        
        Use the `flow_type` values from this endpoint when creating new flows.
        """,
        responses={200: FlowTypeSerializer(many=True)},
        examples=[
            OpenApiExample(
                "Flow Types Response",
                value=[
                    {"app_name": "myflows", "flow_type": "hello_world", "version": "v1"},
                    {"app_name": "myflows", "flow_type": "workflow_a", "version": "v1"},
                ],
                response_only=True,
            ),
        ],
    )
    def list(self, request):
        """
        List all registered flow types.

        Returns metadata about all flow types that can be used to create flows.
        """
        flow_types = FlowType.objects.active()
        serializer = FlowTypeSerializer(flow_types, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
