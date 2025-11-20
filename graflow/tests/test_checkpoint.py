from django.conf import settings
from django.test import TestCase

from graflow.storage.checkpointer import DjangoSaver


class DjangoSaverTest(TestCase):
    """Test the DjangoSaver implementation."""

    def setUp(self):
        """Set up test data."""
        # Skip if not using PostgreSQL
        db_engine = settings.DATABASES['default']['ENGINE']
        if 'postgresql' not in db_engine:
            self.skipTest(f"Test requires PostgreSQL, but using {db_engine}")
        self.saver = DjangoSaver()

    def tearDown(self):
        """Clean up test data."""
        if hasattr(self, "saver") and self.saver is not None:
            try:
                if hasattr(self.saver, "pipe") and self.saver.pipe is not None:
                    self.saver.pipe.close()
                if hasattr(self.saver, "conn") and self.saver.conn is not None:
                    if not self.saver.conn.closed:
                        self.saver.conn.close()
            except Exception:
                pass  # Ignore errors during cleanup

    def test_initialization(self):
        """Test that DjangoSaver initializes correctly."""
        # Should not raise any exceptions
        self.assertIsNotNone(self.saver)
        self.assertIsNotNone(self.saver.conn)

    def test_setup(self):
        """Test that setup method works."""
        # Should not raise any exceptions
        self.saver.setup()

    def test_context_manager(self):
        """Test that DjangoSaver works as a context manager."""
        with DjangoSaver() as saver:
            self.assertIsNotNone(saver)
            self.assertIsNotNone(saver.conn)

    def test_from_django_settings(self):
        """Test the from_django_settings class method."""
        with DjangoSaver.from_django_settings() as saver:
            self.assertIsNotNone(saver)
            self.assertIsNotNone(saver.conn)

    def test_database_settings_validation(self):
        """Test that it validates PostgreSQL database."""
        # This should work with our current Django settings
        saver = DjangoSaver()
        self.assertIsNotNone(saver)

    def test_connection_string_building(self):
        """Test that connection string is built correctly from Django settings."""
        # Verify that the saver can access the database
        with DjangoSaver() as saver:
            # Try a simple query to verify connection works
            with saver._cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                self.assertEqual(result["?column?"], 1)
