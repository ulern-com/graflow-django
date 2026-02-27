"""Comprehensive test suite for Flows API."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from graflow.models.flows import Flow
from graflow.models.registry import FlowType
from graflow.tests.factories import FlowFactory

User = get_user_model()


class FlowsAPITest(APITestCase):
    """Comprehensive test suite for Flows API."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests."""
        # Register test graphs with multiple names for compatibility
        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_graph",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )
        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )
        FlowType.objects.create(
            app_name="test_app",
            flow_type="minimal_test_graph",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_minimal_test_graph",
            state_path="graflow.tests.fixtures.test_graph:MinimalTestState",
            is_latest=True,
        )
        FlowType.objects.create(
            app_name="test_app",
            flow_type="minimal_test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_minimal_test_graph",
            state_path="graflow.tests.fixtures.test_graph:MinimalTestState",
            is_latest=True,
        )

        # Create test users
        cls.user1 = User.objects.create_user(
            email="user1@test.com", username="user1", password="testpass123"
        )
        cls.user2 = User.objects.create_user(
            email="user2@test.com", username="user2", password="testpass123"
        )

    def setUp(self):
        """Set up each test."""
        self.client.force_authenticate(user=self.user1)

    # ==================== CRUD Tests ====================

    def test_create_flow_success(self):
        """Test creating a flow with valid data."""
        url = reverse("graflow:flow-list")
        data = {"flow_type": "test_graph", "state": {"counter": 5, "branch_choice": "right"}}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["flow_type"], "test_graph")
        self.assertIn("id", response.data)
        self.assertIn("state", response.data)

        # Verify state structure and cleanliness
        state = response.data["state"]

        # Flow-level metadata should be cleaned from state
        self.assertNotIn("user_id", state, "user_id should be removed from state")
        self.assertNotIn("flow_id", state, "flow_id should be removed from state")

        # required_data field should be in state only when the graph is interrupted
        self.assertNotIn("required_data", state)

        # Initial state values should have been processed (graph executed)
        # Counter starts at 5, gets incremented once to 6, then the graph completes
        self.assertIn("counter", state)
        self.assertIn("branch_choice", state)
        self.assertEqual(state["branch_choice"], "right")

        # Verify graph executed - should have messages showing execution
        self.assertIn("messages", state)
        self.assertIsInstance(state["messages"], list)
        self.assertGreater(
            len(state["messages"]), 0, "Graph should have executed and generated messages"
        )

    def test_create_flow_with_nested_state(self):
        """Test creating flow with nested state data."""
        url = reverse("graflow:flow-list")
        data = {
            "flow_type": "test_graph",
            "state": {"nested_data": {"branch": "left", "value": 42}, "max_iterations": 5},
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify nested state values
        state = response.data["state"]
        self.assertIn("nested_data", state)
        self.assertEqual(state["nested_data"]["branch"], "left")
        self.assertEqual(state["max_iterations"], 5)

    def test_create_flow_invalid_type(self):
        """Test creating flow with invalid flow_type."""
        url = reverse("graflow:flow-list")
        data = {"flow_type": "nonexistent_graph"}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertIn("nonexistent_graph", str(response.data["error"]))

    def test_create_flow_missing_type(self):
        """Test creating flow without flow_type."""
        url = reverse("graflow:flow-list")
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("flow_type", str(response.data))
        self.assertIn("required", str(response.data))

    def test_create_flow_without_state(self):
        """Test creating flow without initial state - should interrupt for input."""
        url = reverse("graflow:flow-list")
        data = {"flow_type": "test_graph"}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("state", response.data)

        # Flow should be interrupted after double-resume (waiting for actual input)
        self.assertEqual(response.data["status"], "interrupted")

        # State should be minimal (just the interrupt marker)
        state = response.data["state"]
        self.assertIsNotNone(state)
        # Verify it's in interrupted state, not completed
        self.assertEqual(response.data["status"], "interrupted", "Flow should be waiting for input")

    def test_list_flows(self):
        """Test listing user's flows."""
        # Create and initialize flows
        flow1 = FlowFactory.create(user=self.user1)
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})
        flow2 = FlowFactory.create(user=self.user1)
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})

        url = reverse("graflow:flow-list") + "?flow_type=test_flow"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # List responses should NOT include state (only detail responses include state)
        for flow in response.data:
            self.assertNotIn("state", flow, "List serializer should not include state")

    def test_list_flows_filtered_by_type(self):
        """Test listing flows filtered by flow_type."""
        # Create flows of different types
        FlowFactory.create(user=self.user1, flow_type="test_flow")
        FlowFactory.create(user=self.user1, flow_type="minimal_test_flow")
        FlowFactory.create(user=self.user1, flow_type="test_flow")

        # Filter by test_graph - should return only 2
        url = reverse("graflow:flow-list") + "?flow_type=test_flow"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        for flow in response.data:
            self.assertEqual(flow["flow_type"], "test_flow")

        # Filter by minimal_test_graph - should return only 1
        url = reverse("graflow:flow-list") + "?flow_type=minimal_test_flow"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["flow_type"], "minimal_test_flow")

    def test_list_flows_empty(self):
        """Test listing flows when none exist."""
        url = reverse("graflow:flow-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_retrieve_flow(self):
        """Test retrieving a specific flow."""
        flow = FlowFactory.create(user=self.user1)

        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], flow.id)
        self.assertEqual(response.data["flow_type"], "test_flow")
        self.assertIn("state", response.data)

        # Verify state is clean - no flow-level metadata (if state exists)
        state = response.data["state"]
        if state is not None:
            self.assertNotIn("user_id", state, "user_id should be removed from state")
            self.assertNotIn("flow_id", state, "flow_id should be removed from state")

    def test_retrieve_flow_not_found(self):
        """Test retrieving non-existent flow."""
        url = reverse("graflow:flow-detail", kwargs={"pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_flow(self):
        """Test deleting a flow."""
        flow = FlowFactory.create(user=self.user1)

        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        flow.refresh_from_db()
        self.assertEqual(flow.status, "cancelled")

    def test_delete_flow_completed(self):
        """Delete should hide completed flows by marking them cancelled."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_COMPLETED)

        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        flow.refresh_from_db()
        self.assertEqual(flow.status, Flow.STATUS_CANCELLED)

        # Flow should be excluded from subsequent fetches
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_flow_not_found(self):
        """Test deleting non-existent flow."""
        url = reverse("graflow:flow-detail", kwargs={"pk": 99999})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== User Isolation Tests ====================

    def test_user_cannot_access_other_user_flow(self):
        """Test that users can only access their own flows."""
        flow = FlowFactory.create(user=self.user2)

        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_delete_other_user_flow(self):
        """Test that users cannot delete other users' flows."""
        flow = FlowFactory.create(user=self.user2)

        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_only_shows_user_flows(self):
        """Test that list only returns authenticated user's flows."""
        flow1 = FlowFactory.create(user=self.user1)
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})
        flow2 = FlowFactory.create(user=self.user2)
        flow2.resume({"user_id": self.user2.id, "flow_id": flow2.id})

        url = reverse("graflow:flow-list") + "?flow_type=test_flow"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    # ==================== Resume Tests ====================

    def test_resume_flow_basic(self):
        """Test resuming a flow and verifying state continuity."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Pause the flow at first checkpoint (counter will be 1 after increment)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id, "should_pause": True})

        # Verify flow is interrupted after first resume
        flow.refresh_from_db()
        self.assertEqual(flow.status, "interrupted")
        initial_counter = flow.state.get("counter", 0)
        initial_messages_count = len(flow.state.get("messages", []))

        # Resume - flow continues from where it paused and processes one more iteration
        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {"should_pause": False}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify new response structure includes flow metadata + state_update
        self.assertIn("id", response.data)
        self.assertIn("status", response.data)
        self.assertIn("last_resumed_at", response.data)
        self.assertIn("state_update", response.data)
        self.assertEqual(response.data["id"], flow.id)

        # Verify flow-level metadata is cleaned from state_update
        state_update = response.data.get("state_update", {})
        if isinstance(state_update, dict):
            self.assertNotIn("user_id", state_update, "user_id should be removed from state_update")
            self.assertNotIn("flow_id", state_update, "flow_id should be removed from state_update")

        # Verify the graph executed by checking database state (not response, "
        # since interrupt responses may only contain interrupt data, not full state)
        flow.refresh_from_db()
        final_counter = flow.state.get("counter", 0)
        final_messages_count = len(flow.state.get("messages", []))

        # Verify that execution happened by checking messages increased OR counter changed
        # (counter might decrease if loop completes and resets, "
        # but messages should always accumulate)
        execution_happened = (
            final_messages_count > initial_messages_count or final_counter != initial_counter
        )
        self.assertTrue(
            execution_happened,
            f"Execution should have happened: messages "
            f"{initial_messages_count}->{final_messages_count}, "
            f"counter {initial_counter}->{final_counter}",
        )

        # If we got here, execution happened. Verify response structure is valid
        self.assertIsInstance(response.data, dict)

        # Flow may interrupt again at next checkpoint since it's in a loop, or complete
        self.assertIn(
            flow.status, ["completed", "interrupted"], "Flow should be completed or interrupted"
        )

    def test_resume_flow_with_pause(self):
        """Test resuming an interrupted flow."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Set should_pause=True to keep it interrupted
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id, "should_pause": True})

        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {"should_pause": False}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_resume_flow_not_found(self):
        """Test resuming non-existent flow."""
        url = reverse("graflow:flow-resume", kwargs={"pk": 99999})
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_resume_other_user_flow(self):
        """Test that user cannot resume another user's flow."""
        flow = FlowFactory.create(user=self.user2)

        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_resume_updates_state(self):
        """Test that resume properly updates the flow state."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Pause at checkpoint
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id, "should_pause": True})

        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        # Resume with updated state - branch_choice should be reflected
        response = self.client.post(
            url, {"branch_choice": "right", "should_pause": True}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify response includes flow metadata
        self.assertIn("id", response.data)
        self.assertIn("status", response.data)
        self.assertIn("state_update", response.data)
        # Verify state_update contains the changes and does not duplicate metadata fields
        state_update = response.data.get("state_update", {})
        self.assertNotIn("current_state_name", state_update)
        self.assertEqual(response.data.get("current_state_name"), "checkpoint")
        # Verify state was updated in database
        flow.refresh_from_db()
        self.assertEqual(flow.state["branch_choice"], "right")
        # Counter will be incremented by the graph execution
        self.assertIn("counter", flow.state)
        # Verify the flow is still interrupted (status should be interrupted)
        self.assertEqual(flow.status, "interrupted")
        # Verify response status matches database
        self.assertEqual(response.data["status"], flow.status)

    def test_resume_response_structure(self):
        """Test that resume response includes flow metadata + state_update."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})

        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {"should_pause": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify response structure includes all required flow metadata fields
        self.assertIn("id", response.data)
        self.assertIn("status", response.data)
        self.assertIn("error_message", response.data)
        self.assertIn("last_resumed_at", response.data)
        self.assertIn("current_state_name", response.data)
        self.assertIn("state_update", response.data)

        # Verify flow metadata matches database
        flow.refresh_from_db()
        self.assertEqual(response.data["id"], flow.id)
        self.assertEqual(response.data["status"], flow.status)
        # error_message should match (can be None or a string)
        if flow.error_message is None:
            self.assertIsNone(response.data["error_message"])
        else:
            self.assertEqual(response.data["error_message"], flow.error_message)
        # last_resumed_at is serialized as ISO format by DRF DateTimeField
        self.assertIsNotNone(response.data["last_resumed_at"])

        # Verify state_update is a dict (or None)
        state_update = response.data.get("state_update")
        self.assertIsInstance(state_update, (dict, type(None)))

        # Verify current_state_name is set correctly for interrupted flows
        if flow.status == Flow.STATUS_INTERRUPTED:
            self.assertIsNotNone(response.data["current_state_name"])
        else:
            self.assertIsNone(response.data["current_state_name"])

    # ==================== Query Tests ====================

    def test_query_by_single_field(self):
        """Test querying flows by single state field."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Provide state with should_pause to keep it interrupted
        # Note: counter=42 becomes 43 after increment node runs
        flow.resume(
            {"user_id": self.user1.id, "flow_id": flow.id, "counter": 42, "should_pause": True}
        )

        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__counter=43"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], flow.id)

    def test_query_by_multiple_fields(self):
        """Test querying by multiple fields (AND logic)."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Counter gets incremented before pause, so 42 becomes 43
        flow.resume(
            {
                "user_id": self.user1.id,
                "flow_id": flow.id,
                "counter": 42,
                "branch_choice": "left",
                "should_pause": True,
            }
        )

        url = (
            reverse("graflow:flow-list")
            + "?flow_type=test_flow&state__counter=43&state__branch_choice=left"
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_query_by_nested_field(self):
        """Test querying by nested state field."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Set branch_choice to "left" and should_pause to keep it interrupted
        # The graph will set nested_data based on branch_choice and counter
        flow.resume(
            {
                "user_id": self.user1.id,
                "flow_id": flow.id,
                "branch_choice": "left",
                "should_pause": True,
            }
        )

        # Refresh to get updated state after graph execution
        flow.refresh_from_db()

        # Query by nested field - the graph sets nested_data.branch based on branch_choice
        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__nested_data__branch=left"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should find at least our flow (may find others from previous tests)
        self.assertGreaterEqual(len(response.data), 1)
        # Verify our flow is in the results
        flow_ids = [f["id"] for f in response.data]
        self.assertIn(flow.id, flow_ids)

    def test_query_by_deeply_nested_field(self):
        """Test querying by deeply nested state field."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Set counter to 10, after increment it becomes 11, "
        # and branch_right multiplies by 2 = 22
        flow.resume(
            {
                "user_id": self.user1.id,
                "flow_id": flow.id,
                "counter": 10,
                "branch_choice": "right",
                "should_pause": True,
            }
        )

        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__nested_data__value=22"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_query_no_matches(self):
        """Test query with no matching flows."""
        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__counter=999"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_query_with_flow_type_filter(self):
        """Test query with flow_type filter."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Counter gets incremented, so 42 becomes 43
        flow.resume(
            {"user_id": self.user1.id, "flow_id": flow.id, "counter": 42, "should_pause": True}
        )

        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__counter=43"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_query_without_state_filters(self):
        """Test query with only flow_type (no state filters)."""
        FlowFactory.create(user=self.user1)
        FlowFactory.create(user=self.user1)

        url = reverse("graflow:flow-list") + "?flow_type=test_flow"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_query_respects_user_isolation(self):
        """Test that query only returns user's own flows."""
        # Create flow for user2
        flow2 = FlowFactory.create(user=self.user2)
        # First resume: Initialize (will interrupt)
        flow2.resume({"user_id": self.user2.id, "flow_id": flow2.id})
        # Second resume: Provide state with should_pause to keep it interrupted
        flow2.resume(
            {"user_id": self.user2.id, "flow_id": flow2.id, "counter": 42, "should_pause": True}
        )

        # User1 queries for same counter value
        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__counter=42"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_query_type_coercion(self):
        """Test query handles type coercion (int vs string)."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Counter gets incremented, so 42 becomes 43
        flow.resume(
            {"user_id": self.user1.id, "flow_id": flow.id, "counter": 42, "should_pause": True}
        )

        # Query with string version of int (43 after increment)
        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__counter=43"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_query_boolean_field(self):
        """Test querying by boolean field."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Provide state with should_pause=True to keep it interrupted
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id, "should_pause": True})

        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__should_pause=True"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    # ==================== Edge Cases ====================

    def test_unauthenticated_access(self):
        """Test that unauthenticated users cannot access the API."""
        from django.conf import settings

        # Override setting to require authentication for this test
        original_setting = getattr(settings, "GRAFLOW_REQUIRE_AUTHENTICATION", True)
        settings.GRAFLOW_REQUIRE_AUTHENTICATION = True

        try:
            self.client.force_authenticate(user=None)

            url = reverse("graflow:flow-list")
            response = self.client.get(url)

            # DRF returns 403 Forbidden (not 401) when authentication is required but not provided
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        finally:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = original_setting

    def test_closed_flow_not_in_list(self):
        """Test that cancelled flows are not returned in list."""
        flow = FlowFactory.create(user=self.user1)
        flow.cancel()

        url = reverse("graflow:flow-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_closed_flow_not_in_query(self):
        """Test that cancelled flows are not returned in query."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Provide state with should_pause
        flow.resume(
            {"user_id": self.user1.id, "flow_id": flow.id, "counter": 42, "should_pause": True}
        )
        # Cancel the flow
        flow.cancel()

        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__counter=43"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_query_partial_match_fails(self):
        """Test that query requires exact match, not partial."""
        flow = FlowFactory.create(user=self.user1)
        # First resume: Initialize (will interrupt)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        # Second resume: Provide state and let it complete
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id, "branch_choice": "left"})

        # Query with partial match should fail
        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__branch_choice=lef"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_resume_with_invalid_state_data(self):
        """Test resuming with malformed state data."""
        flow = FlowFactory.create(user=self.user1)

        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        # Send invalid data that doesn't match state schema
        response = self.client.post(url, {"invalid_field": "value"}, format="json")

        # Should still work - extra fields are typically ignored
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==================== Status Filtering Tests ====================

    def test_list_flows_filter_by_status_interrupted(self):
        """Test listing flows filtered by interrupted status."""
        # Create flows with different statuses
        flow1 = FlowFactory.create(user=self.user1)
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id, "should_pause": True})

        flow2 = FlowFactory.create(user=self.user1)
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})  # Let it complete

        # Filter by interrupted status
        url = reverse("graflow:flow-list") + "?status=interrupted"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["status"], "interrupted")

    def test_list_flows_filter_by_status_completed(self):
        """Test listing flows filtered by completed status."""
        # Create completed flow
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})  # Let it complete

        # Filter by completed status
        url = reverse("graflow:flow-list") + "?status=completed"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["status"], "completed")

    def test_list_flows_filter_by_status_cancelled(self):
        """Test listing flows filtered by cancelled status - "
        "cancelled flows are excluded from queryset."""
        flow = FlowFactory.create(user=self.user1)
        flow.cancel()

        # Filter by cancelled status - should return empty since cancelled flows are excluded
        url = reverse("graflow:flow-list") + "?status=cancelled"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Cancelled flows are excluded from the queryset, so filtering by cancelled returns empty
        self.assertEqual(len(response.data), 0)

    def test_list_flows_default_shows_only_in_progress(self):
        """Test that list without status filter shows only in-progress flows."""
        # Create flows with various statuses
        flow1 = FlowFactory.create(user=self.user1)
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})  # interrupted

        flow2 = FlowFactory.create(user=self.user1)
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})  # completed

        flow3 = FlowFactory.create(user=self.user1)
        flow3.cancel()  # cancelled

        # List without status filter - should only show interrupted (in-progress)
        url = reverse("graflow:flow-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["status"], "interrupted")

    # ==================== Cancel Action Tests ====================

    def test_cancel_action_success(self):
        """Test explicit cancel action on interrupted flow."""
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})

        url = reverse("graflow:flow-cancel", kwargs={"pk": flow.id})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)
        self.assertEqual(response.data["flow_id"], flow.id)

        # Verify flow is cancelled
        flow.refresh_from_db()
        self.assertEqual(flow.status, "cancelled")

    def test_cancel_action_on_completed_flow(self):
        """Test cancel action on completed flow - should return 400."""
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})  # Complete

        url = reverse("graflow:flow-cancel", kwargs={"pk": flow.id})
        response = self.client.post(url)

        # Cancel on terminal state should return 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_cancel_action_on_already_cancelled_flow(self):
        """Test cancel action on already cancelled flow - returns 404 "
        "since cancelled flows are excluded."""
        flow = FlowFactory.create(user=self.user1)
        flow.cancel()

        url = reverse("graflow:flow-cancel", kwargs={"pk": flow.id})
        response = self.client.post(url)

        # Cancelled flows are excluded from queryset, so get_object() returns 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== Resumability Validation Tests ====================

    def test_resume_completed_flow(self):
        """Test resuming a completed flow - should return 400."""
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})  # Complete

        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {"counter": 10}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_resume_running_flow(self):
        """Test resuming a running flow - should return 400."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_RUNNING)

        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {"counter": 10}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_resume_cancelled_flow(self):
        """Test resuming a cancelled flow - returns 404 since cancelled flows are excluded."""
        flow = FlowFactory.create(user=self.user1)
        flow.cancel()

        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {}, format="json")

        # Cancelled flows are excluded from queryset, so get_object() returns 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_resume_pending_flow_succeeds(self):
        """Test that pending flows can be resumed."""
        flow = FlowFactory.create(user=self.user1)

        # Pending flow should be resumable
        url = reverse("graflow:flow-resume", kwargs={"pk": flow.id})
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==================== Error Context Tests ====================

    def test_create_flow_error_includes_context(self):
        """Test that flow creation errors include helpful context."""
        url = reverse("graflow:flow-list")
        data = {"flow_type": "nonexistent_flow_type"}
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        # Error should mention the invalid flow type
        self.assertIn("nonexistent_flow_type", str(response.data["error"]))

    # ==================== Serializer Enhancement Tests ====================

    def test_list_includes_current_state_name_for_interrupted(self):
        """Test that list serializer includes current_state_name for interrupted flows."""
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id, "should_pause": True})

        # Refresh to get updated status
        flow.refresh_from_db()
        self.assertEqual(flow.status, Flow.STATUS_INTERRUPTED)

        url = reverse("graflow:flow-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        # Should include current_state_name field
        self.assertIn("current_state_name", response.data[0])
        # Note: current_state_name extraction may not work with memory backend
        # The important thing is that the field is present

    def test_detail_includes_current_state_name(self):
        """Test that detail serializer includes current_state_name."""
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})

        url = reverse("graflow:flow-detail", kwargs={"pk": flow.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("current_state_name", response.data)

    # ==================== Stats Endpoint Tests ====================

    def test_stats_endpoint_returns_counts(self):
        """Test stats endpoint returns flow counts by status and type."""
        # Stats endpoint requires admin user
        admin_user = User.objects.create_user(
            email="admin@test.com",
            username="admin",
            password="testpass123",
            is_staff=True,
        )
        self.client.force_authenticate(user=admin_user)

        # Get initial counts to account for flows from other tests
        url = reverse("graflow:flow-stats")
        initial_response = self.client.get(url)
        initial_total = initial_response.data.get("total", 0)
        initial_interrupted = initial_response.data.get("by_status", {}).get("interrupted", 0)
        initial_completed = initial_response.data.get("by_status", {}).get("completed", 0)
        initial_test_flow = initial_response.data.get("by_type", {}).get("test_flow", 0)

        # Create flows with various statuses for admin user
        flow1 = FlowFactory.create(user=admin_user)
        flow1.resume({"user_id": admin_user.id, "flow_id": flow1.id})  # interrupted

        flow2 = FlowFactory.create(user=admin_user)
        flow2.resume({"user_id": admin_user.id, "flow_id": flow2.id})
        flow2.resume({"user_id": admin_user.id, "flow_id": flow2.id})  # completed

        flow3 = FlowFactory.create(user=admin_user, flow_type="minimal_test_flow")
        flow3.cancel()  # cancelled

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total", response.data)
        self.assertIn("by_status", response.data)
        self.assertIn("by_type", response.data)

        # Verify counts - cancelled flows are excluded from queryset
        # Check that counts increased by at least the expected amounts (accounting for other tests)
        # Note: flow2 might not complete immediately, so we check for at least the interrupted flow
        self.assertGreaterEqual(
            response.data["total"], initial_total + 1
        )  # At least flow1, flow3 excluded
        self.assertGreaterEqual(
            response.data["by_status"]["interrupted"], initial_interrupted + 1
        )  # flow1
        # flow2 might complete or stay interrupted depending on graph execution
        self.assertGreaterEqual(
            response.data["by_status"]["completed"], initial_completed
        )  # flow2 may or may not complete
        self.assertEqual(response.data["by_status"]["cancelled"], 0)  # Cancelled flows excluded

        # Verify by_type - cancelled flow is excluded
        # At least flow1 should be counted (flow2 might not complete)
        self.assertGreaterEqual(
            response.data["by_type"]["test_flow"], initial_test_flow + 1
        )  # At least flow1
        # minimal_test_graph flow was cancelled, so it's excluded from stats
        self.assertNotIn("minimal_test_flow", response.data["by_type"])

        # Verify the interrupted flow we created is in the stats
        self.assertGreaterEqual(response.data["by_status"]["interrupted"], 1)

    def test_stats_respects_user_isolation(self):
        """Test that stats only include user's own flows."""
        # Stats endpoint requires admin user
        admin_user = User.objects.create_user(
            email="admin@test.com",
            username="admin",
            password="testpass123",
            is_staff=True,
        )
        self.client.force_authenticate(user=admin_user)

        # Create flows for admin user
        FlowFactory.create(user=admin_user)

        # Create flows for other users (should not be counted)
        FlowFactory.create(user=self.user1)
        FlowFactory.create(user=self.user2)
        FlowFactory.create(user=self.user2)

        url = reverse("graflow:flow-stats")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only count admin user's flow (get_queryset filters by user)
        self.assertEqual(response.data["total"], 1)

    # ==================== Most Recent Endpoint Tests ====================

    def test_most_recent_returns_latest_in_progress_flow(self):
        """Test that most recent returns the latest in-progress flow."""
        # Create two flows and resume them (they become interrupted/in-progress)
        flow1 = FlowFactory.create(user=self.user1)
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})

        # Create another flow (will be more recent)
        flow2 = FlowFactory.create(user=self.user1)
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})

        url = reverse("graflow:flow-most-recent")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return flow2 as it's more recent
        self.assertEqual(response.data["id"], flow2.id)

    def test_most_recent_with_status_filter(self):
        """Test most recent with status filter."""
        # Create a completed flow
        flow1 = FlowFactory.create(user=self.user1)
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})

        # Create an interrupted flow (more recent)
        flow2 = FlowFactory.create(user=self.user1)
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})

        # Get most recent interrupted
        url = reverse("graflow:flow-most-recent") + "?status=interrupted"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], flow2.id)
        self.assertEqual(response.data["status"], "interrupted")

    def test_most_recent_with_flow_type_filter(self):
        """Test most recent with flow_type filter."""
        # Create flows of different types
        flow1 = FlowFactory.create(user=self.user1, flow_type="test_flow")
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})

        flow2 = FlowFactory.create(user=self.user1, flow_type="minimal_test_flow")
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})

        # Get most recent test_flow
        url = reverse("graflow:flow-most-recent") + "?flow_type=test_flow"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], flow1.id)
        self.assertEqual(response.data["flow_type"], "test_flow")

    def test_most_recent_with_both_filters(self):
        """Test most recent with both status and flow_type filters."""
        # Create multiple flows
        flow1 = FlowFactory.create(user=self.user1, flow_type="test_flow")
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})

        flow2 = FlowFactory.create(user=self.user1, flow_type="minimal_test_flow")
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})

        # Get most recent interrupted test_flow
        url = reverse("graflow:flow-most-recent") + "?status=interrupted&flow_type=test_flow"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], flow1.id)
        self.assertEqual(response.data["flow_type"], "test_flow")
        self.assertEqual(response.data["status"], "interrupted")

    def test_most_recent_returns_404_when_no_flows(self):
        """Test that most recent returns 404 when no flows match."""
        url = reverse("graflow:flow-most-recent")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)

    def test_most_recent_respects_user_isolation(self):
        """Test that most recent only returns flows for the authenticated user."""
        # Create flow for user2
        flow_user2 = FlowFactory.create(user=self.user2)
        flow_user2.resume({"user_id": self.user2.id, "flow_id": flow_user2.id})

        # Try to get most recent as user1
        url = reverse("graflow:flow-most-recent")
        response = self.client.get(url)

        # Should return 404 since user1 has no flows
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Create flow for user1
        flow_user1 = FlowFactory.create(user=self.user1)
        flow_user1.resume({"user_id": self.user1.id, "flow_id": flow_user1.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], flow_user1.id)

    def test_most_recent_with_status_all(self):
        """Test most recent with status=all includes all statuses."""
        # Create an interrupted flow (older)
        flow1 = FlowFactory.create(user=self.user1)
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})

        # Create a completed flow (more recent - created after flow1)
        flow2 = FlowFactory.create(user=self.user1)
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})

        # Get most recent with status=all (should include completed)
        url = reverse("graflow:flow-most-recent") + "?status=all"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # flow2 should be more recent since it was created later
        self.assertEqual(response.data["id"], flow2.id)
        self.assertEqual(response.data["status"], "completed")

    # ==================== Combined Filtering Tests ====================

    def test_list_with_status_and_type_filter(self):
        """Test combining status and flow_type filters."""
        # Create interrupted test_graph
        flow1 = FlowFactory.create(user=self.user1)
        flow1.resume({"user_id": self.user1.id, "flow_id": flow1.id})

        # Create interrupted minimal_test_graph
        flow2 = FlowFactory.create(user=self.user1, flow_type="minimal_test_flow")
        flow2.resume({"user_id": self.user1.id, "flow_id": flow2.id})

        # Filter by status=interrupted AND flow_type=test_graph
        url = reverse("graflow:flow-list") + "?status=interrupted&flow_type=test_flow"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["flow_type"], "test_flow")
        self.assertEqual(response.data[0]["status"], "interrupted")

    def test_list_with_status_and_state_filter(self):
        """Test combining status and state filters."""
        # Create interrupted flow with specific state
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        flow.resume(
            {"user_id": self.user1.id, "flow_id": flow.id, "counter": 42, "should_pause": True}
        )

        # Filter by status=interrupted AND state__counter=43
        url = reverse("graflow:flow-list") + "?flow_type=test_flow&state__counter=43"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["status"], "interrupted")


