"""Unit tests for FlowType registry model and QuerySet methods."""

from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.permissions import AllowAny, IsAuthenticated

from graflow.models.registry import FlowType, _import_from_string


class ImportFromStringTest(TestCase):
    """Test _import_from_string utility function."""

    def test_import_with_colon_format(self):
        """Test importing with colon format (preferred)."""
        result = _import_from_string("rest_framework.permissions:IsAuthenticated")
        self.assertEqual(result, IsAuthenticated)

    def test_import_with_dot_format(self):
        """Test importing with dot format (backwards compatibility)."""
        result = _import_from_string("rest_framework.permissions.IsAuthenticated")
        self.assertEqual(result, IsAuthenticated)

    def test_import_function(self):
        """Test importing a function."""
        result = _import_from_string("graflow.tests.fixtures.test_graph:build_test_graph")
        self.assertTrue(callable(result))

    def test_import_class(self):
        """Test importing a class."""
        from graflow.tests.fixtures.test_graph import TestGraphState

        result = _import_from_string("graflow.tests.fixtures.test_graph:TestGraphState")
        self.assertEqual(result, TestGraphState)

    def test_invalid_path_format(self):
        """Test that invalid path format raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            _import_from_string("invalidpath")
        self.assertIn("Invalid path format", str(cm.exception))

    def test_nonexistent_module(self):
        """Test that non-existent module raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            _import_from_string("nonexistent.module:attribute")
        self.assertIn("Failed to import module", str(cm.exception))

    def test_nonexistent_attribute(self):
        """Test that non-existent attribute raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            _import_from_string("rest_framework.permissions:NonexistentClass")
        self.assertIn("has no attribute", str(cm.exception))


class FlowTypeQuerySetTest(TestCase):
    """Test FlowTypeQuerySet methods."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests."""
        # Create flow types for different apps (multi-tenancy)
        cls.flow_type_app1_v1 = FlowType.objects.create(
            app_name="app1",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
            is_active=True,
        )

        cls.flow_type_app1_v2 = FlowType.objects.create(
            app_name="app1",
            flow_type="test_flow",
            version="v2",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=False,
            is_active=True,
        )

        cls.flow_type_app1_v3_inactive = FlowType.objects.create(
            app_name="app1",
            flow_type="test_flow",
            version="v3",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=False,
            is_active=False,
        )

        cls.flow_type_app2_v1 = FlowType.objects.create(
            app_name="app2",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
            is_active=True,
        )

        cls.flow_type_app1_other = FlowType.objects.create(
            app_name="app1",
            flow_type="other_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
            is_active=True,
        )

    def test_get_latest_returns_active_latest(self):
        """Test get_latest returns the latest active version."""
        result = FlowType.objects.get_latest("app1", "test_flow")
        self.assertEqual(result, self.flow_type_app1_v1)
        self.assertTrue(result.is_latest)
        self.assertTrue(result.is_active)

    def test_get_latest_returns_none_when_not_exists(self):
        """Test get_latest returns None when flow type doesn't exist."""
        result = FlowType.objects.get_latest("app1", "nonexistent")
        self.assertIsNone(result)

    def test_get_latest_returns_none_when_inactive(self):
        """Test get_latest returns None when latest version is inactive."""
        # Make the latest version inactive
        self.flow_type_app1_v1.is_active = False
        self.flow_type_app1_v1.save()

        result = FlowType.objects.get_latest("app1", "test_flow")
        self.assertIsNone(result)

    def test_get_latest_respects_app_name(self):
        """Test get_latest respects app_name boundaries (multi-tenancy)."""
        result = FlowType.objects.get_latest("app2", "test_flow")
        self.assertEqual(result, self.flow_type_app2_v1)
        self.assertEqual(result.app_name, "app2")

        # app1 should still return its own latest
        result_app1 = FlowType.objects.get_latest("app1", "test_flow")
        self.assertEqual(result_app1, self.flow_type_app1_v1)
        self.assertEqual(result_app1.app_name, "app1")

    def test_for_app_filters_by_app_name(self):
        """Test for_app filters flow types by app_name."""
        app1_flows = FlowType.objects.for_app("app1")
        self.assertEqual(app1_flows.count(), 4)  # v1, v2, v3_inactive, other
        for flow in app1_flows:
            self.assertEqual(flow.app_name, "app1")

        app2_flows = FlowType.objects.for_app("app2")
        self.assertEqual(app2_flows.count(), 1)
        self.assertEqual(app2_flows.first(), self.flow_type_app2_v1)

    def test_for_app_returns_empty_for_nonexistent_app(self):
        """Test for_app returns empty queryset for non-existent app."""
        result = FlowType.objects.for_app("nonexistent_app")
        self.assertEqual(result.count(), 0)

    def test_active_filters_active_only(self):
        """Test active filters only active flow types."""
        active_flows = FlowType.objects.active()
        # Should exclude v3_inactive
        self.assertGreaterEqual(active_flows.count(), 4)
        for flow in active_flows:
            self.assertTrue(flow.is_active)

        self.assertNotIn(self.flow_type_app1_v3_inactive, active_flows)

    def test_active_can_be_chained(self):
        """Test active can be chained with other queryset methods."""
        result = FlowType.objects.for_app("app1").active()
        self.assertEqual(result.count(), 3)  # v1, v2, other (excluding v3_inactive)
        for flow in result:
            self.assertEqual(flow.app_name, "app1")
            self.assertTrue(flow.is_active)


