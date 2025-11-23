"""
Pytest configuration for graflow tests.
Sets up Django settings to use the project's settings module.
"""

import os

import django
from django.conf import settings

# Set Django settings module if not already set
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myflows.settings")
    django.setup()

    # Override persistence backend to use memory for tests
    # This avoids requiring PostgreSQL for tests
    settings.GRAFLOW_PERSISTENCE_BACKEND = "memory"

    # Override app name to match what tests expect
    settings.GRAFLOW_APP_NAME = "test_app"

    # Reset any already-initialized persistence components to ensure
    # they use the memory backend
    from graflow.graphs import registry

    registry._node_cache = None
    registry._checkpointer = None
    registry._store = None
