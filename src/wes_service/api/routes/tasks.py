"""Task endpoints."""

from fastapi import APIRouter

from src.wes_service.api.deps import CurrentUser, DatabaseSession
from src.wes_service.schemas.task import TaskListResponse, TaskLog
from src.wes_service.services.task_service import TaskService

router = APIRouter()


@router.get(
    "/runs/{run_id}/tasks",
    response_model=TaskListResponse,
    tags=["Workflow Runs"],
    summary="ListTasks",
    description="List tasks for a workflow run with pagination",
)
async def list_tasks(
    run_id: str,
    db: DatabaseSession,
    user: CurrentUser,
    page_size: int | None = None,
    page_token: str | None = None,
) -> TaskListResponse:
    """
    List tasks that were executed as part of a workflow run.

    Task ordering is the same as what would be returned in a RunLog.
    Supports pagination for large task lists.
    """
    service = TaskService(db)
    return await service.list_tasks(run_id, page_size, page_token, user)


@router.get(
    "/runs/{run_id}/tasks/{task_id}",
    response_model=TaskLog,
    tags=["Workflow Runs"],
    summary="GetTask",
    description="Get information about a specific task",
)
async def get_task(
    run_id: str,
    task_id: str,
    db: DatabaseSession,
    user: CurrentUser,
) -> TaskLog:
    """
    Get detailed information about a specific task.

    Returns task execution details including command, timing,
    exit code, and log URLs.
    """
    service = TaskService(db)
    return await service.get_task(run_id, task_id, user)