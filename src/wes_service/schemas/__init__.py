"""Pydantic schemas for API validation."""

from src.wes_service.schemas.callback import CallbackResponse, ExecutorStateChangeCallback
from src.wes_service.schemas.common import TERMINAL_STATES, ErrorResponse, State
from src.wes_service.schemas.run import (
    Log,
    RunId,
    RunListResponse,
    RunLog,
    RunProgress,
    RunRequest,
    RunStatus,
    RunSummary,
)
from src.wes_service.schemas.service_info import (
    DefaultWorkflowEngineParameter,
    ServiceInfo,
    WorkflowEngineVersion,
    WorkflowTypeVersion,
)
from src.wes_service.schemas.task import TaskListResponse, TaskLog

__all__ = [
    # Common
    "State",
    "TERMINAL_STATES",
    "ErrorResponse",
    # Service Info
    "ServiceInfo",
    "WorkflowTypeVersion",
    "WorkflowEngineVersion",
    "DefaultWorkflowEngineParameter",
    # Runs
    "RunId",
    "RunStatus",
    "RunSummary",
    "RunRequest",
    "RunLog",
    "RunListResponse",
    "RunProgress",
    "Log",
    # Tasks
    "TaskLog",
    "TaskListResponse",
    # Callbacks
    "ExecutorStateChangeCallback",
    "CallbackResponse",
]
