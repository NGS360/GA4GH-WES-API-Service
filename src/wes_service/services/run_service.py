"""Service layer for workflow run operations."""

import json
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.wes_service.config import get_settings
from src.wes_service.core.storage import StorageBackend
from src.wes_service.db.models import (
    WorkflowAttachment,
    WorkflowRun,
    WorkflowState,
)
from src.wes_service.schemas.common import State
from src.wes_service.schemas.run import (
    Log,
    RunListResponse,
    RunLog,
    RunRequest,
    RunStatus,
    RunSummary,
)


class RunService:
    """Service for managing workflow runs."""

    def __init__(self, db: AsyncSession, storage: StorageBackend):
        """Initialize run service."""
        self.db = db
        self.storage = storage
        self.settings = get_settings()

    async def create_run(
        self,
        workflow_params: str | None,
        workflow_type: str,
        workflow_type_version: str,
        workflow_url: str,
        workflow_attachments: list[UploadFile] | None,
        tags: str | None,
        workflow_engine: str | None,
        workflow_engine_version: str | None,
        workflow_engine_parameters: str | None,
        user_id: str,
    ) -> str:
        """
        Create a new workflow run.

        Args:
            workflow_params: JSON string of workflow parameters
            workflow_type: Workflow type (CWL, WDL)
            workflow_type_version: Workflow type version
            workflow_url: URL to workflow definition
            workflow_attachments: List of uploaded files
            tags: JSON string of tags
            workflow_engine: Workflow engine name
            workflow_engine_version: Workflow engine version
            workflow_engine_parameters: JSON string of engine parameters
            user_id: User creating the run

        Returns:
            Run ID
        """
        # Parse JSON strings
        params = json.loads(workflow_params) if workflow_params else {}
        tags_dict = json.loads(tags) if tags else {}
        engine_params = (
            json.loads(workflow_engine_parameters)
            if workflow_engine_parameters
            else {}
        )

        # Add "Name" tag if not already present, extracting it from workflow_engine_parameters
        if "Name" not in tags_dict and engine_params and "name" in engine_params:
            tags_dict["Name"] = engine_params["name"]

        # Validate workflow type
        supported_types = list(
            self.settings.get_workflow_type_versions().keys()
        )
        if workflow_type.upper() not in supported_types:
            raise ValueError(
                f"Unsupported workflow type: {workflow_type}. "
                f"Supported types: {supported_types}"
            )

        # Create run record
        run_id = str(uuid4())
        run = WorkflowRun(
            id=run_id,
            state=WorkflowState.QUEUED,
            workflow_type=workflow_type.upper(),
            workflow_type_version=workflow_type_version,
            workflow_url=workflow_url,
            workflow_params=params,
            workflow_engine=workflow_engine,
            workflow_engine_version=workflow_engine_version,
            workflow_engine_parameters=engine_params,
            tags=tags_dict,
            user_id=user_id,
        )

        self.db.add(run)

        # Handle attachments
        if workflow_attachments:
            for attachment in workflow_attachments:
                # Generate storage path
                storage_path = f"runs/{run_id}/attachments/{attachment.filename}"

                # Upload file
                await self.storage.upload_file(attachment, storage_path)

                # Create attachment record
                attachment_record = WorkflowAttachment(
                    run_id=run_id,
                    filename=attachment.filename or "unknown",
                    storage_path=storage_path,
                    content_type=attachment.content_type,
                    size_bytes=attachment.size or 0,
                )
                self.db.add(attachment_record)

        await self.db.commit()
        return run_id

    async def list_runs(
        self,
        page_size: int | None,
        page_token: str | None,
        user_id: str | None,
        tag_filters: dict[str, str] | None = None,
    ) -> RunListResponse:
        """
        List workflow runs with pagination and tag filtering.

        Args:
            page_size: Number of runs per page
            page_token: Token for next page
            user_id: Filter by user (None for all runs)
            tag_filters: Dictionary of tag key-value pairs to filter by

        Returns:
            RunListResponse with runs and next page token
        """
        # Default page size
        if page_size is None:
            page_size = 10
        page_size = min(page_size, 100)  # Max 100 per page

        # Parse page token (offset)
        offset = int(page_token) if page_token else 0

        # Build query
        query = select(WorkflowRun).order_by(WorkflowRun.created_at.desc())

        # Filter by user if specified
        if user_id:
            query = query.where(WorkflowRun.user_id == user_id)

        # Filter by tags if specified
        if tag_filters and isinstance(tag_filters, dict):
            from sqlalchemy import text
            for tag_key, tag_value in tag_filters.items():
                # Use JSON containment operator to check if the tags JSON contains the key-value pair
                # This creates a condition like: tags @> {"project": "testproject"}
                json_condition = text(f"JSON_EXTRACT(tags, '$.{tag_key}') = '{tag_value}'")
                query = query.where(json_condition)

        # Apply pagination
        query = query.offset(offset).limit(page_size + 1)

        # Execute query
        result = await self.db.execute(query)
        runs = result.scalars().all()

        # Check if there are more results
        has_more = len(runs) > page_size
        if has_more:
            runs = runs[:page_size]

        # Convert to summaries
        summaries = [self._run_to_summary(run) for run in runs]

        # Generate next page token
        next_token = str(offset + page_size) if has_more else ""

        return RunListResponse(runs=summaries, next_page_token=next_token)

    async def get_run_status(self, run_id: str, user_id: str | None) -> RunStatus:
        """
        Get workflow run status.

        Args:
            run_id: Run ID
            user_id: User ID for authorization

        Returns:
            RunStatus
        """
        run = await self._get_run(run_id, user_id)
        return RunStatus(
            run_id=run.id,
            state=State(run.state.value),
        )

    async def get_run_log(self, run_id: str, user_id: str | None) -> RunLog:
        """
        Get detailed workflow run log.

        Args:
            run_id: Run ID
            user_id: User ID for authorization

        Returns:
            RunLog
        """
        run = await self._get_run(run_id, user_id, load_relationships=True)

        # Build run request
        request = RunRequest(
            workflow_params=run.workflow_params,
            workflow_type=run.workflow_type,
            workflow_type_version=run.workflow_type_version,
            workflow_url=run.workflow_url,
            tags=run.tags,
            workflow_engine=run.workflow_engine,
            workflow_engine_version=run.workflow_engine_version,
            workflow_engine_parameters=run.workflow_engine_parameters,
        )

        # Build run log
        run_log = None
        if run.start_time:
            run_log = Log(
                name=f"Workflow {run.workflow_type}",
                cmd=None,
                start_time=(
                    run.start_time.isoformat() + "Z" if run.start_time else None
                ),
                end_time=(
                    run.end_time.isoformat() + "Z" if run.end_time else None
                ),
                stdout=run.stdout_url,
                stderr=run.stderr_url,
                exit_code=run.exit_code,
                system_logs=run.system_logs,
            )

        # Build task logs URL
        task_logs_url = (
            f"{self.settings.api_prefix}/runs/{run_id}/tasks"
        )

        # Extract name from workflow_engine_parameters if available
        name = None
        if run.workflow_engine_parameters and "name" in run.workflow_engine_parameters:
            name = run.workflow_engine_parameters["name"]

        return RunLog(
            run_id=run.id,
            request=request,
            state=State(run.state.value),
            name=name,
            run_log=run_log,
            task_logs_url=task_logs_url,
            task_logs=None,  # Deprecated
            outputs=run.outputs,
        )

    async def cancel_run(self, run_id: str, user_id: str | None) -> str:
        """
        Cancel a workflow run.

        Args:
            run_id: Run ID
            user_id: User ID for authorization

        Returns:
            Run ID
        """
        run = await self._get_run(run_id, user_id)

        # Check if run can be canceled
        if run.state in [
            WorkflowState.COMPLETE,
            WorkflowState.EXECUTOR_ERROR,
            WorkflowState.SYSTEM_ERROR,
            WorkflowState.CANCELED,
        ]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel run in state {run.state.value}",
            )

        # Update state to CANCELING
        run.state = WorkflowState.CANCELING
        await self.db.commit()

        return run.id

    async def get_system_state_counts(self) -> dict[str, int]:
        """Get count of runs in each state."""
        query = select(
            WorkflowRun.state,
            func.count(WorkflowRun.id),
        ).group_by(WorkflowRun.state)

        result = await self.db.execute(query)
        counts = {state.value: count for state, count in result}

        # Ensure all states are represented
        for state in WorkflowState:
            if state.value not in counts:
                counts[state.value] = 0

        return counts

    async def _get_run(
        self,
        run_id: str,
        user_id: str | None,
        load_relationships: bool = False,
    ) -> WorkflowRun:
        """
        Get a workflow run by ID.

        Args:
            run_id: Run ID
            user_id: User ID for authorization
            load_relationships: Whether to load related objects

        Returns:
            WorkflowRun

        Raises:
            HTTPException: If run not found or unauthorized
        """
        query = select(WorkflowRun).where(WorkflowRun.id == run_id)

        if load_relationships:
            query = query.options(
                selectinload(WorkflowRun.task_logs),
                selectinload(WorkflowRun.attachments),
            )

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

    def _run_to_summary(self, run: WorkflowRun) -> RunSummary:
        """Convert WorkflowRun to RunSummary."""
        # Extract name from workflow_engine_parameters if available
        name = None
        if run.workflow_engine_parameters and "name" in run.workflow_engine_parameters:
            name = run.workflow_engine_parameters["name"]

        return RunSummary(
            run_id=run.id,
            state=State(run.state.value),
            start_time=(
                run.start_time.isoformat() + "Z" if run.start_time else None
            ),
            end_time=run.end_time.isoformat() + "Z" if run.end_time else None,
            tags=run.tags,
            name=name,
        )
