from django.conf import settings
from django.test import TestCase

from graflow.storage.store import DjangoStore


class DjangoStoreTest(TestCase):
    """Test the DjangoStore implementation."""

    def setUp(self):
        """Set up test data."""
        # Skip if not using PostgreSQL
        db_engine = settings.DATABASES['default']['ENGINE']
        if 'postgresql' not in db_engine:
            self.skipTest(f"Test requires PostgreSQL, but using {db_engine}")
        self.store = DjangoStore()

    def tearDown(self):
        """Clean up test data."""
        if hasattr(self, "store") and self.store is not None:
            try:
                if hasattr(self.store, "pipe") and self.store.pipe is not None:
                    self.store.pipe.close()
                if hasattr(self.store, "conn") and self.store.conn is not None:
                    if not self.store.conn.closed:
                        self.store.conn.close()
            except Exception:
                pass  # Ignore errors during cleanup

    def test_initialization(self):
        """Test that DjangoStore initializes correctly."""
        # Should not raise any exceptions
        self.assertIsNotNone(self.store)
        self.assertIsNotNone(self.store.conn)

    def test_setup(self):
        """Test that setup method works."""
        # Should not raise any exceptions
        self.store.setup()

    def test_context_manager(self):
        """Test that DjangoStore works as a context manager."""
        with DjangoStore() as store:
            self.assertIsNotNone(store)
            self.assertIsNotNone(store.conn)

    def test_from_django_settings(self):
        """Test the from_django_settings class method."""
        with DjangoStore.from_django_settings() as store:
            self.assertIsNotNone(store)
            self.assertIsNotNone(store.conn)

    def test_database_settings_validation(self):
        """Test that it validates PostgreSQL database."""
        # This should work with our current Django settings
        store = DjangoStore()
        self.assertIsNotNone(store)

    def test_connection_string_building(self):
        """Test that connection string is built correctly from Django settings."""
        # Verify that the store can access the database
        with DjangoStore() as store:
            # Try a simple query to verify connection works
            with store._cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                self.assertEqual(result["?column?"], 1)

    def test_basic_store_operations(self):
        """Test basic store operations."""
        with DjangoStore() as store:
            store.setup()

            # Test put and get operations
            namespace = ("test", "namespace")
            key = "test_key"
            value = {"data": "test_value"}

            # Put a value
            store.put(namespace, key, value)

            # Get the value
            result = store.get(namespace, key)
            self.assertEqual(result.value, value)

            # Test list namespaces
            namespaces = list(store.list_namespaces())
            self.assertIn(namespace, namespaces)

    def test_ttl_operations(self):
        """Test TTL operations."""
        from langgraph.store.postgres.base import TTLConfig

        ttl_config = TTLConfig(ttl_minutes=1)

        with DjangoStore(ttl=ttl_config) as store:
            store.setup()

            # Put a value with TTL
            namespace = ("test", "ttl")
            key = "ttl_key"
            value = {"data": "ttl_value"}

            store.put(namespace, key, value, ttl=1)

            # Get the value immediately
            result = store.get(namespace, key)
            self.assertEqual(result.value, value)

            # Test TTL sweep
            swept = store.sweep_ttl()
            self.assertIsInstance(swept, int)