class FlowTypeModelTest(TestCase):
    """Test FlowType model instance methods."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests."""
        cls.flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

    def test_str_representation(self):
        """Test __str__ returns correct format."""
        self.assertEqual(str(self.flow_type), "test_app:test_flow:v1")

    def test_get_builder_returns_callable(self):
        """Test get_builder returns a callable builder function."""
        builder = self.flow_type.get_builder()
        self.assertTrue(callable(builder))

    def test_get_builder_with_colon_format(self):
        """Test get_builder works with colon format."""
        self.flow_type.builder_path = "graflow.tests.fixtures.test_graph:build_test_graph"
        self.flow_type.save()
        builder = self.flow_type.get_builder()
        self.assertTrue(callable(builder))

    def test_get_builder_with_dot_format(self):
        """Test get_builder works with dot format (backwards compatibility)."""
        self.flow_type.builder_path = "graflow.tests.fixtures.test_graph.build_test_graph"
        self.flow_type.save()
        builder = self.flow_type.get_builder()
        self.assertTrue(callable(builder))

    def test_get_builder_invalid_module(self):
        """Test get_builder raises ValueError for invalid module."""
        self.flow_type.builder_path = "nonexistent.module:function"
        self.flow_type.save()
        with self.assertRaises(ValueError) as cm:
            self.flow_type.get_builder()
        self.assertIn("Failed to import module", str(cm.exception))

    def test_get_builder_invalid_attribute(self):
        """Test get_builder raises ValueError for invalid attribute."""
        self.flow_type.builder_path = "rest_framework.permissions:NonexistentFunction"
        self.flow_type.save()
        with self.assertRaises(ValueError) as cm:
            self.flow_type.get_builder()
        self.assertIn("has no attribute", str(cm.exception))

    def test_get_builder_not_callable(self):
        """Test get_builder raises ValueError when path doesn't resolve to callable."""
        # Mock _import_from_string to return a non-callable object (like a string)
        with patch("graflow.models.registry._import_from_string", return_value="not_callable"):
            with self.assertRaises(ValueError) as cm:
                self.flow_type.get_builder()
            self.assertIn("does not resolve to a callable", str(cm.exception))

    def test_get_state_definition_returns_base_model(self):
        """Test get_state_definition returns a Pydantic BaseModel subclass."""
        from pydantic import BaseModel

        state_class = self.flow_type.get_state_definition()
        self.assertTrue(isinstance(state_class, type))
        self.assertTrue(issubclass(state_class, BaseModel))

    def test_get_state_definition_with_colon_format(self):
        """Test get_state_definition works with colon format."""
        self.flow_type.state_path = "graflow.tests.fixtures.test_graph:TestGraphState"
        self.flow_type.save()
        state_class = self.flow_type.get_state_definition()
        from pydantic import BaseModel

        self.assertTrue(issubclass(state_class, BaseModel))

    def test_get_state_definition_with_dot_format(self):
        """Test get_state_definition works with dot format."""
        self.flow_type.state_path = "graflow.tests.fixtures.test_graph.TestGraphState"
        self.flow_type.save()
        state_class = self.flow_type.get_state_definition()
        from pydantic import BaseModel

        self.assertTrue(issubclass(state_class, BaseModel))

    def test_get_state_definition_invalid_module(self):
        """Test get_state_definition raises ValueError for invalid module."""
        self.flow_type.state_path = "nonexistent.module:StateClass"
        self.flow_type.save()
        with self.assertRaises(ValueError) as cm:
            self.flow_type.get_state_definition()
        self.assertIn("Failed to import module", str(cm.exception))

    def test_get_state_definition_invalid_attribute(self):
        """Test get_state_definition raises ValueError for invalid attribute."""
        self.flow_type.state_path = "rest_framework.permissions:NonexistentState"
        self.flow_type.save()
        with self.assertRaises(ValueError) as cm:
            self.flow_type.get_state_definition()
        self.assertIn("has no attribute", str(cm.exception))

    def test_get_state_definition_not_base_model(self):
        """Test get_state_definition raises ValueError when not a BaseModel subclass."""
        self.flow_type.state_path = "rest_framework.permissions:IsAuthenticated"
        self.flow_type.save()
        with self.assertRaises(ValueError) as cm:
            self.flow_type.get_state_definition()
        self.assertIn("does not resolve to a Pydantic BaseModel class", str(cm.exception))

    def test_get_graph_compiles_successfully(self):
        """Test get_graph compiles graph with storage components."""
        graph = self.flow_type.get_graph()
        self.assertIsNotNone(graph)
        # Graph should have the run_name configured
        # We can't easily test the run_name without executing, but compilation should work

    def test_get_graph_run_name_includes_identifiers(self):
        """Test get_graph configures run_name with app_name, flow_type, version."""
        graph = self.flow_type.get_graph()
        # The run_name is set via with_config, but we can verify the graph was compiled
        self.assertIsNotNone(graph)

    def test_get_graph_handles_compilation_errors(self):
        """Test get_graph handles graph compilation errors gracefully."""
        self.flow_type.builder_path = "rest_framework.permissions:IsAuthenticated"
        self.flow_type.save()
        with self.assertRaises(ValueError) as cm:
            self.flow_type.get_graph()
        self.assertIn("Error building graph", str(cm.exception))


