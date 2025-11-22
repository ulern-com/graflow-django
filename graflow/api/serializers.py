from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, Serializer

from graflow.models import Flow


class FlowCreateSerializer(Serializer):
    """
    Serializer for creating a new flow.
    """

    flow_type = serializers.CharField(
        required=True,
        help_text="The type of flow to create (e.g., 'hello_world'). Must be a registered flow type."
    )
    state = serializers.DictField(
        required=False,
        allow_null=True,
        help_text="Optional initial state for the flow. Structure depends on the flow_type's state definition."
    )
    display_name = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=255,
        help_text="User-friendly display name for the flow."
    )
    cover_image_url = serializers.URLField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional cover image URL for the flow."
    )


class FlowStateSerializer(Serializer):
    """
    Two-way serializer for LangGraph's graph state based on a provided Pydantic model.

    This serializer:
    - validates incoming JSON into the Pydantic model (partial-friendly if model supports defaults)
    - serializes model instances or dict results back to JSON

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
            raise serializers.ValidationError({"non_field_errors": [f"Invalid input state: {str(e)}"]})

    def to_representation(self, instance):
        # instance may be a Pydantic BaseModel, a plain dict from LangGraph, or a dataclass-like
        try:
            # LangGraph often returns dict-like; just return as-is if serializable
            if hasattr(instance, "model_dump"):
                return instance.model_dump()
            # Sometimes LangGraph returns a dict with BaseModels inside; best-effort conversion
            if isinstance(instance, dict):

                def convert(value):
                    if hasattr(value, "model_dump"):
                        return value.model_dump()
                    if isinstance(value, dict):
                        return {k: convert(v) for k, v in value.items()}
                    if isinstance(value, (list, tuple)):
                        return [convert(v) for v in value]
                    return value

                return convert(instance)
            return instance
        except Exception as e:
            raise serializers.ValidationError({"non_field_errors": [f"Invalid output state: {str(e)}"]})


class FlowListSerializer(ModelSerializer):
    """
    Lightweight serializer for Flow list views (without state).
    Includes current_node, can_resume, and display_name for better UX.
    """

    current_node = serializers.SerializerMethodField()

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
            "current_node",
            "display_name",
        ]
        read_only_fields = ["id", "app_name", "flow_type", "graph_version", "created_at"]

    def get_current_node(self, obj):
        """Get current node only for interrupted flows (performance optimization)."""
        if obj.status == Flow.STATUS_INTERRUPTED:
            return obj.get_current_node()
        return None


class FlowDetailSerializer(ModelSerializer):
    """
    Detailed serializer for Flow detail views (with state and error message).
    """

    state = serializers.SerializerMethodField()
    current_node = serializers.SerializerMethodField()

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
            "current_node",
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

    def get_current_node(self, obj):
        """Get current node - already computed in state property."""
        if obj.state:
            return obj.state.get("current_node")
        return None


class FlowResumeSerializer(Serializer):
    """
    Serializer for resuming a flow with updated state.
    The state structure depends on the flow type's state definition.
    
    This accepts any dictionary structure. The actual state validation happens
    at runtime against the specific flow type's state schema.
    
    Example states vary by flow type:
    - For hello_world: {"message": "Hello"}
    - For other flows: {"counter": 5, "branch_choice": "right"}
    """

    # Use DictField to accept any structure
    # The actual validation happens in FlowStateSerializer with context
    # This field is just for schema documentation
    state = serializers.DictField(
        required=True,
        allow_empty=False,
        help_text="State dictionary matching the flow type's state schema. Structure varies by flow_type.",
    )


class FlowStatsSerializer(Serializer):
    """
    Response serializer for flow statistics.
    """

    total = serializers.IntegerField(help_text="Total number of flows")
    by_status = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="Count of flows grouped by status (pending, running, interrupted, completed, failed, cancelled)",
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
