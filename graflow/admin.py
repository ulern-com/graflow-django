from django.contrib import admin
from django.utils import timezone

from graflow.models.flows import Flow
from graflow.models.langgraph import CacheEntry, Checkpoint, CheckpointBlob, CheckpointWrite, Store
from graflow.models.registry import FlowType


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    """Admin interface for LangGraph store entries."""

    list_display = ("prefix", "key", "created_at", "updated_at", "expires_at", "is_expired")
    list_filter = ("prefix", "created_at", "updated_at", "expires_at")
    search_fields = ("prefix", "key")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at",)

    def is_expired(self, obj):
        """Show if the store entry is expired."""
        if obj.expires_at is None:
            return False
        return timezone.now() >= obj.expires_at

    is_expired.boolean = True  # type: ignore[attr-defined]
    is_expired.short_description = "Expired"  # type: ignore[attr-defined]

    actions = ["cleanup_expired"]

    def cleanup_expired(self, request, queryset):
        """Clean up expired store entries."""
        expired_count = queryset.filter(expires_at__lte=timezone.now()).delete()[0]
        self.message_user(request, f"Cleaned up {expired_count} expired store entries.")

    cleanup_expired.short_description = "Clean up expired entries"  # type: ignore[attr-defined]


@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    """Admin interface for LangGraph checkpoints."""

    list_display = ("thread_id", "checkpoint_ns", "checkpoint_id", "type", "parent_checkpoint_id")
    list_filter = ("checkpoint_ns", "type")
    search_fields = ("thread_id", "checkpoint_id", "parent_checkpoint_id")
    readonly_fields = (
        "thread_id",
        "checkpoint_ns",
        "checkpoint_id",
        "parent_checkpoint_id",
        "type",
        "checkpoint",
        "metadata",
    )
    ordering = ("-checkpoint_id",)

    def has_add_permission(self, request):
        """Disable adding checkpoints through admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing checkpoints through admin."""
        return False


@admin.register(CheckpointBlob)
class CheckpointBlobAdmin(admin.ModelAdmin):
    """Admin interface for LangGraph checkpoint blobs."""

    list_display = ("thread_id", "checkpoint_ns", "channel", "version", "type", "has_blob")
    list_filter = ("checkpoint_ns", "channel", "type")
    search_fields = ("thread_id", "channel", "version")
    readonly_fields = ("thread_id", "checkpoint_ns", "channel", "version", "type", "blob")
    ordering = ("-version",)

    def has_blob(self, obj):
        """Show if the blob has data."""
        return obj.blob is not None

    has_blob.boolean = True  # type: ignore[attr-defined]
    has_blob.short_description = "Has Blob"  # type: ignore[attr-defined]

    def has_add_permission(self, request):
        """Disable adding checkpoint blobs through admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing checkpoint blobs through admin."""
        return False


@admin.register(CheckpointWrite)
class CheckpointWriteAdmin(admin.ModelAdmin):
    """Admin interface for LangGraph checkpoint writes."""

    list_display = (
        "thread_id",
        "checkpoint_ns",
        "checkpoint_id",
        "task_id",
        "idx",
        "channel",
        "type",
        "has_blob",
    )
    list_filter = ("checkpoint_ns", "channel", "type")
    search_fields = ("thread_id", "checkpoint_id", "task_id", "channel")
    readonly_fields = (
        "thread_id",
        "checkpoint_ns",
        "checkpoint_id",
        "task_id",
        "idx",
        "channel",
        "type",
        "blob",
        "task_path",
    )
    ordering = ("-idx",)

    def has_blob(self, obj):
        """Show if the blob has data."""
        return obj.blob is not None

    has_blob.boolean = True  # type: ignore[attr-defined]
    has_blob.short_description = "Has Blob"  # type: ignore[attr-defined]

    def has_add_permission(self, request):
        """Disable adding checkpoint writes through admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing checkpoint writes through admin."""
        return False


