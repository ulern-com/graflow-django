import inspect
import logging
from collections.abc import Callable
from typing import Any, NamedTuple, TypeVar

from django.conf import settings
from langgraph.graph import StateGraph
from langgraph.types import CachePolicy, interrupt

from graflow.graphs.base import BaseGraphState
from graflow.storage.cache import create_cache_key_from_fields

logger = logging.getLogger(__name__)


StateT = TypeVar("StateT", bound=BaseGraphState)


class FlowStateGraph(StateGraph[StateT, StateT, StateT]):
    """
    Custom StateGraph for Graflow that provides common patterns and utilities for building flows.
    """

    def __init__(
        self,
        state_schema: type[StateT],
        flow_name: str,
        config_schema: type[Any] | None = None,
        **kwargs,
    ):
        super().__init__(state_schema, config_schema, **kwargs)
        self.flow_name = flow_name

    def compile(self, cache=None, checkpointer=None, store=None):
        """Compile the graph with Graflow defaults."""
        return (
            super()
            .compile(checkpointer=checkpointer, cache=cache, store=store)
            .with_config({"run_name": self.flow_name})
        )

    def add_node(  # type: ignore[override]
        self, func: Callable[..., Any], node_name: str | None = None, **kwargs: Any
    ) -> "FlowStateGraph[StateT]":
        """
        Add a node with automatic logging.

        Args:
            node_name: Node name (optional), if not provided, the function name will be used.
            func: The function to build the node from.
            **kwargs: Additional node configuration

        Returns:
            The graph instance.
        """
        if node_name is None:
            node_name = func.__name__

        def wrapped_func(state: StateT):
            logger.info(f"ENTER: {node_name}")
            try:
                result = func(state)
                logger.info(f"EXIT: {node_name}")
                return result
            except Exception as e:
                logger.error(f"ERROR: {node_name} - {e}")
                raise

        super().add_node(node_name, wrapped_func, **kwargs)
        return self  # type: ignore[return-value]

    def add_llm_call_node(
        self, llm_func: Callable[..., Any], result_field: str | None = None, **node_kwargs
    ) -> NamedTuple:
        """
        Add an LLM call node with automatic caching using the function parameters as cache key.

        Args:
            llm_func: LLM function that takes specific parameters (not full state)
            result_field: Field name to store the LLM result in the state "
            "(optional, inferred from the function name if not provided)
            **node_kwargs: Additional node configuration

        Returns:
            The graph instance for method chaining.
        """
        node_name = llm_func.__name__

        if result_field is None:
            result_field = node_name[9:]  # Remove the "generate_" prefix

        sig = inspect.signature(llm_func)
        func_param_names = list(sig.parameters.keys())

        def llm_wrapper(state: StateT) -> StateT:
            # Extract arguments from state based on llm_func signature
            func_args = []
            for param_name in func_param_names:
                if hasattr(state, param_name):
                    func_args.append(getattr(state, param_name))
                else:
                    raise ValueError(
                        f"Field '{param_name}' not found in state for LLM function '{node_name}'"
                    )

            llm_result = llm_func(*func_args)
            return {result_field: llm_result}  # type: ignore[return-value]

        # Add cache policy for LLM calls using function parameters as cache key
        # Use getattr with default to safely access settings
        cache_ttl = getattr(settings, "GRAFLOW_NODE_CACHE_TTL", 3600)

        def create_cache_key_func(state: StateT):
            # Create a dict with the parameters for cache key
            cache_params = {}
            for param_name in func_param_names:
                if hasattr(state, param_name):
                    cache_params[param_name] = getattr(state, param_name)

            return create_cache_key_from_fields(node_name, state, func_param_names)

        cache_policy = CachePolicy(ttl=cache_ttl, key_func=create_cache_key_func)
        node_kwargs["cache_policy"] = cache_policy

        self.add_node(func=llm_wrapper, node_name=node_name, **node_kwargs)
        return self  # type: ignore[return-value]

    def add_data_receiver_node(
        self,
        required_fields: list[str],
        updated_fields: list[str] | None = None,
        node_name: str | None = None,
        **kwargs,
    ) -> "FlowStateGraph":
        """
        Add a node that interrupts for required data fields.

        Args:
            required_fields: List of field names to request from the user
            updated_fields: List of field names to send to the frontend "
            "along with the interrupt (optional)
            node_name: Node name (optional), if not provided, a default name will be generated
            **kwargs: Additional node configuration

        Returns:
            The graph instance for method chaining.
        """
        if node_name is None:
            node_name = f"waiting_for_{'_and_'.join(required_fields)}"

        def data_receiver_func(state: StateT):
            if updated_fields:
                state_update = {field: getattr(state, field) for field in updated_fields}
                received_data = interrupt({**state_update, "required_data": required_fields})
            else:
                received_data = interrupt({"required_data": required_fields})
            logger.info(f"RECEIVED DATA in {node_name}")
            return received_data

        self.add_node(func=data_receiver_func, node_name=node_name, **kwargs)
        return self

    def add_send_data_node(
        self,
        updated_fields: list[str],
        node_name: str | None = None,
        **kwargs,
    ) -> "FlowStateGraph":
        """
        Add a node that sends data to the client.

        Args:
            updated_fields: List of field names to send to the client
            node_name: Node name (optional), if not provided, a default name will be generated
            **kwargs: Additional node configuration

        Returns:
            The graph instance for method chaining.
        """
        if node_name is None:
            node_name = f"send_{'_and_'.join(updated_fields)}"

        def send_data_func(state: StateT):
            interrupt({field: getattr(state, field) for field in updated_fields})
            logger.info(f"SENT DATA in {node_name}")
            return {}

        self.add_node(func=send_data_func, node_name=node_name, **kwargs)
        return self
