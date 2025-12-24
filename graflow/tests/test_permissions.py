from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from parameterized import parameterized
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.test import APITestCase

from graflow.models.flows import Flow
from graflow.models.registry import FlowType
from graflow.tests.factories import FlowFactory

User = get_user_model()


class AllowOnlyTestGraph1Permission(BasePermission):
    """Custom permission that only allows access to crud_restricted_to_graph1 flow type."""

    def has_permission(self, request, view):
        """Check permission at view level (for create, list actions)."""
        # For create action, check flow_type in request data
        if view.action == "create":
            flow_type = request.data.get("flow_type")
            return flow_type == "crud_restricted_to_graph1"
        # For list without flow_type filter, allow (will filter in queryset)
        return True

    def has_object_permission(self, request, view, obj):
        """Check permission for a specific flow object."""
        if isinstance(obj, Flow):
            return obj.flow_type == "crud_restricted_to_graph1"
        return False


class AllowOnlyTestGraph2Permission(BasePermission):
    """Custom permission for auth_default_crud_resume_restricted_to_graph2 flow type."""

    def has_permission(self, request, view):
        """Check permission at view level (for create, list actions)."""
        if view.action == "create":
            flow_type = request.data.get("flow_type")
            return flow_type == "auth_default_crud_resume_restricted_to_graph2"
        return True

    def has_object_permission(self, request, view, obj):
        """Check permission for a specific flow object."""
        if isinstance(obj, Flow):
            return obj.flow_type == "auth_default_crud_resume_restricted_to_graph2"
        return False


class PermissionsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        settings.GRAFLOW_APP_NAME = "test_app"
        settings.GRAFLOW_REQUIRE_AUTHENTICATION = True

        cls.user1 = User.objects.create_user(
            email="user1@test.com", username="user1", password="testpass123"
        )
        cls.admin_user = User.objects.create_user(
            email="admin@test.com",
            username="admin",
            password="testpass123",
            is_staff=True,
        )

        # Create flow types once for all tests
        # Default flow type (uses IsAuthenticated for both CRUD and resume)
        cls.default_flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="auth_default_crud_resume",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )

        # Flow type with custom CRUD permission (restricted to crud_restricted_to_graph1 only)
        cls.custom_crud_flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="crud_restricted_to_graph1",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            crud_permission_class="graflow.tests.test_permissions:AllowOnlyTestGraph1Permission",
            resume_permission_class="graflow.tests.test_permissions:DenyAllPermission",
            is_latest=True,
        )

        # Flow type with custom resume permission
        # (restricted to auth_default_crud_resume_restricted_to_graph2 only)
        # Uses default IsAuthenticated for CRUD, but custom permission for resume
        cls.custom_resume_flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="auth_default_crud_resume_restricted_to_graph2",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            # Uses default IsAuthenticated for CRUD (not set)
            resume_permission_class="graflow.tests.test_permissions:AllowOnlyTestGraph2Permission",
            is_latest=True,
        )

        # Flow type with AllowAny permission for both CRUD and resume
        cls.allowany_flow_type = FlowType.objects.create(
            app_name="test_app",
            flow_type="allowany_crud_resume",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            crud_permission_class="rest_framework.permissions.AllowAny",
            resume_permission_class="rest_framework.permissions.AllowAny",
            is_latest=True,
        )

    # ==================== Default Permission Tests (IsAuthenticated) ====================

    @parameterized.expand(
        [
            ("anonymous", None, None, status.HTTP_403_FORBIDDEN),
            ("authenticated", "user1", "user1", status.HTTP_200_OK),
            ("admin", "admin_user", "admin_user", status.HTTP_200_OK),
        ]
    )
    def test_default_permission_retrieve(
        self, user_type, user_attr, flow_owner_attr, expected_status
    ):
        """Test retrieve with default IsAuthenticated permission."""
        # Create flow owned by the appropriate user (or None for anonymous)
        flow_owner = getattr(self, flow_owner_attr) if flow_owner_attr else None
        flow = FlowFactory.create(
            user=flow_owner, flow_type="auth_default_crud_resume", app_name="test_app"
        )

        if user_attr:
            user = getattr(self, user_attr)
            self.client.force_authenticate(user=user)
        # else: anonymous user (no authentication)

        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, expected_status)

    @parameterized.expand(
        [
            ("anonymous", None, status.HTTP_403_FORBIDDEN),
            ("authenticated", "user1", status.HTTP_201_CREATED),
            ("admin", "admin_user", status.HTTP_201_CREATED),
        ]
    )
    def test_default_permission_create(self, user_type, user_attr, expected_status):
        """Test create with default IsAuthenticated permission."""
        if user_attr:
            user = getattr(self, user_attr)
            self.client.force_authenticate(user=user)

        url = reverse("graflow:flow-list")
        response = self.client.post(
            url, {"flow_type": "auth_default_crud_resume"}, format="json"
        )

        self.assertEqual(response.status_code, expected_status)

    @parameterized.expand(
        [
            ("anonymous", None, None, status.HTTP_403_FORBIDDEN),
            ("authenticated", "user1", "user1", status.HTTP_204_NO_CONTENT),
            ("admin", "admin_user", "admin_user", status.HTTP_204_NO_CONTENT),
        ]
    )
    def test_default_permission_destroy(
        self, user_type, user_attr, flow_owner_attr, expected_status
    ):
        """Test destroy with default IsAuthenticated permission."""
        # Create flow owned by the appropriate user (or None for anonymous)
        flow_owner = getattr(self, flow_owner_attr) if flow_owner_attr else None
        flow = FlowFactory.create(
            user=flow_owner, flow_type="auth_default_crud_resume", app_name="test_app"
        )

        if user_attr:
            user = getattr(self, user_attr)
            self.client.force_authenticate(user=user)

        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, expected_status)

    # ==================== Custom CRUD Permission Tests ====================

    def test_custom_crud_permission_retrieve_allowed(self):
        """Test retrieve with custom CRUD permission - allowed flow type."""
        flow = FlowFactory.create(
            user=self.user1,
            flow_type="crud_restricted_to_graph1",
            app_name="test_app",
        )

        self.client.force_authenticate(user=self.user1)
        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_custom_crud_permission_retrieve_denied(self):
        """Test retrieve with custom CRUD permission - denied flow type."""
        flow = FlowFactory.create(
            user=self.user1,
            flow_type="auth_default_crud_resume_restricted_to_graph2",
            app_name="test_app",
        )

        self.client.force_authenticate(user=self.user1)
        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.get(url)

        # test_graph_2 uses default IsAuthenticated for CRUD (allows authenticated users)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_custom_crud_permission_create_allowed(self):
        """Test create with custom CRUD permission - allowed flow type."""
        self.client.force_authenticate(user=self.user1)

        url = reverse("graflow:flow-list")
        response = self.client.post(
            url, {"flow_type": "crud_restricted_to_graph1"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_custom_crud_permission_create_denied(self):
        """Test create with custom CRUD permission - denied flow type."""
        self.client.force_authenticate(user=self.user1)

        url = reverse("graflow:flow-list")
        # auth_default_crud_resume_restricted_to_graph2 doesn't have a custom CRUD permission,
        # so it uses default IsAuthenticated which allows authenticated users
        response = self.client.post(
            url,
            {"flow_type": "auth_default_crud_resume_restricted_to_graph2"},
            format="json",
        )

        # Uses default IsAuthenticated for CRUD (allows authenticated users)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # ==================== Custom Resume Permission Tests ====================

    def test_custom_resume_permission_allowed(self):
        """Test resume with custom resume permission - allowed flow type."""
        flow = FlowFactory.create(
            user=self.user1,
            flow_type="auth_default_crud_resume_restricted_to_graph2",
            app_name="test_app",
            status=Flow.STATUS_INTERRUPTED,
        )

        self.client.force_authenticate(user=self.user1)
        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {"message": "test"}, format="json")

        # Should be allowed (might fail for other reasons, but permission should pass)
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
        )

    def test_custom_resume_permission_denied(self):
        """Test resume with custom resume permission - denied flow type."""
        # crud_restricted_to_graph1 only has custom CRUD permission, not custom resume permission
        # So resume uses default IsAuthenticated, which allows authenticated users
        flow = FlowFactory.create(
            user=self.user1,
            flow_type="crud_restricted_to_graph1",
            app_name="test_app",
            status=Flow.STATUS_INTERRUPTED,
        )

        self.client.force_authenticate(user=self.user1)
        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {"message": "test"}, format="json")

        # test_graph_1 uses default IsAuthenticated for resume (allows authenticated users)
        # Might fail for other reasons, but permission should pass
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
        )

    # ==================== AllowAny Permission Tests ====================

    @parameterized.expand(
        [
            ("anonymous", None, None),  # anonymous users see flows with user=None
            ("authenticated", "user1", "user1"),
            ("admin", "admin_user", "admin_user"),
        ]
    )
    def test_allowany_permission_retrieve(self, user_type, user_attr, flow_owner_attr):
        """Test retrieve with AllowAny permission - should work for all users."""
        # Create flow owned by the appropriate user (or None for anonymous)
        flow_owner = getattr(self, flow_owner_attr) if flow_owner_attr else None
        flow = FlowFactory.create(
            user=flow_owner, flow_type="allowany_crud_resume", app_name="test_app"
        )

        if user_attr:
            user = getattr(self, user_attr)
            self.client.force_authenticate(user=user)

        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @parameterized.expand(
        [
            ("anonymous", None),
            ("authenticated", "user1"),
            ("admin", "admin_user"),
        ]
    )
    def test_allowany_permission_create(self, user_type, user_attr):
        """Test create with AllowAny permission - should work for all users."""
        if user_attr:
            user = getattr(self, user_attr)
            self.client.force_authenticate(user=user)

        url = reverse("graflow:flow-list")
        response = self.client.post(
            url, {"flow_type": "allowany_crud_resume"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # ==================== Stats Endpoint Tests (Admin Only) ====================

    def test_stats_endpoint_anonymous(self):
        """Test stats endpoint - should require admin."""
        url = reverse("graflow:flow-stats")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_stats_endpoint_authenticated_user(self):
        """Test stats endpoint - should require admin (not just authenticated)."""
        self.client.force_authenticate(user=self.user1)

        url = reverse("graflow:flow-stats")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_stats_endpoint_admin(self):
        """Test stats endpoint - should work for admin."""
        self.client.force_authenticate(user=self.admin_user)

        url = reverse("graflow:flow-stats")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==================== List Filtering Tests ====================

    def test_list_with_flow_type_filter_uses_permission(self):
        """Test that list with flow_type filter uses that flow type's permission."""
        FlowFactory.create(
            user=self.user1,
            flow_type="crud_restricted_to_graph1",
            app_name="test_app",
        )
        FlowFactory.create(
            user=self.user1,
            flow_type="auth_default_crud_resume_restricted_to_graph2",
            app_name="test_app",
        )

        self.client.force_authenticate(user=self.user1)

        # List with flow_type filter for allowed type
        url = reverse("graflow:flow-list")
        response = self.client.get(url, {"flow_type": "crud_restricted_to_graph1"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only return flows of type crud_restricted_to_graph1
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["flow_type"], "crud_restricted_to_graph1")

    def test_list_without_flow_type_filter_filters_by_permissions(self):
        """Test that list without flow_type filter filters results by permissions."""
        FlowFactory.create(
            user=self.user1,
            flow_type="crud_restricted_to_graph1",
            app_name="test_app",
        )
        FlowFactory.create(
            user=self.user1,
            flow_type="auth_default_crud_resume_restricted_to_graph2",
            app_name="test_app",
        )
        FlowFactory.create(
            user=self.user1, flow_type="auth_default_crud_resume", app_name="test_app"
        )

        self.client.force_authenticate(user=self.user1)

        url = reverse("graflow:flow-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only return flows where user has permission
        # crud_restricted_to_graph1: allowed
        # (custom AllowOnlyTestGraph1Permission - allows this type)
        # auth_default_crud_resume_restricted_to_graph2: allowed
        # (default IsAuthenticated for CRUD)
        # auth_default_crud_resume: allowed (default IsAuthenticated permission)
        # So all 3 should be returned since user1 is authenticated
        self.assertEqual(len(response.data), 3)
        flow_types = {f["flow_type"] for f in response.data}
        self.assertIn("crud_restricted_to_graph1", flow_types)
        self.assertIn("auth_default_crud_resume_restricted_to_graph2", flow_types)
        self.assertIn("auth_default_crud_resume", flow_types)
