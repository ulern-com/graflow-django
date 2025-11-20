from django.conf import settings
from django.test import TestCase

from graflow.storage.cache import DjangoCache


class PostgresCacheTest(TestCase):
    """Test the PostgreSQL cache implementation."""

    def setUp(self):
        """Set up test data."""
        # DjangoCache uses Django ORM, so it works with any database
        # (migrations are automatically run by Django's test framework)
        self.cache = DjangoCache()
        self.test_namespace = ("test", "namespace")
        self.test_key = "test_key"
        self.test_value = {"data": "test_value"}

    def test_set_and_get(self):
        """Test setting and getting a cache value."""
        # Set a value
        self.cache.set({(self.test_namespace, self.test_key): (self.test_value, None)})

        # Get the value
        result = self.cache.get([(self.test_namespace, self.test_key)])

        # Verify the result
        self.assertEqual(result[(self.test_namespace, self.test_key)], self.test_value)

    def test_set_with_ttl(self):
        """Test setting a cache value with TTL."""
        # Set a value with 1 second TTL
        self.cache.set({(self.test_namespace, self.test_key): (self.test_value, 1)})

        # Get the value immediately
        result = self.cache.get([(self.test_namespace, self.test_key)])
        self.assertEqual(result[(self.test_namespace, self.test_key)], self.test_value)

        # Wait for expiration
        import time

        time.sleep(1.1)

        # Try to get the expired value
        result = self.cache.get([(self.test_namespace, self.test_key)])
        self.assertEqual(len(result), 0)  # Should be empty

    def test_clear_namespace(self):
        """Test clearing a specific namespace."""
        # Set values in different namespaces
        self.cache.set(
            {
                (self.test_namespace, "key1"): (self.test_value, None),
                (("other", "namespace"), "key2"): (self.test_value, None),
            }
        )

        # Clear only the test namespace
        self.cache.clear([self.test_namespace])

        # Check that only the test namespace is cleared
        result = self.cache.get([(self.test_namespace, "key1"), (("other", "namespace"), "key2")])

        self.assertNotIn((self.test_namespace, "key1"), result)
        self.assertIn((("other", "namespace"), "key2"), result)

    def test_clear_all(self):
        """Test clearing all cache entries."""
        # Set multiple values
        self.cache.set(
            {
                (self.test_namespace, "key1"): (self.test_value, None),
                (("other", "namespace"), "key2"): (self.test_value, None),
            }
        )

        # Clear all
        self.cache.clear()

        # Check that all are cleared
        result = self.cache.get([(self.test_namespace, "key1"), (("other", "namespace"), "key2")])

        self.assertEqual(len(result), 0)

    def test_get_stats(self):
        """Test getting cache statistics."""
        # Set some values
        self.cache.set(
            {
                (self.test_namespace, "key1"): (self.test_value, None),
                (self.test_namespace, "key2"): (self.test_value, 1),  # Will expire
            }
        )

        stats = self.cache.get_stats()

        self.assertIn("total_entries", stats)
        self.assertIn("active_entries", stats)
        self.assertIn("expired_entries", stats)
        self.assertEqual(stats["total_entries"], 2)
