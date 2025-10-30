"""Task-related schemas."""

from pydantic import BaseModel, Field

from src.wes_service.schemas.run import Log


class TaskLog(Log):
    """Runtime information for a given task."""

    id: str = Field(..., description="Unique identifier for the task")
    tes_uri: str | None = Field(
        None,
        description="Optional URL to TES task definition",
    )


class TaskListResponse(BaseModel):
    """Response for listing task logs."""

    task_logs: list[TaskLog] = Field(
        default_factory=list,
        description="List of task logs for the workflow run",
    )
    next_page_token: str | None = Field(
        None,
        description="Token for next page (empty if no more items)",
    )
