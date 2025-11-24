"""
Interactive demo graph that showcases Graflow's human-in-the-loop helpers.

This graph demonstrates three Graflow-specific features:
- FlowStateGraph for better logging/config injection
- add_data_receiver_node to pause and collect user input
- add_send_data_node to push intermediate results to the client
"""

from langgraph.graph import END, START
from pydantic import Field

from graflow.graphs.base import BaseGraphState
from graflow.graphs.flow_state_graph import FlowStateGraph


class InteractiveDemoState(BaseGraphState):
    """State for the interactive demo flow."""

    topic: str | None = Field(default=None, description="Brainstorming topic provided by user")
    ideas: list[str] = Field(default_factory=list, description="Latest brainstorming ideas")
    feedback: str | None = Field(default=None, description="User feedback to refine the plan")
    conversation: list[str] = Field(default_factory=list, description="Conversation transcript")
    iteration: int = Field(default=0, description="Number of idea batches generated")
    summary: str | None = Field(default=None, description="Final summary shared with the user")


def initialize_conversation(state: InteractiveDemoState) -> dict:
    """Seed the conversation with a friendly greeting."""
    if state.conversation:
        return {}
    greeting = (
        "Hi! I'm your interactive co-creator. Tell me what you're working on "
        "and we'll design a plan together."
    )
    return {"conversation": [greeting]}


def brainstorm_ideas(state: InteractiveDemoState) -> dict:
    """Generate a small batch of ideas for the provided topic."""
    if not state.topic:
        return {}

    iteration = state.iteration + 1
    base_templates = [
        f"Define a clear outcome for {state.topic}.",
        f"Interview a power user impacted by {state.topic}.",
        f"Prototype a low-fidelity experiment related to {state.topic}.",
    ]
    ideas = [f"[Round {iteration}] {template}" for template in base_templates]

    conversation = state.conversation + [
        f"I drafted {len(ideas)} ideas for '{state.topic}'. Let me know what resonates."
    ]
    return {"ideas": ideas, "conversation": conversation, "iteration": iteration}


def prompt_for_feedback(state: InteractiveDemoState) -> dict:
    """Ask the user to react to the suggestions."""
    prompt = (
        "Share what you like, dislike, or want to double-click on. "
        "I can adjust the plan based on your feedback."
    )
    return {"conversation": state.conversation + [prompt]}


def apply_feedback(state: InteractiveDemoState) -> dict:
    """Produce a final summary that incorporates user feedback."""
    acknowledgement = (
        f"Thanks for the feedback: '{state.feedback}'."
        if state.feedback
        else "Thanks for the review."
    )
    summary_lines = [
        acknowledgement,
        f"Focus topic: {state.topic or 'unspecified'}",
        f"Highlighted idea: {state.ideas[0] if state.ideas else 'N/A'}",
        "Next step: schedule a follow-up session after trying the idea.",
    ]

    conversation = state.conversation + [
        "Great! I've incorporated your feedback into the plan. "
        "Restart the flow if you'd like another iteration."
    ]
    return {"summary": "\n".join(summary_lines), "conversation": conversation}


def build_interactive_demo_graph():
    """
    Build an interactive demo flow that demonstrates Graflow-specific helpers.

    Flow:
    START
        -> initialize_conversation (seed greeting)
        -> request_topic (interrupt, requires topic)
        -> brainstorm_ideas (generate ideas with FlowStateGraph node)
        -> share_ideas (interrupt, send ideas to UI)
        -> prompt_for_feedback (ask for feedback)
        -> collect_feedback (interrupt, requires feedback)
        -> apply_feedback (final summary)
        -> END
    """

    graph = FlowStateGraph(InteractiveDemoState, "interactive_demo")

    graph.add_node(initialize_conversation, node_name="initialize_conversation")
    graph.add_node(brainstorm_ideas, node_name="brainstorm_ideas")
    graph.add_node(prompt_for_feedback, node_name="prompt_for_feedback")
    graph.add_node(apply_feedback, node_name="apply_feedback")

    graph.add_data_receiver_node(
        required_fields=["topic"],
        updated_fields=["conversation"],
        node_name="request_topic",
    )

    graph.add_send_data_node(
        updated_fields=["ideas", "conversation"],
        node_name="share_ideas",
    )

    graph.add_data_receiver_node(
        required_fields=["feedback"],
        updated_fields=["conversation", "ideas"],
        node_name="collect_feedback",
    )

    graph.add_edge(START, "initialize_conversation")
    graph.add_edge("initialize_conversation", "request_topic")
    graph.add_edge("request_topic", "brainstorm_ideas")
    graph.add_edge("brainstorm_ideas", "share_ideas")
    graph.add_edge("share_ideas", "prompt_for_feedback")
    graph.add_edge("prompt_for_feedback", "collect_feedback")
    graph.add_edge("collect_feedback", "apply_feedback")
    graph.add_edge("apply_feedback", END)

    return graph
