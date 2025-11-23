from django.apps import AppConfig


class GraflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "graflow"

    def ready(self):
        """Called when Django starts. Register graphs from settings."""
        from graflow.graphs.registry import register_graphs_from_settings

        register_graphs_from_settings()