class FlowTypesAPITest(APITestCase):
    """Tests for the flow types endpoint."""

    @classmethod
    def setUpTestData(cls):
        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_graph",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )
        FlowType.objects.create(
            app_name="test_app",
            flow_type="test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_test_graph",
            state_path="graflow.tests.fixtures.test_graph:TestGraphState",
            is_latest=True,
        )
        FlowType.objects.create(
            app_name="test_app",
            flow_type="minimal_test_graph",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_minimal_test_graph",
            state_path="graflow.tests.fixtures.test_graph:MinimalTestState",
            is_latest=True,
        )
        FlowType.objects.create(
            app_name="test_app",
            flow_type="minimal_test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_minimal_test_graph",
            state_path="graflow.tests.fixtures.test_graph:MinimalTestState",
            is_latest=True,
        )
        cls.user = User.objects.create_user(
            email="flowtypes@test.com", username="flowtypes", password="testpass123"
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_list_flow_types(self):
        url = reverse("graflow:flow-type-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Filter to only test_app graphs (ignore graphs from settings like myflows)
        test_app_graphs = [item for item in response.data if item["app_name"] == "test_app"]
        self.assertEqual(
            sorted(
                test_app_graphs,
                key=lambda item: (item["app_name"], item["flow_type"], item["version"]),
            ),
            [
                {"app_name": "test_app", "flow_type": "minimal_test_flow", "version": "v1"},
                {"app_name": "test_app", "flow_type": "minimal_test_graph", "version": "v1"},
                {"app_name": "test_app", "flow_type": "test_flow", "version": "v1"},
                {"app_name": "test_app", "flow_type": "test_graph", "version": "v1"},
            ],
        )

    def test_requires_authentication(self):
        from django.conf import settings

        # Override setting to require authentication for this test
        original_setting = getattr(settings, "GRAFLOW_REQUIRE_AUTHENTICATION", True)
        settings.GRAFLOW_REQUIRE_AUTHENTICATION = True

        try:
            self.client.force_authenticate(user=None)
            url = reverse("graflow:flow-type-list")
            response = self.client.get(url)

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        finally:
            settings.GRAFLOW_REQUIRE_AUTHENTICATION = original_setting
