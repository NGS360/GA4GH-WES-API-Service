"""Common schemas used across the API."""

from enum import Enum

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