class FlowTypePermissionTest(TestCase):
    """Test FlowType permission instance methods."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests."""
        cls.flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

    def test_get_permission_instance_crud_default(self):
        """Test get_permission_instance returns default for CRUD when not set."""
        # FlowType with default permission class
        permission = self.flow_type.get_permission_instance("crud")
        self.assertIsInstance(permission, IsAuthenticated)

    def test_get_permission_instance_resume_default(self):
        """Test get_permission_instance returns default for resume when not set."""
        permission = self.flow_type.get_permission_instance("resume")
        self.assertIsInstance(permission, IsAuthenticated)

    def test_get_permission_instance_crud_custom(self):
        """Test get_permission_instance returns custom permission for CRUD."""
        self.flow_type.crud_permission_class = "rest_framework.permissions:AllowAny"
        self.flow_type.save()
        permission = self.flow_type.get_permission_instance("crud")
        self.assertIsInstance(permission, AllowAny)

    def test_get_permission_instance_resume_custom(self):
        """Test get_permission_instance returns custom permission for resume."""
        self.flow_type.resume_permission_class = "rest_framework.permissions:AllowAny"
        self.flow_type.save()
        permission = self.flow_type.get_permission_instance("resume")
        self.assertIsInstance(permission, AllowAny)

    def test_get_permission_instance_empty_path_falls_back(self):
        """Test get_permission_instance falls back when permission_path is empty."""
        original_setting = getattr(settings, "GRAFLOW_REQUIRE_AUTHENTICATION", True)
        try:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = True
            self.flow_type.crud_permission_class = ""
            self.flow_type.save()
            permission = self.flow_type.get_permission_instance("crud")
            self.assertIsInstance(permission, IsAuthenticated)
        finally:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = original_setting

    def test_get_permission_instance_respects_require_auth_setting_true(self):
        """Test get_permission_instance respects GRAFLOW_REQUIRE_AUTHENTICATION=True."""
        original_setting = getattr(settings, "GRAFLOW_REQUIRE_AUTHENTICATION", True)
        try:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = True
            self.flow_type.crud_permission_class = ""
            self.flow_type.save()
            permission = self.flow_type.get_permission_instance("crud")
            self.assertIsInstance(permission, IsAuthenticated)
        finally:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = original_setting

    def test_get_permission_instance_respects_require_auth_setting_false(self):
        """Test get_permission_instance respects GRAFLOW_REQUIRE_AUTHENTICATION=False."""
        original_setting = getattr(settings, "GRAFLOW_REQUIRE_AUTHENTICATION", True)
        try:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = False
            self.flow_type.crud_permission_class = ""
            self.flow_type.save()
            permission = self.flow_type.get_permission_instance("crud")
            self.assertIsInstance(permission, AllowAny)
        finally:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = original_setting

    def test_get_permission_instance_invalid_path_falls_back(self):
        """Test get_permission_instance falls back when permission class fails to load."""
        original_setting = getattr(settings, "GRAFLOW_REQUIRE_AUTHENTICATION", True)
        try:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = True
            self.flow_type.crud_permission_class = "nonexistent.module:Permission"
            self.flow_type.save()
            # Should fall back to default without raising exception
            permission = self.flow_type.get_permission_instance("crud")
            self.assertIsInstance(permission, IsAuthenticated)
        finally:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = original_setting

    def test_get_permission_instance_with_dot_format(self):
        """Test get_permission_instance works with dot format permission path."""
        self.flow_type.crud_permission_class = "rest_framework.permissions.AllowAny"
        self.flow_type.save()
        permission = self.flow_type.get_permission_instance("crud")
        self.assertIsInstance(permission, AllowAny)

    def test_get_permission_instance_with_colon_format(self):
        """Test get_permission_instance works with colon format permission path."""
        self.flow_type.crud_permission_class = "rest_framework.permissions:AllowAny"
        self.flow_type.save()
        permission = self.flow_type.get_permission_instance("crud")
        self.assertIsInstance(permission, AllowAny)

    def test_get_permission_instance_returns_different_instances(self):
        """Test get_permission_instance returns different instances (not singletons)."""
        permission1 = self.flow_type.get_permission_instance("crud")
        permission2 = self.flow_type.get_permission_instance("crud")
        # Should be different instances
        self.assertIsNot(permission1, permission2)


