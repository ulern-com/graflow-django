from pydantic import BaseModel, Field


class BaseGraphState(BaseModel):
    """
    Base graph state for all graphs.
    """

    user_id: int | None = Field(default=None, description="The user ID")
    flow_id: int | None = Field(default=None, description="The flow ID")
