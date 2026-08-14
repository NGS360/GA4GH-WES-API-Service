"""Service layer for callback operations."""

import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from wes_service.db.models import WorkflowRun, WorkflowState
from wes_schemas.callback import CallbackResponse, OmicsStateChangeCallback

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

        run = await self._fetch_run(payload.wes_run_id)

        if duplicate := self._check_duplicate_event(run, payload):
            return duplicate

        await self._sync_omics_run_id(run, payload)
        new_state = self._resolve_new_state(payload.status)
        await self._record_start_time(run, payload)

        previous_state = run.state

        if no_change := self._build_no_change_response(run, new_state):
            return no_change

        if invalid := self._handle_invalid_transition(run, previous_state, new_state):
            return invalid

        self._apply_state_update(run, payload, new_state)

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

    # --- Private helpers ---

    async def _fetch_run(self, wes_run_id: str) -> WorkflowRun:
        """Fetch workflow run or raise 404."""
        result = await self.db.execute(
            select(WorkflowRun).where(WorkflowRun.id == wes_run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            logger.error(f"Workflow run not found: {wes_run_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow run {wes_run_id} not found",
            )
        return run

    def _check_duplicate_event(
        self, run: WorkflowRun, payload: OmicsStateChangeCallback
    ) -> Optional[CallbackResponse]:
        """Return a cached response if the event was already processed."""
        has_last_event = hasattr(run, 'last_event_id') and run.last_event_id
        if has_last_event and run.last_event_id == payload.event_id:
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
        return None

    async def _sync_omics_run_id(
        self, run: WorkflowRun, payload: OmicsStateChangeCallback
    ) -> None:
        """Backfill workflow_run_id from payload if not yet set."""
        if payload.omics_run_id and not run.workflow_run_id:
            run.workflow_run_id = payload.omics_run_id
            attributes.flag_modified(run, "workflow_run_id")
            await self.db.commit()

    def _resolve_new_state(self, omics_status: str) -> WorkflowState:
        """Map Omics status string to WorkflowState or raise 400."""
        new_state = self.OMICS_STATUS_MAP.get(omics_status)
        if not new_state:
            logger.error(f"Unknown Omics status: {omics_status}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown Omics status: {omics_status}",
            )
        return new_state

    async def _record_start_time(
        self, run: WorkflowRun, payload: OmicsStateChangeCallback
    ) -> None:
        """Set start_time on first RUNNING transition."""
        if payload.status == "RUNNING" and not run.start_time:
            run.start_time = payload.event_time
            attributes.flag_modified(run, "start_time")
            await self.db.commit()

    def _build_no_change_response(
        self, run: WorkflowRun, new_state: WorkflowState
    ) -> Optional[CallbackResponse]:
        """Return early response if state hasn't changed."""
        if new_state == run.state:
            logger.info(
                f"No state change for run {run.id} "
                f"(still {new_state}), returning success"
            )
            return CallbackResponse(
                success=True,
                wes_run_id=run.id,
                previous_state=run.state.value,
                new_state=new_state.value,
                message="No state change",
                already_processed=False,
            )
        return None

    def _handle_invalid_transition(
        self,
        run: WorkflowRun,
        previous_state: WorkflowState,
        new_state: WorkflowState,
    ) -> Optional[CallbackResponse]:
        """
        Validate state transition.

        Returns a CallbackResponse if the transition is gracefully ignored
        (e.g. run already in terminal state), or raises HTTPException if
        the transition is truly invalid. Returns None when valid.
        """
        if self._is_valid_transition(previous_state, new_state):
            return None

        # Already terminal → ignore gracefully
        if previous_state in self.TERMINAL_STATES:
            logger.warning(
                f"Run {run.id} already in terminal state "
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

        # Truly invalid transition
        logger.error(
            f"Invalid state transition for run {run.id}: "
            f"{previous_state} -> {new_state}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition: {previous_state} -> {new_state}",
        )

    def _apply_state_update(
        self,
        run: WorkflowRun,
        payload: OmicsStateChangeCallback,
        new_state: WorkflowState,
    ) -> None:
        """Mutate the run object with all state-change side effects."""
        run.state = new_state
        self._update_tracking_fields(run, payload)
        self._append_logs(run, payload)
        if new_state in self.TERMINAL_STATES:
            self._handle_terminal_state(run, payload, new_state)

    def _update_tracking_fields(
        self, run: WorkflowRun, payload: OmicsStateChangeCallback
    ) -> None:
        """Update callback tracking metadata on the run."""
        if hasattr(run, 'last_callback_time'):
            run.last_callback_time = payload.event_time
        if hasattr(run, 'last_event_id'):
            run.last_event_id = payload.event_id

    def _append_logs(
        self, run: WorkflowRun, payload: OmicsStateChangeCallback
    ) -> None:
        """Append status and failure messages to system logs."""
        if payload.status_message:
            run.system_logs.append(f"Status: {payload.status_message}")
            attributes.flag_modified(run, "system_logs")
        if payload.failure_reason:
            run.system_logs.append(f"Failure reason: {payload.failure_reason}")
            attributes.flag_modified(run, "system_logs")

    def _handle_terminal_state(
        self,
        run: WorkflowRun,
        payload: OmicsStateChangeCallback,
        new_state: WorkflowState,
    ) -> None:
        """Set end_time, exit_code, and outputs for terminal states."""
        if not run.end_time:
            run.end_time = payload.event_time
            attributes.flag_modified(run, "end_time")

        if payload.log_urls:
            run.outputs = run.outputs or {}
            run.outputs["log_urls"] = payload.log_urls
            attributes.flag_modified(run, "outputs")

        if new_state == WorkflowState.COMPLETE:
            run.exit_code = 0
            if payload.output_mapping:
                run.outputs = run.outputs or {}
                run.outputs["output_mapping"] = payload.output_mapping
                attributes.flag_modified(run, "outputs")
        else:
            run.exit_code = 1

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
                WorkflowState.EXECUTOR_ERROR,
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
