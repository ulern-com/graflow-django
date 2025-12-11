import logging

from django.test import TestCase
from langgraph.graph import START

from graflow.graphs.base import BaseGraphState
from graflow.graphs.flow_state_graph import FlowStateGraph
from graflow.logger import logging as lg

logger = logging.getLogger(lg.__name__)


class FakeState(BaseGraphState):
    pass


class LoggingTests(TestCase):
    """test suite for logging"""

    def setUp(self):
        self.flow = FlowStateGraph(FakeState, "test_flow")

    def test_node_logs_enter_exit(self):

        def greeting(state):
            return {"text": "hello"}

        self.flow.add_node(greeting, "greeting_node")
        self.flow.add_edge(START, "greeting_node")

        with self.assertLogs(logger, level="INFO") as log:
            self.flow.compile().invoke({})

        output = "\n".join(log.output)

        self.assertIn("[ENTER] greeting_node", output)
        self.assertIn("[EXIT] greeting_node", output)

    def test_node_logs_error(self):

        def useless_node(state):
            raise ValueError("something bad happened")

        self.flow.add_node(useless_node, "useless_node")
        self.flow.add_edge(START, "useless_node")

        with self.assertLogs(logger, level="ERROR") as log:
            with self.assertRaises(ValueError):  # <-- REQUIRED
                self.flow.compile().invoke({})

        output = "\n".join(log.output)

        self.assertIn("[ERROR] useless_node", output)
        self.assertIn("ValueError", output)
        self.assertIn("something bad happened", output)

    def test_llm_nodes(self):

        def generate_summary(text: str):
            return f"something {text}"

        class LLMState(BaseGraphState):
            text: str

        flow = FlowStateGraph(LLMState, "llm_flow")

        flow.add_llm_call_node(generate_summary, "text")
        flow.add_edge(START, "generate_summary")

        with self.assertLogs(logger, level="INFO") as log:
            flow.compile().invoke({"text": "hello"})

        output = "\n".join(log.output)

        self.assertIn("[ENTER] generate_summary", output)
        self.assertIn("[EXIT] generate_summary", output)

    def test_data_receiver_node(self):

        class TestState(BaseGraphState):
            name: str | None = None

        flow = FlowStateGraph(TestState, "test_flow")
        flow.add_data_receiver_node(required_fields=["name"])
        flow.add_edge(START, "waiting_for_name")

        with self.assertLogs(logger, level="INFO") as log:

            flow.compile().invoke({"name": None})

        output = "\n".join(log.output)
        self.assertIn("[ENTER] waiting_for_name", output)

    def test_send_data_node(self):
        class TestState(BaseGraphState):
            value: int = 42

        flow = FlowStateGraph(TestState, "test_flow")
        flow.add_send_data_node(updated_fields=["value"])
        flow.add_edge(START, "send_value")

        with self.assertLogs(logger, level="INFO") as log:
            flow.compile().invoke({"value": 42})

        output = "\n".join(log.output)
        self.assertIn("[ENTER] send_value", output)