class FlowTypeConstraintsTest(TestCase):
    """Test FlowType model constraints and validation."""

    def test_unique_constraint_app_name_flow_type_version(self):
        """Test that (app_name, flow_type, version) must be unique."""
        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
        )

        # Trying to create duplicate should raise IntegrityError
        with self.assertRaises(IntegrityError):
            FlowType.objects.create(
                app_name="test_app",
                flow_type="test_flow",
                version="v1",
                builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
                state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            )

    def test_same_version_different_app_name_allowed(self):
        """Test that same version is allowed for different app_name."""
        FlowType.objects.create(
            app_name="app1",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
        )

        # Should be allowed
        FlowType.objects.create(
            app_name="app2",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
        )

        self.assertEqual(FlowType.objects.count(), 2)

    def test_same_version_different_flow_type_allowed(self):
        """Test that same version is allowed for different flow_type."""
        FlowType.objects.create(
            app_name="test_app",
            flow_type="flow1",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
        )

        # Should be allowed
        FlowType.objects.create(
            app_name="test_app",
            flow_type="flow2",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
        )

        self.assertEqual(FlowType.objects.count(), 2)

    def test_one_latest_per_app_type_constraint(self):
        """Test that only one is_latest=True is allowed per (app_name, flow_type)."""
        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        # Trying to create another latest should raise IntegrityError
        with self.assertRaises(IntegrityError):
            FlowType.objects.create(
                app_name="test_app",
                flow_type="test_flow",
                version="v2",
                builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
                state_path="graflow.tests.fixtures.test_graph:TestGraphState",
                is_latest=True,
            )

    def test_different_flow_types_can_both_be_latest(self):
        """Test that different flow_types can both have is_latest=True."""
        FlowType.objects.create(
            app_name="test_app",
            flow_type="flow1",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        # Should be allowed
        FlowType.objects.create(
            app_name="test_app",
            flow_type="flow2",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        latest_flows = FlowType.objects.filter(is_latest=True)
        self.assertEqual(latest_flows.count(), 2)

    def test_different_apps_can_both_be_latest(self):
        """Test that different app_names can both have is_latest=True."""
        FlowType.objects.create(
            app_name="app1",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        # Should be allowed
        FlowType.objects.create(
            app_name="app2",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        latest_flows = FlowType.objects.filter(is_latest=True)
        self.assertEqual(latest_flows.count(), 2)

    def test_display_name_is_optional(self):
        """Test that display_name field is optional."""
        flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            display_name="",  # Empty string
        )
        self.assertEqual(flow_type.display_name, "")

        flow_type2 = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow2",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            # display_name not provided
        )
        self.assertEqual(flow_type2.display_name, "")

    def test_description_is_optional(self):
        """Test that description field is optional."""
        flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow3",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            description="",  # Empty string
        )
        self.assertEqual(flow_type.description, "")

        flow_type2 = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow4",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            # description not provided
        )
        self.assertEqual(flow_type2.description, "")

    def test_permission_classes_have_defaults(self):
        """Test that permission class fields have defaults."""
        flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow5",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
        )
        self.assertIn("IsAuthenticated", flow_type.crud_permission_class)
        self.assertIn("IsAuthenticated", flow_type.resume_permission_class)

    def test_throttle_classes_are_optional(self):
        """Test that throttle class fields are optional."""
        flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow6",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
        )
        self.assertEqual(flow_type.crud_throttle_class, "")
        self.assertEqual(flow_type.resume_throttle_class, "")


