"""Common schemas used across the API."""

from enum import Enum

from pydantic import BaseModel, Field


class State(str, Enum):
    """
    Workflow execution state enum.

    State can take any of the following values:
    - UNKNOWN: The state of the task is unknown
    - QUEUED: The task is queued
    - INITIALIZING: The task has been assigned to a worker
    - RUNNING: The task is running
    - PAUSED: The task is paused
    - COMPLETE: The task has completed successfully
    - EXECUTOR_ERROR: The task encountered an error in an Executor
    - SYSTEM_ERROR: The task was stopped due to a system error
    - CANCELED: The task was canceled by the user
    - CANCELING: The task is in the process of being canceled
    - PREEMPTED: The task was preempted by the system
    """

    UNKNOWN = "UNKNOWN"
    QUEUED = "QUEUED"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETE = "COMPLETE"
    EXECUTOR_ERROR = "EXECUTOR_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    CANCELED = "CANCELED"
    CANCELING = "CANCELING"
    PREEMPTED = "PREEMPTED"


#: States a run does not leave. Anything polling a run needs this to know when to
#: stop, and getting it wrong means either an infinite wait or a premature one --
#: so it lives beside the enum rather than being redefined by each caller.
#:
#: CANCELING is deliberately absent: a cancellation in progress still becomes
#: CANCELED. UNKNOWN is absent too, because it is what the service reports when it
#: cannot currently determine the state, not a resting place.
TERMINAL_STATES = frozenset(
    {
        State.COMPLETE,
        State.EXECUTOR_ERROR,
        State.SYSTEM_ERROR,
        State.CANCELED,
        State.PREEMPTED,
    }
)


class ErrorResponse(BaseModel):
    """Error response schema."""

    msg: str = Field(..., description="A detailed error message")
    status_code: int = Field(
        ...,
        description="The integer representing the HTTP status code",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "msg": "Workflow run not found",
                "status_code": 404,
            }
        }
    }
