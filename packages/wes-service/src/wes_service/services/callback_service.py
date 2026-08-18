"""Service layer for callback operations."""

import logging
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from wes_service.config import get_settings
from wes_service.db.models import WorkflowRun, WorkflowState
from wes_schemas.callback import (
    CallbackResponse,
    ExecutorStateChangeCallback,
    OmicsStateChangeCallback,
)

logger = logging.getLogger(__name__)


def _cloudwatch_console_url(log_group: str, log_stream: str, region: str) -> str:
    """
    Build a CloudWatch Logs console link to one log stream.

    The console's fragment router wants each path segment percent-encoded and
    then the percent signs themselves escaped as ``$25``, so a group like
    ``/aws/batch/job`` reaches it as ``$252Faws$252Fbatch$252Fjob``. Encoding it
    once, the obvious way, produces a link that opens an empty log group.
    """
    def encode(value: str) -> str:
        return quote(value, safe="").replace("%", "$25")

    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
        f"?region={region}#logsV2:log-groups/log-group/{encode(log_group)}"
        f"/log-events/{encode(log_stream)}"
    )


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

    # Map AWS Batch job status to WorkflowState. Batch distinguishes "accepted
    # but no compute yet" (SUBMITTED/PENDING/RUNNABLE) from "container being
    # pulled and started" (STARTING), which lines up with QUEUED and
    # INITIALIZING better than the Omics vocabulary does.
    #
    # Batch has no cancellation status of its own: a terminated job reports
    # FAILED with a "canceled" status reason, so a caller that knows it asked
    # for termination reports CANCELED by sending that status explicitly.
    BATCH_STATUS_MAP = {
        'SUBMITTED': WorkflowState.QUEUED,
        'PENDING': WorkflowState.QUEUED,
        'RUNNABLE': WorkflowState.QUEUED,
        'STARTING': WorkflowState.INITIALIZING,
        'RUNNING': WorkflowState.RUNNING,
        'SUCCEEDED': WorkflowState.COMPLETE,
        'FAILED': WorkflowState.EXECUTOR_ERROR,
        'CANCELED': WorkflowState.CANCELED,
        # Reported by whoever submits the job when SubmitJob itself failed --
        # the run exists but no executor ever will, which is this service's
        # fault to own rather than an executor error.
        'SUBMIT_FAILED': WorkflowState.SYSTEM_ERROR,
    }

    # Status vocabularies by executor name, as sent on the generic callback.
    STATUS_MAPS = {
        'awsbatch': BATCH_STATUS_MAP,
        'omics': OMICS_STATUS_MAP,
        'awshealthomics': OMICS_STATUS_MAP,
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

        return await self.handle_state_change(
            payload,
            status_map=self.OMICS_STATUS_MAP,
            executor="Omics",
            executor_run_id=payload.omics_run_id,
        )

    async def handle_executor_state_change(
        self,
        payload: ExecutorStateChangeCallback,
    ) -> CallbackResponse:
        """
        Handle a state change reported by any execution backend.

        Args:
            payload: Callback payload naming the executor and its status

        Returns:
            CallbackResponse with update details

        Raises:
            HTTPException: 400 for an unknown executor or status, 404 for an
                unknown run
        """
        logger.info(
            f"Processing {payload.executor} state change callback: "
            f"wes_run_id={payload.wes_run_id}, "
            f"executor_run_id={payload.executor_run_id}, "
            f"status={payload.status}"
        )

        status_map = self.STATUS_MAPS.get(payload.executor.strip().lower())
        if status_map is None:
            logger.error(f"Unknown executor: {payload.executor}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unknown executor: {payload.executor}. "
                    f"Known executors: {sorted(self.STATUS_MAPS)}"
                ),
            )

        return await self.handle_state_change(
            payload,
            status_map=status_map,
            executor=payload.executor,
            executor_run_id=payload.executor_run_id,
        )

    async def handle_state_change(
        self,
        payload: OmicsStateChangeCallback | ExecutorStateChangeCallback,
        status_map: dict[str, WorkflowState],
        executor: str,
        executor_run_id: str | None,
    ) -> CallbackResponse:
        """
        Apply one executor state change to a run.

        The executor-independent core of callback handling: every backend needs
        the same idempotency check, the same transition validation, and the same
        terminal-state bookkeeping. What differs is the status vocabulary, which
        is why the map is a parameter rather than a lookup inside here.

        Args:
            payload: The callback payload
            status_map: The executor's status name to WorkflowState mapping
            executor: Executor name, used in log and error messages
            executor_run_id: The run's ID in the executor, if known yet

        Returns:
            CallbackResponse with update details

        Raises:
            HTTPException: If the run, status, or transition is not acceptable
        """
        run = await self._fetch_run(payload.wes_run_id)

        if duplicate := self._check_duplicate_event(run, payload):
            return duplicate

        await self._bind_executor_run_id(run, executor_run_id)
        await self._record_log_location(run, payload)
        new_state = self._map_status(payload.status, status_map, executor)
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
        """Backfill workflow_run_id from an Omics payload if not yet set."""
        await self._bind_executor_run_id(run, payload.omics_run_id)

    async def _bind_executor_run_id(
        self, run: WorkflowRun, executor_run_id: str | None
    ) -> None:
        """
        Record the run's ID in the execution backend, once.

        Written on the first callback that carries it and never overwritten: the
        column is the join key operators and log viewers use, so a later event
        reporting a different ID is a routing bug that should be visible as a
        mismatch rather than quietly replace what is already bound.
        """
        if executor_run_id and not run.workflow_run_id:
            run.workflow_run_id = executor_run_id
            attributes.flag_modified(run, "workflow_run_id")
            await self.db.commit()

    async def _record_log_location(
        self,
        run: WorkflowRun,
        payload: OmicsStateChangeCallback | ExecutorStateChangeCallback,
    ) -> None:
        """
        Turn a reported CloudWatch log stream into a link on the run.

        Set as soon as the stream is known -- while the job runs, not at the end
        -- because a stuck launcher is exactly when someone wants the logs. The
        raw stream name is kept alongside it so log viewers that page through
        CloudWatch themselves do not have to parse it back out of a console URL.

        A no-op for payloads that report no log stream, which is every Omics
        callback.
        """
        log_urls = payload.log_urls or {}
        stream_name = log_urls.get("log_stream_name")
        if not stream_name or run.stdout_url:
            return

        settings = get_settings()
        run.stdout_url = _cloudwatch_console_url(
            log_group=log_urls.get("log_group") or settings.batch_log_group,
            log_stream=stream_name,
            region=settings.aws_console_region,
        )
        run.outputs = {**(run.outputs or {}), "log_stream_name": stream_name}
        attributes.flag_modified(run, "stdout_url")
        attributes.flag_modified(run, "outputs")
        await self.db.commit()

    def _resolve_new_state(self, omics_status: str) -> WorkflowState:
        """Map Omics status string to WorkflowState or raise 400."""
        return self._map_status(omics_status, self.OMICS_STATUS_MAP, "Omics")

    def _map_status(
        self,
        executor_status: str,
        status_map: dict[str, WorkflowState],
        executor: str,
    ) -> WorkflowState:
        """Map an executor's status string to WorkflowState or raise 400."""
        new_state = status_map.get(executor_status)
        if not new_state:
            logger.error(f"Unknown {executor} status: {executor_status}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unknown {executor} status: {executor_status}. "
                    f"Known statuses: {sorted(status_map)}"
                ),
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

        # An executor that reports the container's real exit code wins over the
        # 0/1 stand-in: "exited 137" is the difference between a bug and an OOM
        # kill, and only the executor knows it. Omics reports no exit code.
        reported_exit_code = getattr(payload, "exit_code", None)

        if new_state == WorkflowState.COMPLETE:
            run.exit_code = 0 if reported_exit_code is None else reported_exit_code
            output_mapping = getattr(payload, "output_mapping", None)
            if output_mapping:
                run.outputs = run.outputs or {}
                run.outputs["output_mapping"] = output_mapping
                attributes.flag_modified(run, "outputs")
        else:
            run.exit_code = 1 if reported_exit_code is None else reported_exit_code

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