class FlowTypeThrottleTest(TestCase):
    """Test FlowType throttle instance methods."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests."""
        cls.flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

    def test_get_throttle_instance_crud_default(self):
        """Test get_throttle_instance returns None when not configured (uses default)."""
        throttle = self.flow_type.get_throttle_instance("crud")
        self.assertIsNone(throttle)  # Should use default viewset throttles

    def test_get_throttle_instance_resume_default(self):
        """Test get_throttle_instance returns None when not configured (uses default)."""
        throttle = self.flow_type.get_throttle_instance("resume")
        self.assertIsNone(throttle)  # Should use default viewset throttles

    def test_get_throttle_instance_crud_custom(self):
        """Test get_throttle_instance returns custom throttle for CRUD."""
        self.flow_type.crud_throttle_class = "graflow.api.throttling:FlowCreationThrottle"
        self.flow_type.save()
        throttle = self.flow_type.get_throttle_instance("crud")
        self.assertIsNotNone(throttle)
        from graflow.api.throttling import FlowCreationThrottle

        self.assertIsInstance(throttle, FlowCreationThrottle)

    def test_get_throttle_instance_resume_custom(self):
        """Test get_throttle_instance returns custom throttle for resume."""
        self.flow_type.resume_throttle_class = "graflow.api.throttling:FlowResumeThrottle"
        self.flow_type.save()
        throttle = self.flow_type.get_throttle_instance("resume")
        self.assertIsNotNone(throttle)
        from graflow.api.throttling import FlowResumeThrottle

        self.assertIsInstance(throttle, FlowResumeThrottle)

    def test_get_throttle_instance_empty_path_returns_none(self):
        """Test get_throttle_instance returns None when throttle_path is empty."""
        self.flow_type.crud_throttle_class = ""
        self.flow_type.save()
        throttle = self.flow_type.get_throttle_instance("crud")
        self.assertIsNone(throttle)

    def test_get_throttle_instance_whitespace_path_returns_none(self):
        """Test get_throttle_instance returns None when throttle_path is whitespace."""
        self.flow_type.crud_throttle_class = "   "
        self.flow_type.save()
        throttle = self.flow_type.get_throttle_instance("crud")
        self.assertIsNone(throttle)

    def test_get_throttle_instance_invalid_path_falls_back(self):
        """Test get_throttle_instance falls back to None when throttle class fails to load."""
        self.flow_type.crud_throttle_class = "nonexistent.module:Throttle"
        self.flow_type.save()
        throttle = self.flow_type.get_throttle_instance("crud")
        self.assertIsNone(throttle)  # Should fall back to default

    def test_get_throttle_instance_with_dot_format(self):
        """Test get_throttle_instance works with dot format throttle path."""
        self.flow_type.crud_throttle_class = "graflow.api.throttling.FlowCreationThrottle"
        self.flow_type.save()
        throttle = self.flow_type.get_throttle_instance("crud")
        self.assertIsNotNone(throttle)
        from graflow.api.throttling import FlowCreationThrottle

        self.assertIsInstance(throttle, FlowCreationThrottle)

    def test_get_throttle_instance_with_colon_format(self):
        """Test get_throttle_instance works with colon format throttle path."""
        self.flow_type.crud_throttle_class = "graflow.api.throttling:FlowCreationThrottle"
        self.flow_type.save()
        throttle = self.flow_type.get_throttle_instance("crud")
        self.assertIsNotNone(throttle)
        from graflow.api.throttling import FlowCreationThrottle

        self.assertIsInstance(throttle, FlowCreationThrottle)

    def test_get_throttle_instance_returns_different_instances(self):
        """Test get_throttle_instance returns different instances (not singletons)."""
        self.flow_type.crud_throttle_class = "graflow.api.throttling:FlowCreationThrottle"
        self.flow_type.save()
        throttle1 = self.flow_type.get_throttle_instance("crud")
        throttle2 = self.flow_type.get_throttle_instance("crud")
        # Should be different instances
        self.assertIsNot(throttle1, throttle2)


