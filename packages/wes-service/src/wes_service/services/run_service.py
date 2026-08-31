"""Service layer for workflow run operations."""

import json
import logging
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wes_service.config import get_settings
from wes_service.core.storage import StorageBackend
from wes_service.db.models import (
    WorkflowAttachment,
    WorkflowRun,
    WorkflowState,
)
from wes_schemas.common import State
from wes_schemas.run import (
    Log,
    RunListResponse,
    RunLog,
    RunProgress,
    RunRequest,
    RunStatus,
    RunSummary,
)

logger = logging.getLogger(__name__)


class RunService:
    """Service for managing workflow runs."""

    def __init__(
        self,
        db: AsyncSession,
        storage: StorageBackend,
    ):
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
    ) -> WorkflowRun:
        """
        Create a new workflow run.

        Args:
            workflow_params: JSON string of workflow parameters
            workflow_type: Workflow type (CWL, WDL)
            workflow_type_version: Workflow type version
            workflow_url: URL to workflow definition
            workflow_attachments: List of uploaded files
            tags: JSON string of tags including ProjectId and TaskName
            workflow_engine: Workflow engine name
            workflow_engine_version: Workflow engine version
            workflow_engine_parameters: JSON string of engine parameters
            user_id: User creating the run

        Returns:
            WorkflowRun object representing the created workflow run
        """
        # Parse JSON strings
        params = json.loads(workflow_params) if workflow_params else {}
        tags_dict = json.loads(tags) if tags else {}

        if workflow_engine_parameters:
            engine_params = json.loads(workflow_engine_parameters)
        else:
            engine_params = {}

        output_bucket = get_settings().s3_bucket_name
        if "ProjectId" not in tags_dict:
            error_msg = "Job Submission Failed: ProjectId tag is required but not provided in tags"
            logger.error(error_msg)
            raise ValueError(error_msg)
        project_id = tags_dict.get("ProjectId")
        output_uri = f"s3://{output_bucket}/Project/{project_id}/"
        engine_params["outputUri"] = output_uri

        # Add "Name" tag if not already present, extracting it from workflow_engine_parameters
        if "TaskName" not in tags_dict and engine_params and "name" in engine_params:
            tags_dict["TaskName"] = engine_params["name"]

        # A launcher passes its own run id as ParentRunId on every child it
        # submits, which is what makes launcher progress derivable from the runs
        # table. Promoted to a column for the same reason ProjectId and TaskName
        # are: it is filtered and grouped on, not just displayed.
        parent_run_id = await self._resolve_parent_run_id(tags_dict.get("ParentRunId"))

        # Validate workflow type
        supported_types = list(
            self.settings.get_workflow_type_versions().keys()
        )
        if workflow_type.upper() not in supported_types:
            error_msg = f"Unsupported workflow type: {workflow_type}. " \
                        f"Supported types: {supported_types}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        self._validate_workflow_engine(workflow_engine, workflow_engine_version)

        # Create run record
        run_id = str(uuid4())
        task_name = tags_dict["TaskName"] if "TaskName" in tags_dict else 'wes-run-' + run_id
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
            project=project_id,
            task_name=task_name,
            parent_run_id=parent_run_id,
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

        # Submit workflow for execution
        # logger.info(f"Submitting workflow {run_id} for execution")
        # submission_response = await self.workflow_submission.submit_workflow(run, self.db)

        # if 'omics_run_id' not in submission_response:
        #     logger.error("Workflow submission response did not contain omics_run_id")
        #     run.state = WorkflowState.SYSTEM_ERROR

        #     detailed_error = None
        #     if run.system_logs:
        #         # Get the last error message (most recent one from workflow submission)
        #         for log_entry in reversed(run.system_logs):
        #             if log_entry and not log_entry.startswith("Successfully"):
        #                 detailed_error = log_entry
        #                 break

        #     if not detailed_error:
        #         detailed_error = f"Error submitting workflow {run_id} for execution"
        #         run.system_logs.append(detailed_error)

        #     await self.db.commit()
        #     return {"error": detailed_error}

        # # Update run with execution ID but keep QUEUED state
        # if not run.outputs:
        #     run.outputs = {}

        # run.workflow_run_id = submission_response['omics_run_id']

        # # Keep state as QUEUED - EventBridge events will update status and outputs
        # run.system_logs.append(
        #         f"Successfully submitted for execution. "
        #         f"Omics run ID: {submission_response['omics_run_id']}")
        # await self.db.commit()
        # logger.info(
        #         f"Successfully submitted workflow {run_id} for execution - "
        #         "run remains QUEUED until EventBridge status update"
        # )

        return run

    def _validate_workflow_engine(
        self,
        workflow_engine: str | None,
        workflow_engine_version: str | None,
    ) -> None:
        """
        Check a submitted engine against the engines service-info advertises.

        The engine decides which backend a run is dispatched to, so an
        unrecognised name has to be rejected here rather than resolved by the
        submission factory's default: a launcher submitted as "aws-batch" would
        otherwise be handed to HealthOmics, fail there on a deployment it never
        had, and report a HealthOmics error for a typo.

        Validated against Settings.get_workflow_engine_versions rather than a
        second list, because the spec makes that map the client's only way to
        discover legal values -- the check and the advertisement cannot disagree.

        An omitted engine stays legal and means this instance's default backend,
        which is what every run did before engines were dispatched on.
        workflow_engine_version is not checked: it does not affect dispatch, and
        the spec lets a server pick the version when only the engine is named
        (workflow_type_version is likewise unchecked).

        Raises:
            ValueError: If the engine is not advertised, or if a version was
                given with no engine -- the spec requires the engine in that case.
        """
        if not workflow_engine or not workflow_engine.strip():
            if workflow_engine_version:
                error_msg = (
                    "Job Submission Failed: workflow_engine is required when "
                    "workflow_engine_version is provided"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            return

        supported_engines = sorted(self.settings.get_workflow_engine_versions())
        if workflow_engine.strip().lower() not in supported_engines:
            error_msg = (
                f"Unsupported workflow engine: {workflow_engine}. "
                f"Supported engines: {supported_engines}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    async def _resolve_parent_run_id(self, parent_run_id: str | None) -> str | None:
        """
        Validate a ParentRunId tag against the runs table.

        A parent that does not exist is a client mistake worth rejecting at
        submission: accepting it would produce a child that no progress rollup
        ever counts and that no launcher can find again, which is invisible until
        someone wonders why a launcher reports fewer children than it submitted.

        Cycles need no check -- the parent must already exist and run ids are
        server-generated, so a run cannot name itself or a descendant.

        Returns:
            The parent run ID, or None if no ParentRunId tag was supplied.

        Raises:
            ValueError: If the named parent run does not exist.
        """
        if not parent_run_id:
            return None

        query = select(WorkflowRun.id).where(WorkflowRun.id == parent_run_id)
        result = await self.db.execute(query)
        if result.scalar_one_or_none() is None:
            error_msg = (
                f"Job Submission Failed: ParentRunId tag references a run that "
                f"does not exist: {parent_run_id}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        return parent_run_id

    async def list_runs(
        self,
        page_size: int | None,
        page_token: str | None,
        user_id: str | None,
        filters: dict[str, any] | None = None,
    ) -> RunListResponse:
        """
        List workflow runs with pagination and dynamic filtering.

        Args:
            page_size: Number of runs per page
            page_token: Token for next page
            user_id: Filter by user (None for all runs)
            filters: Dictionary containing filter criteria where:
                - String values: {column: value} → WorkflowRun.column == value
                - Dict values: {column: {key: value}} → WorkflowRun.column[key].as_string() == value

        Returns:
            RunListResponse with runs and next page token
        """
        page_size = self._normalize_page_size(page_size)
        offset = self._parse_page_token(page_token)

        # Build and execute query
        query = self._build_base_query(user_id)
        query = self._apply_filters_to_query(query, filters)
        query = query.offset(offset).limit(page_size + 1)

        # Execute and process results
        runs = await self._execute_query(query)
        summaries, next_token = self._process_results(runs, page_size, offset)
        total_count = await self._count_runs(user_id, filters)

        return RunListResponse(
            runs=summaries,
            next_page_token=next_token,
            total_count=total_count,
        )

    async def _count_runs(self, user_id: str | None, filters: dict[str, any] | None) -> int:
        """Count every run matching the same user and filters, ignoring pagination."""
        query = select(func.count()).select_from(WorkflowRun)
        query = self._apply_user_filter(query, user_id)
        query = self._apply_filters_to_query(query, filters)

        result = await self.db.execute(query)
        return result.scalar_one()

    def _normalize_page_size(self, page_size: int | None) -> int:
        """Normalize page size to valid range."""
        if page_size is None:
            return 10
        return min(page_size, 100)

    def _parse_page_token(self, page_token: str | None) -> int:
        """Parse page token to offset."""
        return int(page_token) if page_token else 0

    def _build_base_query(self, user_id: str | None):
        """Build base query with user filter if specified."""
        query = select(WorkflowRun).order_by(WorkflowRun.created_at.desc())
        return self._apply_user_filter(query, user_id)

    def _apply_user_filter(self, query, user_id: str | None):
        """Restrict a query to one user's runs, if a user was given."""
        if user_id:
            query = query.where(WorkflowRun.user_id == user_id)
        return query

    def _apply_filters_to_query(self, query, filters: dict[str, any] | None):
        """Apply dynamic filters to query."""
        if not filters or not isinstance(filters, dict):
            return query

        for filter_key, filter_value in filters.items():
            query = self._apply_single_filter(query, filter_key, filter_value)
        return query

    def _apply_single_filter(self, query, filter_key: str, filter_value: any):
        """Apply a single filter to the query."""
        try:
            if not hasattr(WorkflowRun, filter_key):
                return query

            column = getattr(WorkflowRun, filter_key)

            if isinstance(filter_value, dict):
                return self._apply_json_filter(query, column, filter_value)
            else:
                return self._apply_scalar_filter(query, column, filter_key, filter_value)
        except Exception:
            return query

    def _apply_json_filter(self, query, column, filter_value: dict):
        """Apply JSON column filter (e.g., tags, workflow_params)."""
        for json_key, json_value in filter_value.items():
            if isinstance(json_value, (dict, list)):
                # Complex objects: use JSON serialization
                json_str = json.dumps(json_value, separators=(',', ':'), sort_keys=True)
                query = query.where(column[json_key].as_string() == json_str)
            else:
                # Simple values: use string comparison
                query = query.where(column[json_key].as_string() == str(json_value))
        return query

    def _apply_scalar_filter(self, query, column, filter_key: str, filter_value: any):
        """Apply scalar column filter."""
        converted_value = self._convert_filter_value(filter_key, filter_value)
        if converted_value is not None:
            query = query.where(column == converted_value)
        return query

    def _convert_filter_value(self, filter_key: str, filter_value: any) -> any:
        """Convert filter value to appropriate type (e.g., state enum)."""
        if filter_key == "state" and isinstance(filter_value, str):
            try:
                return WorkflowState(filter_value)
            except ValueError:
                return None
        return filter_value

    async def _execute_query(self, query):
        """Execute query and return results."""
        result = await self.db.execute(query)
        return result.scalars().all()

    def _process_results(self, runs: list, page_size: int, offset: int) -> tuple[list, str]:
        """Process query results and generate pagination info."""
        has_more = len(runs) > page_size
        if has_more:
            runs = runs[:page_size]

        summaries = [self._run_to_summary(run) for run in runs]
        next_token = str(offset + page_size) if has_more else ""

        return summaries, next_token

    async def get_run_status(self, run_id: str, user_id: str | None) -> RunStatus:
        """
        Get workflow run status.

        Args:
            run_id: Run ID
            user_id: User ID (unused - all users have read access)

        Returns:
            RunStatus
        """
        run = await self._get_run(run_id, None)  # Allow read access to all users
        return RunStatus(
            run_id=run.id,
            state=State(run.state.value),
        )

    async def get_run_log(self, run_id: str, user_id: str | None) -> RunLog:
        """
        Get detailed workflow run log.

        Args:
            run_id: Run ID
            user_id: User ID (unused - all users have read access)

        Returns:
            RunLog
        """
        run = await self._get_run(run_id, None, load_relationships=True)

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

        return RunLog(
            run_id=run.id,
            request=request,
            state=State(run.state.value),
            name=run.task_name,
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
        run = await self._get_run(run_id, None)  # Get run without user restriction

        # Authorization check for write operations - only owner can cancel
        if user_id and run.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to cancel this workflow run",
            )

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

    async def get_run_progress(self, run_id: str, user_id: str | None) -> RunProgress:
        """
        Roll up the states of the runs a launcher run submitted.

        Counts direct children only. A launcher that submits launchers is
        reached by walking the tree one level at a time, which keeps this a
        single indexed GROUP BY instead of a recursive query.

        Args:
            run_id: Run ID of the launcher run
            user_id: User ID (unused - all users have read access)

        Returns:
            RunProgress
        """
        run = await self._get_run(run_id, None)  # Allow read access to all users

        query = (
            select(
                WorkflowRun.state,
                func.count(WorkflowRun.id),
                func.max(WorkflowRun.updated_at),
            )
            .where(WorkflowRun.parent_run_id == run_id)
            .group_by(WorkflowRun.state)
        )
        result = await self.db.execute(query)
        rows = result.all()

        counts = {state.value: 0 for state in WorkflowState}
        counts.update({state.value: count for state, count, _ in rows})

        last_updates = [last_update for _, _, last_update in rows if last_update]
        children_last_update = (
            max(last_updates).isoformat() + "Z" if last_updates else None
        )

        return RunProgress(
            run_id=run.id,
            state=State(run.state.value),
            children_total=sum(count for _, count, _ in rows),
            children_by_state=counts,
            children_last_update=children_last_update,
        )

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

        return run

    def _run_to_summary(self, run: WorkflowRun) -> RunSummary:
        """Convert WorkflowRun to RunSummary."""
        return RunSummary(
            run_id=run.id,
            state=State(run.state.value),
            start_time=(
                run.start_time.isoformat() + "Z" if run.start_time else None
            ),
            end_time=run.end_time.isoformat() + "Z" if run.end_time else None,
            tags=run.tags,
            name=run.task_name,
            project=run.project,
            workflow_url=run.workflow_url,
            submitted_by=run.user_id,
        )
