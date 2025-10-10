"""Service layer for task operations."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.wes_service.db.models import TaskLog as TaskLogModel
from src.wes_service.db.models import WorkflowRun
from src.wes_service.schemas.task import TaskListResponse, TaskLog


class TaskService:
    """Service for managing workflow tasks."""

    def __init__(self, db: AsyncSession):
        """Initialize task service."""
        self.db = db

    async def list_tasks(
        self,
        run_id: str,
        page_size: int | None,
        page_token: str | None,
        user_id: str | None,
    ) -> TaskListResponse:
        """
        List tasks for a workflow run with pagination.

        Args:
            run_id: Run ID
            page_size: Number of tasks per page
            page_token: Token for next page
            user_id: User ID for authorization

        Returns:
            TaskListResponse with tasks and next page token
        """
        # Verify run exists and user has access
        await self._verify_run_access(run_id, user_id)

        # Default page size
        if page_size is None:
            page_size = 10
        page_size = min(page_size, 100)  # Max 100 per page

        # Parse page token (offset)
        offset = int(page_token) if page_token else 0

        # Build query
        query = (
            select(TaskLogModel)
            .where(TaskLogModel.run_id == run_id)
            .order_by(TaskLogModel.created_at.asc())
            .offset(offset)
            .limit(page_size + 1)
        )

        # Execute query
        result = await self.db.execute(query)
        tasks = result.scalars().all()

        # Check if there are more results
        has_more = len(tasks) > page_size
        if has_more:
            tasks = tasks[:page_size]

        # Convert to schemas
        task_logs = [self._task_to_schema(task) for task in tasks]

        # Generate next page token
        next_token = str(offset + page_size) if has_more else ""

        return TaskListResponse(task_logs=task_logs, next_page_token=next_token)

    async def get_task(
        self,
        run_id: str,
        task_id: str,
        user_id: str | None,
    ) -> TaskLog:
        """
        Get a specific task.

        Args:
            run_id: Run ID
            task_id: Task ID
            user_id: User ID for authorization

        Returns:
            TaskLog
        """
        # Verify run exists and user has access
        await self._verify_run_access(run_id, user_id)

        # Get task
        query = select(TaskLogModel).where(
            TaskLogModel.run_id == run_id,
            TaskLogModel.id == task_id,
        )

        result = await self.db.execute(query)
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task not found: {task_id}",
            )

        return self._task_to_schema(task)

    async def _verify_run_access(
        self,
        run_id: str,
        user_id: str | None,
    ) -> WorkflowRun:
        """
        Verify run exists and user has access.

        Args:
            run_id: Run ID
            user_id: User ID for authorization

        Returns:
            WorkflowRun

        Raises:
            HTTPException: If run not found or unauthorized
        """
        query = select(WorkflowRun).where(WorkflowRun.id == run_id)
        result = await self.db.execute(query)
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow run not found: {run_id}",
            )

        # Authorization check
        if user_id and run.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this workflow run",
            )

        return run

    def _task_to_schema(self, task: TaskLogModel) -> TaskLog:
        """Convert TaskLogModel to TaskLog schema."""
        return TaskLog(
            id=task.id,
            name=task.name,
            cmd=task.cmd,
            start_time=(
                task.start_time.isoformat() + "Z" if task.start_time else None
            ),
            end_time=(
                task.end_time.isoformat() + "Z" if task.end_time else None
            ),
            stdout=task.stdout_url,
            stderr=task.stderr_url,
            exit_code=task.exit_code,
            system_logs=task.system_logs,
            tes_uri=task.tes_uri,
        )