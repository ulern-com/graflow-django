import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import decorators, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from graflow.api.serializers import (
    FlowDetailSerializer,
    FlowListSerializer,
    FlowStateSerializer,
    FlowTypeSerializer,
)
from graflow.api.throttling import FlowCreationThrottle, FlowResumeThrottle
from graflow.graphs.registry import get_latest_graph_version, list_registered_graphs
from graflow.models import Flow

logger = logging.getLogger(__name__)


class FlowViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FlowDetailSerializer
    lookup_field = "pk"

    def get_queryset(self):
        """
        Ensure users can only access their own flows.
        """
        return Flow.objects.filter(user=self.request.user).exclude(status=Flow.STATUS_CANCELLED)

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
        serializer = FlowStateSerializer(data=state, context={"graph_state_definition": flow.graph_state_definition})
        serializer.is_valid(raise_exception=True)
        validated_state = serializer.validated_data
        result_state = flow.resume(validated_state)
        return result_state

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
        flows = self.get_queryset()

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

        if is_detailed:
            serializer = FlowDetailSerializer(flows, many=True)
        else:
            serializer = FlowListSerializer(flows, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        # This now automatically filters by user due to get_object()
        flow = self.get_object()
        serializer = FlowDetailSerializer(flow)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request):
        self.throttle_classes = [FlowCreationThrottle]

        flow_type = request.data.get("flow_type")
        if not flow_type:
            return Response({"error": "flow_type is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Use getattr with default to safely access settings
            app_name = getattr(settings, 'GRAFLOW_APP_NAME', 'graflow')
            graph_version = get_latest_graph_version(flow_type, app_name)
            if graph_version is None:
                return Response(
                    {"error": f"No graph found for flow_type '{flow_type}' in app '{app_name}'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            flow = Flow.objects.create(
                user=request.user,
                app_name=app_name,
                flow_type=flow_type,
                graph_version=graph_version,
                display_name=request.data.get("display_name") or None,
                cover_image_url=request.data.get("cover_image_url"),
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Start the flow with the initial state (user_id, flow_id)
            state = {"user_id": request.user.id, "flow_id": flow.id}
            self._resume_flow(flow, state)

            # Resume the flow with the request state, if provided
            state = request.data.get("state")
            if state:
                self._resume_flow(flow, state)
        except Exception as e:
            # Clean up the flow if initialization fails
            logger.error(f"Error initializing flow {flow.id}: {str(e)}", exc_info=True)
            flow.cancel()
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

        serializer = FlowDetailSerializer(flow)
        response_data = serializer.data
        return Response(response_data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        """
        Delete a flow (cancels it).
        Idempotent - succeeds even if flow is already in a terminal state.
        Note: Use the explicit /cancel/ action for stricter validation.
        """
        flow = self.get_object()
        try:
            flow.cancel()
        except ValueError:
            # Flow is already in a terminal state - that's fine for DELETE
            # DELETE should be idempotent
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)

    @decorators.action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """
        Cancel a flow (hard cancellation - cannot be resumed).

        Returns 400 if flow is already in a terminal state.
        """
        flow = self.get_object()

        try:
            flow.cancel()
            return Response({"message": "Flow cancelled successfully", "flow_id": flow.id}, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {
                    "error": str(e),
                    "flow_id": flow.id,
                    "flow_status": flow.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @decorators.action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        """
        Resume flow execution with updated state.

        Returns 400 if flow cannot be resumed (terminal state or running).
        """
        self.throttle_classes = [FlowResumeThrottle]

        # This now automatically filters by user due to get_object()
        flow = self.get_object()

        try:
            result_state = self._resume_flow(flow, request.data)
            serializer = FlowStateSerializer(
                result_state, context={"graph_state_definition": flow.graph_state_definition}
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

    @decorators.action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """
        Get flow statistics for the authenticated user.

        Returns counts by status and by flow type.
        """
        flows = self.get_queryset()

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
            "by_type": {flow_type: flows.filter(flow_type=flow_type).count() for flow_type in flow_types},
        }

        return Response(stats_data, status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=["get"], url_path="most-recent")
    def most_recent(self, request):
        """
        Return the most recently modified flow for the authenticated user.

        Optional query params:
          - flow_type: filter by graph name
          - status: filter by status (defaults to in-progress flows if omitted; use "all" for no status filter)
        """
        flows = self.get_queryset()

        flow_type = request.query_params.get("flow_type")
        status_filter = request.query_params.get("status")

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

        # Get the first (most recent)
        most_recent_flow = flows.first() if hasattr(flows, "first") else (flows[0] if flows else None)

        if not most_recent_flow:
            return Response({"detail": "No flows found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = FlowDetailSerializer(most_recent_flow)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FlowTypeViewSet(viewsets.ViewSet):
    """
    Read-only viewset exposing the registered flow types.
    """

    permission_classes = [IsAuthenticated]

    def list(self, request):
        flow_types = list_registered_graphs()
        serializer = FlowTypeSerializer(flow_types, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