@admin.register(CacheEntry)
class CacheEntryAdmin(admin.ModelAdmin):
    """Admin interface for cache entries."""

    list_display = ("namespace", "key", "created_at", "expires_at", "is_expired")
    list_filter = ("created_at", "expires_at")
    search_fields = ("namespace", "key")
    readonly_fields = ("created_at",)

    def is_expired(self, obj):
        """Show if the cache entry is expired."""
        return obj.is_expired()

    is_expired.boolean = True  # type: ignore[attr-defined]
    is_expired.short_description = "Expired"  # type: ignore[attr-defined]

    def get_queryset(self, request):
        """Add expired filter."""
        qs = super().get_queryset(request)
        return qs

    actions = ["cleanup_expired"]

    def cleanup_expired(self, request, queryset):
        """Clean up expired cache entries."""
        expired_count = queryset.filter(expires_at__lte=timezone.now()).delete()[0]
        self.message_user(request, f"Cleaned up {expired_count} expired cache entries.")

    cleanup_expired.short_description = "Clean up expired entries"  # type: ignore[attr-defined]


@admin.register(Flow)
class FlowAdmin(admin.ModelAdmin):
    """Admin interface for user flows."""

    list_display = (
        "id",
        "display_name",
        "user",
        "created_at",
        "last_resumed_at",
        "app_name",
        "flow_type",
        "graph_version",
        "status",
    )
    list_filter = (
        "created_at",
        "last_resumed_at",
        "app_name",
        "flow_type",
        "graph_version",
        "status",
    )
    search_fields = (
        "user__username",
        "user__email",
        "app_name",
        "flow_type",
        "graph_version",
        "status",
    )
    readonly_fields = ("created_at", "last_resumed_at", "state")
    ordering = ("-last_resumed_at",)

    fieldsets = (
        (
            "Flow Info",
            {
                "fields": (
                    "display_name",
                    "user",
                    "created_at",
                    "last_resumed_at",
                    "app_name",
                    "flow_type",
                    "graph_version",
                    "status",
                )
            },
        ),
        ("Graph State", {"fields": ("state",)}),
    )

    def get_queryset(self, request):
        """Optimize queryset with user select_related."""
        return super().get_queryset(request).select_related("user")


@admin.register(FlowType)
class FlowTypeAdmin(admin.ModelAdmin):
    """Admin interface for flow types (graph registry)."""

    list_display = (
        "app_name",
        "flow_type",
        "version",
        "is_latest",
        "is_active",
        "display_name",
        "created_at",
    )
    list_filter = ("app_name", "is_latest", "is_active", "created_at", "updated_at")
    search_fields = ("app_name", "flow_type", "version", "display_name", "description")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "app_name",
                    "flow_type",
                    "version",
                    "is_latest",
                    "is_active",
                )
            },
        ),
        (
            "Graph Definition",
            {
                "fields": (
                    "builder_path",
                    "state_path",
                ),
                "description": (
                    "String paths to builder function and state class "
                    "(e.g., 'myapp.graphs:build_graph')"
                ),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "display_name",
                    "description",
                )
            },
        ),
        (
            "Permissions & Throttling",
            {
                "fields": (
                    "crud_permission_class",
                    "resume_permission_class",
                    "crud_throttle_class",
                    "resume_throttle_class",
                ),
                "description": (
                    "String paths to permission/throttle classes "
                    "(e.g., 'myapp.permissions:CustomPermission')"
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["activate", "deactivate", "mark_as_latest"]

    def activate(self, request, queryset):
        """Activate selected flow types."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} flow type(s).")

    activate.short_description = "Activate selected flow types"

    def deactivate(self, request, queryset):
        """Deactivate selected flow types."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {count} flow type(s).")

    deactivate.short_description = "Deactivate selected flow types"

    def mark_as_latest(self, request, queryset):
        """Mark selected flow types as latest version (unmarks others)."""
        # Only one version per (app_name, flow_type) can be latest
        updated_count = 0
        for flow_type in queryset:
            # Unmark other versions of the same (app_name, flow_type)
            FlowType.objects.filter(
                app_name=flow_type.app_name, flow_type=flow_type.flow_type
            ).exclude(id=flow_type.id).update(is_latest=False)
            # Mark this one as latest
            if not flow_type.is_latest:
                flow_type.is_latest = True
                flow_type.save(update_fields=["is_latest"])
                updated_count += 1
            else:
                updated_count += 1
        self.message_user(request, f"Marked {updated_count} flow type(s) as latest version.")

    mark_as_latest.short_description = "Mark selected as latest version"
