"""Unit tests for Flow model and FlowQuerySet."""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from graflow.models.flows import Flow
from graflow.models.registry import FlowType
from graflow.tests.factories import FlowFactory

User = get_user_model()


class FlowModelTest(TestCase):
    """Unit tests for Flow model methods."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests."""
        # Create FlowType entries for test graphs
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

    def test_is_terminal_for_pending(self):
        """Test is_terminal returns False for pending flows."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_PENDING)
        self.assertFalse(flow.is_terminal())

    def test_is_terminal_for_running(self):
        """Test is_terminal returns False for running flows."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_RUNNING)
        self.assertFalse(flow.is_terminal())

    def test_is_terminal_for_interrupted(self):
        """Test is_terminal returns False for interrupted flows."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_INTERRUPTED)
        self.assertFalse(flow.is_terminal())

    def test_is_terminal_for_completed(self):
        """Test is_terminal returns True for completed flows."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_COMPLETED)
        self.assertTrue(flow.is_terminal())

    def test_is_terminal_for_failed(self):
        """Test is_terminal returns True for failed flows."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_FAILED)
        self.assertTrue(flow.is_terminal())

    def test_is_terminal_for_cancelled(self):
        """Test is_terminal returns True for cancelled flows."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_CANCELLED)
        self.assertTrue(flow.is_terminal())

    def test_cancel_success(self):
        """Test cancel method successfully cancels a flow."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_PENDING)
        flow.cancel()
        flow.refresh_from_db()
        self.assertEqual(flow.status, Flow.STATUS_CANCELLED)

    def test_cancel_on_completed_raises_error(self):
        """Test cancel raises ValueError on terminal state."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_COMPLETED)
        with self.assertRaises(ValueError) as context:
            flow.cancel()
        self.assertIn("terminal state", str(context.exception))

    def test_cancel_on_failed_raises_error(self):
        """Test cancel raises ValueError on failed state."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_FAILED)
        with self.assertRaises(ValueError) as context:
            flow.cancel()
        self.assertIn("terminal state", str(context.exception))

    def test_cancel_on_cancelled_raises_error(self):
        """Test cancel raises ValueError on already cancelled state."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_CANCELLED)
        with self.assertRaises(ValueError) as context:
            flow.cancel()
        self.assertIn("terminal state", str(context.exception))

    def test_infer_current_state_name_prefers_next_metadata(self):
        """Current state name should be inferred from StateSnapshot.next when available."""
        flow = FlowFactory.create(user=self.user1)
        snapshot = SimpleNamespace(next=("request_topic",), tasks=())
        self.assertEqual(flow._infer_current_state_name_from_snapshot(snapshot), "request_topic")

    def test_infer_current_state_name_falls_back_to_task_name(self):
        """Current state name should use task.name when next metadata is missing."""
        flow = FlowFactory.create(user=self.user1)
        task = SimpleNamespace(
            name="collect_feedback",
            interrupts=("dummy",),
            path=("__pregel_pull", "collect_feedback"),
        )
        snapshot = SimpleNamespace(next=(), tasks=(task,))
        self.assertEqual(flow._infer_current_state_name_from_snapshot(snapshot), "collect_feedback")

    def test_resume_from_pending(self):
        """Test resume from pending state works."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_PENDING)
        result = flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        flow.refresh_from_db()
        # Flow should be interrupted or completed after resume
        self.assertIn(flow.status, [Flow.STATUS_INTERRUPTED, Flow.STATUS_COMPLETED])
        self.assertIsNotNone(result)

    def test_resume_from_interrupted(self):
        """Test resume from interrupted state works."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_INTERRUPTED)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        result = flow.resume({"user_id": self.user1.id, "flow_id": flow.id, "counter": 1})
        flow.refresh_from_db()
        # Flow should still be interrupted or completed after resume
        self.assertIn(flow.status, [Flow.STATUS_INTERRUPTED, Flow.STATUS_COMPLETED])
        self.assertIsNotNone(result)

    def test_resume_sets_status_to_running(self):
        """Test that resume sets status to running during execution."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_PENDING)
        # Note: We can't directly test this without mocking, but we can verify
        # the flow eventually gets a non-pending status
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        flow.refresh_from_db()
        self.assertNotEqual(flow.status, Flow.STATUS_PENDING)
        self.assertNotEqual(flow.status, Flow.STATUS_RUNNING)  # Should have finished

    def test_resume_rejects_terminal_state(self):
        """Resume should fail for terminal flows."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_COMPLETED)
        with self.assertRaises(ValueError) as context:
            flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        self.assertIn("terminal", str(context.exception))

    def test_resume_rejects_running_state(self):
        """Resume should fail for running flows."""
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_RUNNING)
        with self.assertRaises(ValueError) as context:
            flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        self.assertIn("running", str(context.exception))

    def test_str_representation_with_user(self):
        """Test string representation includes user info."""
        flow = FlowFactory.create(user=self.user1)
        str_repr = str(flow)
        self.assertIn("test_app", str_repr)
        self.assertIn("test_flow", str_repr)
        self.assertIn("user1", str_repr)

    def test_str_representation_without_user(self):
        """Test string representation for background flows."""
        flow = FlowFactory.create(user=None)
        str_repr = str(flow)
        self.assertIn("test_app", str_repr)
        self.assertIn("test_flow", str_repr)
        self.assertIn("background flow", str_repr)

    def test_state_excludes_current_state_name(self):
        """Flow.state should not include current_state_name metadata."""
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id})
        state = flow.state
        self.assertIsInstance(state, dict)
        self.assertNotIn("current_state_name", state)


