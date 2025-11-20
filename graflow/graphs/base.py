from functools import wraps

from pydantic import BaseModel, Field


class BaseGraphState(BaseModel):
    """
    Base graph state for all graphs.
    """

    user_id: int | None = Field(default=None, description="The user ID")
    flow_id: int | None = Field(default=None, description="The flow ID")


def data_receiver(func=None, updated_fields=None):
    """
    Decorator to automatically receive required data from the user based on function parameters.
    The function should accept the required fields as parameters, and the decorator
    will automatically interrupt for them and return them as a dictionary.

    If the function returns None or an empty dict, the decorator will automatically
    return a dictionary with all the required fields.

    Args:
        func: The function to decorate (automatically passed when used without arguments)
        updated_fields: Fields to send to the frontend along with the interrupt.
                       Can be:
                       - dict: Explicit key-value pairs to send {"key": "value"}
                       - list: Field names to extract from state ["field1", "field2"]

    Usage:
        # Without updated_fields
        @data_receiver
        def get_inputs(state: MyState, user_input: str) -> Dict[str, Any]:
            return {}  # Will automatically return the required fields

        # With updated_fields as dict (explicit values)
        @data_receiver(updated_fields={"suggested_options": ["Option A", "Option B"]})
        def select_option(state: MyState, selected_option: str) -> Dict[str, Any]:
            return {}  # Will send suggested_options to FE and request selected_option

        # With updated_fields as list (extract from state)
        @data_receiver(updated_fields=["current_data"])
        def process_data(state: MyState, processed_result: str) -> Dict[str, Any]:
            return {}  # Will send current_data from state to FE
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(state):
            import inspect

            from langgraph.types import interrupt

            # Get function signature to extract parameter names
            sig = inspect.signature(fn)
            param_names = list(sig.parameters.keys())

            # Remove 'state' parameter as it's handled separately
            required_fields = [name for name in param_names if name != "state"]

            # Build interrupt data with updated fields and required data
            interrupt_data = {}

            # Handle updated_fields based on type
            if updated_fields:
                if isinstance(updated_fields, dict):
                    # Explicit key-value pairs
                    interrupt_data.update(updated_fields)
                elif isinstance(updated_fields, list):
                    # Extract field values from state
                    for field_name in updated_fields:
                        if hasattr(state, field_name):
                            interrupt_data[field_name] = getattr(state, field_name)

            interrupt_data["required_data"] = required_fields

            # Interrupt for required data
            state = interrupt(interrupt_data)

            # Extract the required fields from state
            kwargs = {field: getattr(state, field) for field in required_fields}

            # Call the original function with the extracted parameters
            result = fn(state, **kwargs)

            # If function returns None or empty dict, automatically return the required fields
            if result is None or result == {}:
                return kwargs

            return result

        return wrapper

    # Handle both @data_receiver and @data_receiver(updated_fields={...})
    if func is None:
        # Called with arguments: @data_receiver(updated_fields={...})
        return decorator
    else:
        # Called without arguments: @data_receiver
        return decorator(func)
