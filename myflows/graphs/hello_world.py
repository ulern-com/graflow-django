from langgraph.graph import StateGraph, MessagesState, START, END


HelloWorldState = MessagesState


def mock_llm(state: HelloWorldState):
    return {"messages": [{"role": "ai", "content": "hello world"}]}


def build_hello_world_graph():
    graph = StateGraph(HelloWorldState)
    graph.add_node(mock_llm)
    graph.add_edge(START, "mock_llm")
    graph.add_edge("mock_llm", END)
    return graph