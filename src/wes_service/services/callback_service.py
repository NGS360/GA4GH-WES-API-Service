"""Service layer for callback operations."""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from src.wes_service.db.models import WorkflowRun, WorkflowState
from src.wes_service.schemas.callback import CallbackResponse, OmicsStateChangeCallback

logger = logging.getLogger(__name__)


class CallbackService:
    """Service for handling internal callbacks."""

    # Map HealthOmics status to WorkflowState
    OMICS_STATUS_MAP = {
        'COMPLETED': WorkflowState.COMPLETE,
        'FAILED': WorkflowState.EXECUTOR_ERROR,
        'CANCELLED': WorkflowState.CANCELED,
        'CANCELLED_RUNNING': WorkflowState.CANCELED,
        'CANCELLED_STARTING': WorkflowState.CANCELED,
        'STARTING': WorkflowState.RUNNING,
        'RUNNING': WorkflowState.RUNNING,
        'PENDING': WorkflowState.RUNNING,
        'QUEUED': WorkflowState.RUNNING,
        'STOPPING': WorkflowState.RUNNING,
        'TERMINATING': WorkflowState.RUNNING,
    }

    # Terminal states that mark end of workflow
    TERMINAL_STATES = {
        WorkflowState.COMPLETE,
        WorkflowState.EXECUTOR_ERROR,
        WorkflowState.CANCELED,
        WorkflowState.SYSTEM_ERROR,
    }

    def __init__(self, db: AsyncSession):
        """Initialize callback service."""
        self.db = db

    async def handle_omics_state_change(
        self,
        payload: OmicsStateChangeCallback,
    ) -> CallbackResponse:
        """
        Handle AWS HealthOmics state change callback.

        Args:
            payload: Callback payload from Lambda

        Returns:
            CallbackResponse with update details

        Raises:
            HTTPException: If update fails
        """
        logger.info(
            f"Processing Omics state change callback: "
            f"wes_run_id={payload.wes_run_id}, "
            f"omics_run_id={payload.omics_run_id}, "
            f"status={payload.status}"
        )

        # Get the workflow run
        result = await self.db.execute(
            select(WorkflowRun).where(WorkflowRun.id == payload.wes_run_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            logger.error(f"Workflow run not found: {payload.wes_run_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow run {payload.wes_run_id} not found",
            )

        # Check for duplicate event (idempotency)
        if hasattr(run, 'last_event_id') and run.last_event_id == payload.event_id:
            logger.info(
                f"Duplicate event {payload.event_id} for run {payload.wes_run_id}, "
                f"returning cached response"
            )
            return CallbackResponse(
                success=True,
                wes_run_id=run.id,
                previous_state=run.state.value,
                new_state=run.state.value,
                message=f"Event {payload.event_id} already processed",
                already_processed=True,
            )

        # Store previous state
        previous_state = run.state

        # Map Omics status to WES state
        new_state = self.OMICS_STATUS_MAP.get(payload.status)
        if not new_state:
            logger.error(f"Unknown Omics status: {payload.status}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown Omics status: {payload.status}",
            )

        # Validate state transition
        if not self._is_valid_transition(previous_state, new_state):
            # If run is already in terminal state, don't update but return success
            if previous_state in self.TERMINAL_STATES:
                logger.warning(
                    f"Run {payload.wes_run_id} already in terminal state "
                    f"{previous_state}, ignoring update to {new_state}"
                )
                return CallbackResponse(
                    success=True,
                    wes_run_id=run.id,
                    previous_state=previous_state.value,
                    new_state=previous_state.value,
                    message=f"Run already in terminal state {previous_state}",
                    already_processed=False,
                )

            logger.error(
                f"Invalid state transition for run {payload.wes_run_id}: "
                f"{previous_state} -> {new_state}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state transition: {previous_state} -> {new_state}",
            )

        # Update the workflow run
        run.state = new_state

        # Update callback tracking fields
        if hasattr(run, 'last_callback_time'):
            run.last_callback_time = datetime.now(timezone.utc)
        if hasattr(run, 'last_event_id'):
            run.last_event_id = payload.event_id

        # Add system log entry
        log_msg = (
            f"State updated via callback: {previous_state} -> {new_state} "
            f"(Omics: {payload.status})"
        )
        run.system_logs.append(log_msg)
        attributes.flag_modified(run, "system_logs")

        # If status message provided, add to logs
        if payload.status_message:
            run.system_logs.append(f"Status: {payload.status_message}")
            attributes.flag_modified(run, "system_logs")

        # If failure reason provided, add to logs
        if payload.failure_reason:
            run.system_logs.append(f"Failure reason: {payload.failure_reason}")
            attributes.flag_modified(run, "system_logs")

        # If terminal state, set end time and exit code
        if new_state in self.TERMINAL_STATES:
            if not run.end_time:
                run.end_time = datetime.now(timezone.utc)

            # Store log urls if provided
            if payload.log_urls:
                run.outputs = run.outputs or {}
                run.outputs["log_urls"] = payload.log_urls
                attributes.flag_modified(run, "outputs")

            if new_state == WorkflowState.COMPLETE:
                run.exit_code = 0
                # Store output mapping if provided
                if payload.output_mapping:
                    run.outputs = run.outputs or {}
                    run.outputs["output_mapping"] = payload.output_mapping
                    attributes.flag_modified(run, "outputs")
            else:
                run.exit_code = 1

        # Commit the transaction
        await self.db.commit()
        await self.db.refresh(run)

        logger.info(
            f"Successfully updated run {payload.wes_run_id}: "
            f"{previous_state} -> {new_state}"
        )

        return CallbackResponse(
            success=True,
            wes_run_id=run.id,
            previous_state=previous_state.value,
            new_state=new_state.value,
            message=f"Successfully updated state from {previous_state} to {new_state}",
            already_processed=False,
        )

    def _is_valid_transition(
        self,
        from_state: WorkflowState,
        to_state: WorkflowState,
    ) -> bool:
        """
        Check if state transition is valid.

        Args:
            from_state: Current state
            to_state: Desired new state

        Returns:
            True if transition is valid
        """
        # Can't transition from terminal states
        if from_state in self.TERMINAL_STATES:
            return False

        # Define valid transitions
        valid_transitions = {
            WorkflowState.UNKNOWN: {
                WorkflowState.QUEUED,
                WorkflowState.INITIALIZING,
                WorkflowState.RUNNING,
                WorkflowState.SYSTEM_ERROR,
            },
            WorkflowState.QUEUED: {
                WorkflowState.INITIALIZING,
                WorkflowState.RUNNING,
                WorkflowState.CANCELED,
                WorkflowState.SYSTEM_ERROR,
            },
            WorkflowState.INITIALIZING: {
                WorkflowState.RUNNING,
                WorkflowState.CANCELED,
                WorkflowState.EXECUTOR_ERROR,
                WorkflowState.SYSTEM_ERROR,
            },
            WorkflowState.RUNNING: {
                WorkflowState.COMPLETE,
                WorkflowState.EXECUTOR_ERROR,
                WorkflowState.CANCELED,
                WorkflowState.SYSTEM_ERROR,
                WorkflowState.PAUSED,
            },
            WorkflowState.PAUSED: {
                WorkflowState.RUNNING,
                WorkflowState.CANCELED,
                WorkflowState.SYSTEM_ERROR,
            },
            WorkflowState.CANCELING: {
                WorkflowState.CANCELED,
                WorkflowState.SYSTEM_ERROR,
            },
        }

        # Check if transition is in the valid set
        return to_state in valid_transitions.get(from_state, set())
