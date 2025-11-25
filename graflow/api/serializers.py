from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, Serializer

from graflow.models import Flow


class FlowCreateSerializer(Serializer):
    """
    Serializer for creating a new flow.
    """

    flow_type = serializers.CharField(
        required=True,
        help_text=(
            "The type of flow to create (e.g., 'hello_world'). " "Must be a registered flow type."
        ),
    )
    state = serializers.DictField(
        required=False,
        allow_null=True,
        help_text=(
            "Optional initial state for the flow. "
            "Structure depends on the flow_type's state definition."
        ),
    )
    display_name = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=255,
        help_text="User-friendly display name for the flow.",
    )
    cover_image_url = serializers.URLField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional cover image URL for the flow.",
    )


class FlowStateSerializer(Serializer):
    """
    Serializer for flow states to verify submitted state against the graph state definition.

    NOTE: We accept a graph_state_definition in the serializer context
    """

    def to_internal_value(self, data):
        graph_state_definition = self.context.get("graph_state_definition")
        if graph_state_definition is None:
            raise serializers.ValidationError(
                {"non_field_errors": ["Graph state definition is required in serializer context"]}
            )
        try:
            # Let the graph state definition do validation/coercion
            graph_state = graph_state_definition(**data)
            return graph_state
        except Exception as e:
            raise serializers.ValidationError(
                {"non_field_errors": [f"Invalid input state: {str(e)}"]}
            ) from e


class FlowListSerializer(ModelSerializer):
    """
    Lightweight serializer for Flow list views (without state).
    Includes current_state_name, can_resume, and display_name for better UX.
    """

    current_state_name = serializers.SerializerMethodField()

    class Meta:
        model = Flow
        fields = [
            "id",
            "app_name",
            "flow_type",
            "graph_version",
            "status",
            "created_at",
            "last_resumed_at",
            "current_state_name",
            "display_name",
        ]
        read_only_fields = ["id", "app_name", "flow_type", "graph_version", "created_at"]

    def get_current_state_name(self, obj):
        """Get current state name only for interrupted flows (performance optimization)."""
        if obj.status == Flow.STATUS_INTERRUPTED:
            return obj.get_current_state_name()
        return None


class FlowDetailSerializer(ModelSerializer):
    """
    Detailed serializer for Flow detail views (with state and error message).
    """

    state = serializers.SerializerMethodField()
    current_state_name = serializers.SerializerMethodField()

    class Meta:
        model = Flow
        fields = [
            "id",
            "app_name",
            "flow_type",
            "graph_version",
            "status",
            "error_message",
            "created_at",
            "last_resumed_at",
            "state",
            "current_state_name",
            "display_name",
        ]
        read_only_fields = ["id", "app_name", "flow_type", "graph_version", "created_at"]

    def get_state(self, obj):
        """
        Get state and convert any Pydantic models to dicts for JSON serialization.
        """
        state = obj.state
        if state:
            # Convert any remaining Pydantic models to dicts
            return self._convert_pydantic_to_dict(state)
        return state

    def _convert_pydantic_to_dict(self, obj):
        """Recursively convert Pydantic models to dicts."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="python")
        elif isinstance(obj, dict):
            return {k: self._convert_pydantic_to_dict(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._convert_pydantic_to_dict(item) for item in obj]
        return obj

    def get_current_state_name(self, obj):
        """Get current state name only for interrupted flows (performance optimization)."""
        if obj.status == Flow.STATUS_INTERRUPTED:
            return obj.get_current_state_name()
        return None


class FlowStateUpdateSerializer(Serializer):
    """
    Response serializer for flow resume endpoint.

    Returns flow metadata (status, error_message, last_resumed_at, current_state_name)
    along with the state_update delta. This allows the frontend to update both
    the flow metadata and the flow state without needing an additional GET request.
    """

    # Flow metadata fields
    id = serializers.IntegerField(help_text="Flow ID", read_only=True)
    status = serializers.CharField(help_text="Current flow status", read_only=True)
    error_message = serializers.CharField(
        allow_null=True, help_text="Error message if flow failed", read_only=True
    )
    last_resumed_at = serializers.DateTimeField(
        help_text="Timestamp of last resume operation", read_only=True
    )
    current_state_name = serializers.CharField(
        allow_null=True, help_text="Current state name if flow is interrupted", read_only=True
    )

    # State update delta (partial state changes)
    state_update = serializers.SerializerMethodField(
        help_text="Incremental state update (delta) from this resume operation"
    )

    def get_state_update(self, obj):
        """
        Get state_update from context and serialize it.
        obj here is expected to be a dict with 'state_update' key.
        """
        state_update = obj.get("state_update") if isinstance(obj, dict) else None
        if state_update is None:
            return None

        # Use FlowStateSerializer's conversion logic
        graph_state_definition = self.context.get("graph_state_definition")
        if graph_state_definition is None:
            # Fallback: try to convert if it's a dict with Pydantic models
            return self._convert_pydantic_to_dict(state_update)

        # Serialize using the same logic as FlowStateSerializer
        try:
            if hasattr(state_update, "model_dump"):
                return state_update.model_dump()
            if isinstance(state_update, dict):

                def convert(value):
                    if hasattr(value, "model_dump"):
                        return value.model_dump()
                    if isinstance(value, dict):
                        return {k: convert(v) for k, v in value.items()}
                    if isinstance(value, (list, tuple)):
                        return [convert(v) for v in value]
                    return value

                return convert(state_update)
            return state_update
        except Exception:
            # Fallback conversion
            return self._convert_pydantic_to_dict(state_update)

    def _convert_pydantic_to_dict(self, obj):
        """Recursively convert Pydantic models to dicts."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="python")
        elif isinstance(obj, dict):
            return {k: self._convert_pydantic_to_dict(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._convert_pydantic_to_dict(item) for item in obj]
        return obj

    def to_representation(self, instance):
        """
        Override to properly handle the instance which is a dict with flow and state_update.
        """
        if isinstance(instance, dict) and "flow" in instance:
            flow = instance["flow"]
            # Use field serializers to properly serialize values
            # Handle None values explicitly to avoid CharField converting None to 'None'
            error_message = flow.error_message if flow.error_message is not None else None
            current_state_name = flow.get_current_state_name()

            result = {
                "id": self.fields["id"].to_representation(flow.id),
                "status": self.fields["status"].to_representation(flow.status),
                "error_message": error_message,
                "last_resumed_at": self.fields["last_resumed_at"].to_representation(
                    flow.last_resumed_at
                ),
                "current_state_name": current_state_name,
            }
            # Get state_update
            result["state_update"] = self.get_state_update(instance)
            return result
        # Fallback: assume instance is already a dict with the structure we need
        return super().to_representation(instance)


class FlowStatsSerializer(Serializer):
    """
    Response serializer for flow statistics.
    """

    total = serializers.IntegerField(help_text="Total number of flows")
    by_status = serializers.DictField(
        child=serializers.IntegerField(),
        help_text=(
            "Count of flows grouped by status "
            "(pending, running, interrupted, completed, failed, cancelled)"
        ),
    )
    by_type = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="Count of flows grouped by flow_type",
    )


class FlowTypeSerializer(Serializer):
    """
    Read-only serializer describing a registered flow type entry.
    """

    app_name = serializers.CharField()
    flow_type = serializers.CharField()
    version = serializers.CharField()
