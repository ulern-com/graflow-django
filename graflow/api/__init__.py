"""
REST API for Graflow flows.
"""

__all__ = [
    "FlowViewSet",
    "FlowDetailSerializer",
    "FlowListSerializer",
    "FlowStateSerializer",
    "FlowCreationThrottle",
    "FlowResumeThrottle",
]


def __getattr__(name):
    """Lazy import to avoid circular dependencies."""
    if name in ("FlowDetailSerializer", "FlowListSerializer", "FlowStateSerializer"):
        from graflow.api.serializers import (
            FlowDetailSerializer,
            FlowListSerializer,
            FlowStateSerializer,
        )

        return {
            "FlowDetailSerializer": FlowDetailSerializer,
            "FlowListSerializer": FlowListSerializer,
            "FlowStateSerializer": FlowStateSerializer,
        }[name]
    elif name in ("FlowCreationThrottle", "FlowResumeThrottle"):
        from graflow.api.throttling import FlowCreationThrottle, FlowResumeThrottle

        return {
            "FlowCreationThrottle": FlowCreationThrottle,
            "FlowResumeThrottle": FlowResumeThrottle,
        }[name]
    elif name == "FlowViewSet":
        from graflow.api.views import FlowViewSet

        return FlowViewSet
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
