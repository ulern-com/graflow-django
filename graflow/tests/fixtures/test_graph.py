"""
Test graph for comprehensive API testing.

This graph includes:
- Branching (conditional edges)
- Loops (dynamic goto with Command)
- Interrupts (pause points)
- Nested state for query testing
"""

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import Field

from graflow.graphs.base import BaseGraphState

# Shared in-memory checkpointer for all test graph instances
# This ensures state persists across graph invocations within the same test session
_test_checkpointer = MemorySaver()


class TestGraphState(BaseGraphState):  # noqa: N801
    """State for test graph with various features."""

    __test__ = False  # Tell pytest not to collect this as a test class

    counter: int = Field(default=0, description="Counter for loops")
    branch_choice: str = Field(default="left", description="Branch direction: left or right")
    max_iterations: int = Field(default=3, description="Max loop iterations")
    nested_data: dict = Field(default_factory=dict, description="Nested data for query tests")
    should_pause: bool = Field(default=False, description="Whether to pause at checkpoint")
    messages: list[str] = Field(default_factory=list, description="Message log for tracking flow")
    initial_input_received: bool = Field(
        default=False, description="Internal: tracks if user provided initial input"
    )


def node_initialize(state: TestGraphState) -> dict:
    """
    Initialize state with input data.
    Interrupts on first invocation (when only flow-level data is present) to get actual user input.
    This supports the double-resume pattern in the API.
    """
    # If this is the first invocation (no initial input received yet), interrupt
    if not state.initial_input_received:
        # Mark that we've now received the first call and interrupt for user input
        return interrupt({"initial_input_received": True})

    # Real initialization after user provides input (or on second resume)
    update: dict[str, Any] = {"messages": state.messages + ["initialized"]}
    if state.counter == 0 and not state.messages:  # Default value, not explicitly set
        update["counter"] = 0
    return update


def node_increment(state: TestGraphState) -> dict:
    """Increment counter."""
    new_counter = state.counter + 1
    return {"counter": new_counter, "messages": state.messages + [f"incremented to {new_counter}"]}


def node_branch_left(state: TestGraphState) -> dict:
    """Left branch processing."""
    return {
        "messages": state.messages + ["took left branch"],
        "nested_data": {"branch": "left", "value": state.counter},
    }


def node_branch_right(state: TestGraphState) -> dict:
    """Right branch processing."""
    return {
        "messages": state.messages + ["took right branch"],
        "nested_data": {"branch": "right", "value": state.counter * 2},
    }


def node_checkpoint(state: TestGraphState) -> dict:
    """Checkpoint that can pause for user interaction."""
    if state.should_pause:
        return interrupt({"messages": state.messages + ["paused at checkpoint"]})
    return {"messages": state.messages + ["passed checkpoint"]}


def node_loop_check(state: TestGraphState) -> Command:
    """Check if should continue looping (demonstrates dynamic goto)."""
    if state.counter < state.max_iterations:
        return Command(goto="increment")
    else:
        return Command(goto="finalize")


def node_finalize(state: TestGraphState) -> dict:
    """Finalize the graph."""
    return {"messages": state.messages + ["completed"]}


def decide_branch(state: TestGraphState) -> str:
    """Conditional edge to decide which branch to take."""
    return state.branch_choice if state.branch_choice in ["left", "right"] else "left"


def build_test_graph() -> StateGraph:
    """
    Build test graph with branching, loops, and interrupts.

    Flow:
    START -> initialize -> increment -> [branch_left OR branch_right] -> checkpoint -> loop_check
                                            ^                                              |
                                            |____________(if counter < max)________________|
                                                         (else) -> finalize -> END

    Note: Uses shared in-memory checkpointer for testing to avoid database connection issues.
    All test graph instances share the same checkpointer to persist state across invocations.
    """
    # Use shared in-memory checkpointer - no database connections needed
    graph = StateGraph(TestGraphState)

    # Add nodes
    graph.add_node("initialize", node_initialize)
    graph.add_node("increment", node_increment)
    graph.add_node("branch_left", node_branch_left)
    graph.add_node("branch_right", node_branch_right)
    graph.add_node("checkpoint", node_checkpoint)
    graph.add_node("loop_check", node_loop_check)
    graph.add_node("finalize", node_finalize)

    # Add edges
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "increment")
    graph.add_conditional_edges(
        "increment", decide_branch, {"left": "branch_left", "right": "branch_right"}
    )
    graph.add_edge("branch_left", "checkpoint")
    graph.add_edge("branch_right", "checkpoint")
    graph.add_edge("checkpoint", "loop_check")
    # loop_check uses Command for dynamic goto (either back to increment or to finalize)
    graph.add_edge("finalize", END)

    return graph


# ==================== Minimal Test Graph ====================


class MinimalTestState(BaseGraphState):  # noqa: N801
    __test__ = False  # Tell pytest not to collect this as a test class
    """Minimal state for simple testing - just tracks processing."""

    processing_stage: str = Field(default="started", description="Processing stage")
    result: str = Field(default="", description="Result value")


def minimal_node_process(state: MinimalTestState) -> dict:
    """Simple processing node."""
    return {"processing_stage": "processed", "result": "success"}


def build_minimal_test_graph() -> StateGraph:
    """
    Build minimal test graph with just one node for testing purposes.

    Flow: START -> process -> END

    This is used for testing features like flow type filtering without
    the complexity of the full test_graph.
    """
    graph = StateGraph(MinimalTestState)

    # Single processing node
    graph.add_node("process", minimal_node_process)

    # Simple linear flow
    graph.add_edge(START, "process")
    graph.add_edge("process", END)

    return graph