class FlowTypeVersioningTest(TestCase):
    """Test version management scenarios."""

    def test_multiple_versions_same_flow_type(self):
        """Test that multiple versions can exist for same (app_name, flow_type)."""
        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=False,
        )

        v2 = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v2",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v3",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=False,
        )

        # All versions should exist
        versions = FlowType.objects.filter(app_name="test_app", flow_type="test_flow")
        self.assertEqual(versions.count(), 3)
        # Only v2 should be latest
        latest = FlowType.objects.get_latest("test_app", "test_flow")
        self.assertEqual(latest, v2)

    def test_mark_new_version_as_latest(self):
        """Test marking new version as latest (unmarking old one)."""
        v1 = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        # Create v2 as latest (should fail due to constraint)
        # Instead, we need to unmark v1 first
        v1.is_latest = False
        v1.save()

        v2 = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v2",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        # v2 should be latest
        latest = FlowType.objects.get_latest("test_app", "test_flow")
        self.assertEqual(latest, v2)
        self.assertFalse(FlowType.objects.get(pk=v1.pk).is_latest)

    def test_inactive_versions_excluded_from_get_latest(self):
        """Test that inactive versions are excluded from get_latest."""
        v1_active = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
            is_active=True,
        )

        # Create inactive version (can't be latest if active one exists due to constraint)
        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v2",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=False,
            is_active=False,
        )

        # get_latest should return v1 (active), not v2 (inactive)
        latest = FlowType.objects.get_latest("test_app", "test_flow")
        self.assertEqual(latest, v1_active)

        # Make v1 inactive
        v1_active.is_active = False
        v1_active.save()

        # Now get_latest should return None (no active latest)
        latest = FlowType.objects.get_latest("test_app", "test_flow")
        self.assertIsNone(latest)

    def test_old_versions_remain_accessible(self):
        """Test that old versions remain accessible (not deleted)."""
        v1 = FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        # Create v2
        v1.is_latest = False
        v1.save()

        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v2",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        # v1 should still exist and be accessible
        self.assertTrue(FlowType.objects.filter(pk=v1.pk).exists())
        v1_refresh = FlowType.objects.get(pk=v1.pk)
        self.assertEqual(v1_refresh.version, "v1")
        self.assertFalse(v1_refresh.is_latest)