class FlowQuerySetTest(TestCase):
    """Unit tests for FlowQuerySet methods."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests."""
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
            flow_type="minimal_test_flow",
            version="v1",
            builder_path="graflow.tests.fixtures.test_graph:build_minimal_test_graph",
            state_path="graflow.tests.fixtures.test_graph:MinimalTestState",
            is_latest=True,
        )

        cls.user1 = User.objects.create_user(
            email="user1@test.com", username="user1", password="testpass123"
        )
        cls.user2 = User.objects.create_user(
            email="user2@test.com", username="user2", password="testpass123"
        )

        # Create flows for testing
        FlowFactory.create(user=cls.user1, flow_type="test_flow", status=Flow.STATUS_PENDING)
        FlowFactory.create(user=cls.user1, flow_type="test_flow", status=Flow.STATUS_INTERRUPTED)
        FlowFactory.create(
            user=cls.user1, flow_type="minimal_test_flow", status=Flow.STATUS_COMPLETED
        )
        FlowFactory.create(user=cls.user2, flow_type="test_flow", status=Flow.STATUS_PENDING)

    def test_for_user_filter(self):
        """Test for_user filters by user."""
        flows = Flow.objects.for_user(self.user1)
        self.assertEqual(flows.count(), 3)
        for flow in flows:
            self.assertEqual(flow.user, self.user1)

    def test_for_app_filter(self):
        """Test for_app filters by app name."""
        flows = Flow.objects.for_app("test_app")
        self.assertEqual(flows.count(), 4)  # All flows are in test_app

    def test_of_type_filter(self):
        """Test of_type filters by flow type."""
        flows = Flow.objects.of_type("test_flow")
        self.assertEqual(flows.count(), 3)  # 2 for user1, 1 for user2

    def test_in_progress_filter(self):
        """Test in_progress filters for non-terminal flows."""
        flows = Flow.objects.in_progress()
        # Should include pending and interrupted, exclude completed
        self.assertEqual(flows.count(), 3)
        for flow in flows:
            self.assertIn(
                flow.status, [Flow.STATUS_PENDING, Flow.STATUS_RUNNING, Flow.STATUS_INTERRUPTED]
            )

    def test_by_recency_ordering(self):
        """Test by_recency orders by last_resumed_at descending."""
        flows = list(Flow.objects.by_recency())
        # Verify they're ordered by last_resumed_at descending
        if len(flows) > 1:
            for i in range(len(flows) - 1):
                self.assertGreaterEqual(flows[i].last_resumed_at, flows[i + 1].last_resumed_at)

    def test_filter_by_state_simple_field(self):
        """Test filter_by_state with simple field."""
        # Create a flow with specific state by resuming it
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id, "counter": 42})

        # Graph increments counter once before completing
        all_flows = Flow.objects.filter(user=self.user1)
        filtered = all_flows.filter_by_state(counter=43)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].id, flow.id)

    def test_filter_by_state_nested_field(self):
        """Test filter_by_state with nested field."""
        # Create flow with nested state using nested_data field from TestGraphState
        flow = FlowFactory.create(user=self.user1)
        state = {
            "user_id": self.user1.id,
            "flow_id": flow.id,
            "nested_data": {"nested": {"value": "test"}},
        }
        flow.resume(state)

        # Graph overwrites nested_data based on branch choice (default left) and counter
        all_flows = Flow.objects.filter(user=self.user1)
        filtered = all_flows.filter_by_state(nested_data__branch="left", nested_data__value=3)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].id, flow.id)

    def test_filter_by_state_multiple_filters(self):
        """Test filter_by_state with multiple filters (AND logic)."""
        # Create flows with different states
        flow1 = FlowFactory.create(user=self.user1)
        flow1.resume(
            {
                "user_id": self.user1.id,
                "flow_id": flow1.id,
                "counter": 5,
                "branch_choice": "left",
            }
        )

        flow2 = FlowFactory.create(user=self.user1)
        flow2.resume(
            {
                "user_id": self.user1.id,
                "flow_id": flow2.id,
                "counter": 5,
                "branch_choice": "right",
            }
        )

        # Graph increments counter once before completing
        all_flows = Flow.objects.filter(user=self.user1)
        filtered = all_flows.filter_by_state(counter=6, branch_choice="left")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].id, flow1.id)

    def test_filter_by_state_no_match(self):
        """Test filter_by_state returns empty list when no matches."""
        all_flows = Flow.objects.filter(user=self.user1)
        filtered = all_flows.filter_by_state(counter=999999)
        self.assertEqual(len(filtered), 0)

    def test_filter_by_state_handles_none_state(self):
        """Test filter_by_state handles flows with None state gracefully."""
        # Create a flow that hasn't been resumed (no state yet)
        flow = FlowFactory.create(user=self.user1, status=Flow.STATUS_PENDING)
        all_flows = Flow.objects.filter(user=self.user1, id=flow.id)
        filtered = all_flows.filter_by_state(counter=42)
        # Should return empty list since state is None
        self.assertEqual(len(filtered), 0)

    def test_filter_by_state_type_coercion(self):
        """Test filter_by_state handles type coercion."""
        flow = FlowFactory.create(user=self.user1)
        flow.resume({"user_id": self.user1.id, "flow_id": flow.id, "counter": 42})

        # Graph increments counter once before completing
        all_flows = Flow.objects.filter(user=self.user1)
        filtered = all_flows.filter_by_state(counter="43")
        self.assertEqual(len(filtered), 1)

    def test_filter_by_state_empty_filters(self):
        """Test filter_by_state returns all flows when no filters provided."""
        all_flows = list(Flow.objects.filter(user=self.user1))
        filtered = Flow.objects.filter(user=self.user1).filter_by_state()
        self.assertEqual(len(filtered), len(all_flows))

    def test_chaining_queryset_methods(self):
        """Test that queryset methods can be chained."""
        flows = Flow.objects.for_user(self.user1).of_type("test_flow").in_progress().by_recency()
        # Should get user1's test_flow flows that are in progress, ordered by recency
        self.assertGreater(flows.count(), 0)
        for flow in flows:
            self.assertEqual(flow.user, self.user1)
            self.assertEqual(flow.flow_type, "test_flow")
            self.assertIn(
                flow.status, [Flow.STATUS_PENDING, Flow.STATUS_RUNNING, Flow.STATUS_INTERRUPTED]
            )
