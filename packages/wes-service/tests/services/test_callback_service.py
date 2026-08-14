"""Unit tests for CallbackService private methods."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from wes_service.db.models import WorkflowRun, WorkflowState
from wes_schemas.callback import CallbackResponse, OmicsStateChangeCallback
from wes_service.services.callback_service import CallbackService


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    """Create a CallbackService with a mocked DB."""
    return CallbackService(db=mock_db)


@pytest.fixture
def sample_run():
    """Create a sample WorkflowRun for testing."""
    run = WorkflowRun(
        id=str(uuid4()),
        state=WorkflowState.RUNNING,
        project="test-project",
        task_name="test-task",
        workflow_type="CWL",
        workflow_type_version="v1.0",
        workflow_url="s3://bucket/workflow.cwl",
        workflow_params={},
        system_logs=[],
        outputs=None,
        workflow_run_id=None,
        start_time=None,
        end_time=None,
        exit_code=None,
        last_event_id=None,
        last_callback_time=None,
    )
    return run


@pytest.fixture
def sample_payload():
    """Create a sample OmicsStateChangeCallback payload."""
    return OmicsStateChangeCallback(
        wes_run_id=str(uuid4()),
        omics_run_id="omics-12345",
        status="COMPLETED",
        event_time=datetime.now(UTC),
        event_id="evt-abc123",
        status_message=None,
        failure_reason=None,
        output_mapping=None,
        log_urls=None,
    )


class TestFetchRun:
    """Tests for _fetch_run."""

    @pytest.mark.asyncio
    async def test_returns_run_when_found(self, service, mock_db, sample_run):
        """Should return the workflow run when it exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_run
        mock_db.execute.return_value = mock_result

        result = await service._fetch_run(sample_run.id)

        assert result == sample_run
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self, service, mock_db):
        """Should raise HTTPException 404 when run doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await service._fetch_run("nonexistent-id")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail


class TestCheckDuplicateEvent:
    """Tests for _check_duplicate_event."""

    def test_returns_none_when_no_last_event_id(self, service, sample_run, sample_payload):
        """Should return None when run has no last_event_id."""
        sample_run.last_event_id = None

        result = service._check_duplicate_event(sample_run, sample_payload)

        assert result is None

    def test_returns_none_when_event_ids_differ(self, service, sample_run, sample_payload):
        """Should return None when event IDs don't match."""
        sample_run.last_event_id = "different-event-id"
        sample_payload.event_id = "evt-abc123"

        result = service._check_duplicate_event(sample_run, sample_payload)

        assert result is None

    def test_returns_response_when_duplicate(self, service, sample_run, sample_payload):
        """Should return CallbackResponse when event is a duplicate."""
        sample_payload.event_id = "evt-duplicate"
        sample_run.last_event_id = "evt-duplicate"
        sample_run.state = WorkflowState.RUNNING

        result = service._check_duplicate_event(sample_run, sample_payload)

        assert result is not None
        assert isinstance(result, CallbackResponse)
        assert result.already_processed is True
        assert result.success is True
        assert result.previous_state == "RUNNING"
        assert result.new_state == "RUNNING"

    def test_returns_none_when_event_id_is_none_in_payload(
        self, service, sample_run, sample_payload
    ):
        """Should return None when payload has no event_id."""
        sample_payload.event_id = None
        sample_run.last_event_id = "some-event-id"

        result = service._check_duplicate_event(sample_run, sample_payload)

        assert result is None


class TestSyncOmicsRunId:
    """Tests for _sync_omics_run_id."""

    @pytest.mark.asyncio
    async def test_sets_workflow_run_id_when_missing(
        self, service, mock_db, sample_run, sample_payload
    ):
        """Should set workflow_run_id when not already set."""
        sample_run.workflow_run_id = None
        sample_payload.omics_run_id = "omics-99999"

        await service._sync_omics_run_id(sample_run, sample_payload)

        assert sample_run.workflow_run_id == "omics-99999"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_workflow_run_id(
        self, service, mock_db, sample_run, sample_payload
    ):
        """Should not overwrite if workflow_run_id already exists."""
        sample_run.workflow_run_id = "existing-id"
        sample_payload.omics_run_id = "new-id"

        await service._sync_omics_run_id(sample_run, sample_payload)

        assert sample_run.workflow_run_id == "existing-id"
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_nothing_when_omics_run_id_is_none(
        self, service, mock_db, sample_run, sample_payload
    ):
        """Should do nothing if omics_run_id is not provided."""
        sample_run.workflow_run_id = None
        sample_payload.omics_run_id = None

        await service._sync_omics_run_id(sample_run, sample_payload)

        assert sample_run.workflow_run_id is None
        mock_db.commit.assert_not_called()


class TestResolveNewState:
    """Tests for _resolve_new_state."""

    @pytest.mark.parametrize(
        "omics_status,expected_state",
        [
            ("COMPLETED", WorkflowState.COMPLETE),
            ("FAILED", WorkflowState.EXECUTOR_ERROR),
            ("CANCELLED", WorkflowState.CANCELED),
            ("CANCELLED_RUNNING", WorkflowState.CANCELED),
            ("CANCELLED_STARTING", WorkflowState.CANCELED),
            ("STARTING", WorkflowState.RUNNING),
            ("RUNNING", WorkflowState.RUNNING),
            ("PENDING", WorkflowState.RUNNING),
            ("QUEUED", WorkflowState.RUNNING),
            ("STOPPING", WorkflowState.RUNNING),
            ("TERMINATING", WorkflowState.RUNNING),
        ],
    )
    def test_maps_known_statuses(self, service, omics_status, expected_state):
        """Should correctly map all known Omics statuses to WorkflowState."""
        result = service._resolve_new_state(omics_status)

        assert result == expected_state

    def test_raises_400_for_unknown_status(self, service):
        """Should raise HTTPException 400 for unknown Omics status."""
        with pytest.raises(HTTPException) as exc_info:
            service._resolve_new_state("UNKNOWN_STATUS")

        assert exc_info.value.status_code == 400
        assert "Unknown Omics status" in exc_info.value.detail


class TestRecordStartTime:
    """Tests for _record_start_time."""

    @pytest.mark.asyncio
    async def test_sets_start_time_on_first_running(
        self, service, mock_db, sample_run, sample_payload
    ):
        """Should set start_time when status is RUNNING and no start_time exists."""
        sample_run.start_time = None
        sample_payload.status = "RUNNING"
        event_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        sample_payload.event_time = event_time

        await service._record_start_time(sample_run, sample_payload)

        assert sample_run.start_time == event_time
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_start_time(
        self, service, mock_db, sample_run, sample_payload
    ):
        """Should not overwrite if start_time already set."""
        existing_time = datetime(2024, 1, 14, 8, 0, 0, tzinfo=UTC)
        sample_run.start_time = existing_time
        sample_payload.status = "RUNNING"

        await service._record_start_time(sample_run, sample_payload)

        assert sample_run.start_time == existing_time
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_nothing_for_non_running_status(
        self, service, mock_db, sample_run, sample_payload
    ):
        """Should do nothing when status is not RUNNING."""
        sample_run.start_time = None
        sample_payload.status = "COMPLETED"

        await service._record_start_time(sample_run, sample_payload)

        assert sample_run.start_time is None
        mock_db.commit.assert_not_called()


class TestBuildNoChangeResponse:
    """Tests for _build_no_change_response."""

    def test_returns_response_when_state_unchanged(self, service, sample_run):
        """Should return CallbackResponse when state hasn't changed."""
        sample_run.state = WorkflowState.RUNNING

        result = service._build_no_change_response(sample_run, WorkflowState.RUNNING)

        assert result is not None
        assert isinstance(result, CallbackResponse)
        assert result.success is True
        assert result.previous_state == "RUNNING"
        assert result.new_state == "RUNNING"
        assert result.message == "No state change"
        assert result.already_processed is False

    def test_returns_none_when_state_changed(self, service, sample_run):
        """Should return None when the state is different."""
        sample_run.state = WorkflowState.RUNNING

        result = service._build_no_change_response(sample_run, WorkflowState.COMPLETE)

        assert result is None


class TestHandleInvalidTransition:
    """Tests for _handle_invalid_transition."""

    def test_returns_none_for_valid_transition(self, service, sample_run):
        """Should return None when the transition is valid."""
        sample_run.state = WorkflowState.RUNNING

        result = service._handle_invalid_transition(
            sample_run, WorkflowState.RUNNING, WorkflowState.COMPLETE
        )

        assert result is None

    def test_returns_response_for_terminal_state(self, service, sample_run):
        """Should return a graceful response when run is already in terminal state."""
        sample_run.state = WorkflowState.COMPLETE

        result = service._handle_invalid_transition(
            sample_run, WorkflowState.COMPLETE, WorkflowState.RUNNING
        )

        assert result is not None
        assert isinstance(result, CallbackResponse)
        assert result.success is True
        assert result.previous_state == "COMPLETE"
        assert result.new_state == "COMPLETE"
        assert "terminal state" in result.message

    def test_raises_400_for_truly_invalid_transition(self, service, sample_run):
        """Should raise HTTPException 400 for invalid non-terminal transition."""
        sample_run.state = WorkflowState.RUNNING

        with pytest.raises(HTTPException) as exc_info:
            service._handle_invalid_transition(
                sample_run, WorkflowState.RUNNING, WorkflowState.QUEUED
            )

        assert exc_info.value.status_code == 400
        assert "Invalid state transition" in exc_info.value.detail


class TestUpdateTrackingFields:
    """Tests for _update_tracking_fields."""

    def test_updates_last_callback_time(self, service, sample_run, sample_payload):
        """Should update last_callback_time from payload."""
        event_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        sample_payload.event_time = event_time

        service._update_tracking_fields(sample_run, sample_payload)

        assert sample_run.last_callback_time == event_time

    def test_updates_last_event_id(self, service, sample_run, sample_payload):
        """Should update last_event_id from payload."""
        sample_payload.event_id = "evt-tracking-test"

        service._update_tracking_fields(sample_run, sample_payload)

        assert sample_run.last_event_id == "evt-tracking-test"


class TestAppendLogs:
    """Tests for _append_logs."""

    def test_appends_status_message(self, service, sample_run, sample_payload):
        """Should append status_message to system_logs."""
        sample_run.system_logs = []
        sample_payload.status_message = "Workflow is progressing"

        service._append_logs(sample_run, sample_payload)

        assert "Status: Workflow is progressing" in sample_run.system_logs

    def test_appends_failure_reason(self, service, sample_run, sample_payload):
        """Should append failure_reason to system_logs."""
        sample_run.system_logs = []
        sample_payload.failure_reason = "Out of memory"

        service._append_logs(sample_run, sample_payload)

        assert "Failure reason: Out of memory" in sample_run.system_logs

    def test_appends_both_status_and_failure(self, service, sample_run, sample_payload):
        """Should append both messages when both are provided."""
        sample_run.system_logs = []
        sample_payload.status_message = "Step 3 failed"
        sample_payload.failure_reason = "OOM error"

        service._append_logs(sample_run, sample_payload)

        assert len(sample_run.system_logs) == 2
        assert "Status: Step 3 failed" in sample_run.system_logs
        assert "Failure reason: OOM error" in sample_run.system_logs

    def test_does_nothing_when_no_messages(self, service, sample_run, sample_payload):
        """Should not modify system_logs when neither message is set."""
        sample_run.system_logs = ["existing log"]
        sample_payload.status_message = None
        sample_payload.failure_reason = None

        service._append_logs(sample_run, sample_payload)

        assert sample_run.system_logs == ["existing log"]


class TestHandleTerminalState:
    """Tests for _handle_terminal_state."""

    def test_sets_end_time_when_not_set(self, service, sample_run, sample_payload):
        """Should set end_time when not already set."""
        sample_run.end_time = None
        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)
        sample_payload.event_time = event_time

        service._handle_terminal_state(sample_run, sample_payload, WorkflowState.COMPLETE)

        assert sample_run.end_time == event_time

    def test_does_not_overwrite_existing_end_time(self, service, sample_run, sample_payload):
        """Should not overwrite end_time if already set."""
        existing_time = datetime(2024, 1, 15, 13, 0, 0, tzinfo=UTC)
        sample_run.end_time = existing_time
        sample_payload.event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)

        service._handle_terminal_state(sample_run, sample_payload, WorkflowState.COMPLETE)

        assert sample_run.end_time == existing_time

    def test_sets_exit_code_0_on_complete(self, service, sample_run, sample_payload):
        """Should set exit_code to 0 for COMPLETE state."""
        sample_run.end_time = None

        service._handle_terminal_state(sample_run, sample_payload, WorkflowState.COMPLETE)

        assert sample_run.exit_code == 0

    def test_sets_exit_code_1_on_error(self, service, sample_run, sample_payload):
        """Should set exit_code to 1 for non-COMPLETE terminal states."""
        sample_run.end_time = None

        service._handle_terminal_state(
            sample_run, sample_payload, WorkflowState.EXECUTOR_ERROR
        )

        assert sample_run.exit_code == 1

    def test_sets_exit_code_1_on_canceled(self, service, sample_run, sample_payload):
        """Should set exit_code to 1 for CANCELED state."""
        sample_run.end_time = None

        service._handle_terminal_state(sample_run, sample_payload, WorkflowState.CANCELED)

        assert sample_run.exit_code == 1

    def test_stores_log_urls(self, service, sample_run, sample_payload):
        """Should store log_urls in outputs when provided."""
        sample_run.end_time = None
        sample_run.outputs = None
        sample_payload.log_urls = {"engine": "s3://bucket/logs/engine.log"}

        service._handle_terminal_state(sample_run, sample_payload, WorkflowState.COMPLETE)

        assert sample_run.outputs["log_urls"] == {"engine": "s3://bucket/logs/engine.log"}

    def test_stores_output_mapping_on_complete(self, service, sample_run, sample_payload):
        """Should store output_mapping in outputs on COMPLETE."""
        sample_run.end_time = None
        sample_run.outputs = None
        sample_payload.output_mapping = {"result": "s3://bucket/output/result.txt"}

        service._handle_terminal_state(sample_run, sample_payload, WorkflowState.COMPLETE)

        assert sample_run.outputs["output_mapping"] == {
            "result": "s3://bucket/output/result.txt"
        }

    def test_does_not_store_output_mapping_on_error(
        self, service, sample_run, sample_payload
    ):
        """Should not store output_mapping on non-COMPLETE terminal states."""
        sample_run.end_time = None
        sample_run.outputs = None
        sample_payload.output_mapping = {"result": "s3://bucket/output/result.txt"}
        sample_payload.log_urls = None

        service._handle_terminal_state(
            sample_run, sample_payload, WorkflowState.EXECUTOR_ERROR
        )

        # outputs may be None or not contain output_mapping
        if sample_run.outputs:
            assert "output_mapping" not in sample_run.outputs

    def test_preserves_existing_outputs(self, service, sample_run, sample_payload):
        """Should preserve existing outputs when adding log_urls."""
        sample_run.end_time = None
        sample_run.outputs = {"existing_key": "existing_value"}
        sample_payload.log_urls = {"engine": "s3://bucket/logs/engine.log"}

        service._handle_terminal_state(sample_run, sample_payload, WorkflowState.COMPLETE)

        assert sample_run.outputs["existing_key"] == "existing_value"
        assert sample_run.outputs["log_urls"] == {"engine": "s3://bucket/logs/engine.log"}


class TestApplyStateUpdate:
    """Tests for _apply_state_update."""

    def test_sets_new_state(self, service, sample_run, sample_payload):
        """Should set the run's state to the new state."""
        sample_run.state = WorkflowState.RUNNING
        sample_run.end_time = None

        service._apply_state_update(sample_run, sample_payload, WorkflowState.COMPLETE)

        assert sample_run.state == WorkflowState.COMPLETE

    def test_calls_terminal_handling_for_terminal_state(
        self, service, sample_run, sample_payload
    ):
        """Should handle terminal state when new_state is terminal."""
        sample_run.state = WorkflowState.RUNNING
        sample_run.end_time = None
        sample_payload.event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC)

        service._apply_state_update(
            sample_run, sample_payload, WorkflowState.EXECUTOR_ERROR
        )

        assert sample_run.exit_code == 1
        assert sample_run.end_time == sample_payload.event_time

    def test_does_not_call_terminal_for_non_terminal(
        self, service, sample_run, sample_payload
    ):
        """Should not set exit_code or end_time for non-terminal states."""
        sample_run.state = WorkflowState.QUEUED
        sample_run.exit_code = None
        sample_run.end_time = None

        service._apply_state_update(sample_run, sample_payload, WorkflowState.RUNNING)

        assert sample_run.exit_code is None
        assert sample_run.end_time is None

    def test_updates_tracking_fields(self, service, sample_run, sample_payload):
        """Should update tracking fields."""
        sample_payload.event_id = "evt-apply-test"
        sample_payload.event_time = datetime(2024, 1, 15, 15, 0, 0, tzinfo=UTC)

        service._apply_state_update(sample_run, sample_payload, WorkflowState.RUNNING)

        assert sample_run.last_event_id == "evt-apply-test"
        assert sample_run.last_callback_time == sample_payload.event_time


class TestIsValidTransition:
    """Tests for _is_valid_transition."""

    @pytest.mark.parametrize(
        "from_state,to_state",
        [
            (WorkflowState.UNKNOWN, WorkflowState.RUNNING),
            (WorkflowState.UNKNOWN, WorkflowState.QUEUED),
            (WorkflowState.UNKNOWN, WorkflowState.INITIALIZING),
            (WorkflowState.UNKNOWN, WorkflowState.SYSTEM_ERROR),
            (WorkflowState.QUEUED, WorkflowState.INITIALIZING),
            (WorkflowState.QUEUED, WorkflowState.RUNNING),
            (WorkflowState.QUEUED, WorkflowState.CANCELED),
            (WorkflowState.QUEUED, WorkflowState.SYSTEM_ERROR),
            (WorkflowState.QUEUED, WorkflowState.EXECUTOR_ERROR),
            (WorkflowState.INITIALIZING, WorkflowState.RUNNING),
            (WorkflowState.INITIALIZING, WorkflowState.CANCELED),
            (WorkflowState.INITIALIZING, WorkflowState.EXECUTOR_ERROR),
            (WorkflowState.INITIALIZING, WorkflowState.SYSTEM_ERROR),
            (WorkflowState.RUNNING, WorkflowState.COMPLETE),
            (WorkflowState.RUNNING, WorkflowState.EXECUTOR_ERROR),
            (WorkflowState.RUNNING, WorkflowState.CANCELED),
            (WorkflowState.RUNNING, WorkflowState.SYSTEM_ERROR),
            (WorkflowState.RUNNING, WorkflowState.PAUSED),
            (WorkflowState.PAUSED, WorkflowState.RUNNING),
            (WorkflowState.PAUSED, WorkflowState.CANCELED),
            (WorkflowState.PAUSED, WorkflowState.SYSTEM_ERROR),
            (WorkflowState.CANCELING, WorkflowState.CANCELED),
            (WorkflowState.CANCELING, WorkflowState.SYSTEM_ERROR),
        ],
    )
    def test_valid_transitions(self, service, from_state, to_state):
        """Should return True for all valid state transitions."""
        assert service._is_valid_transition(from_state, to_state) is True

    @pytest.mark.parametrize(
        "from_state,to_state",
        [
            (WorkflowState.COMPLETE, WorkflowState.RUNNING),
            (WorkflowState.COMPLETE, WorkflowState.CANCELED),
            (WorkflowState.EXECUTOR_ERROR, WorkflowState.RUNNING),
            (WorkflowState.CANCELED, WorkflowState.RUNNING),
            (WorkflowState.SYSTEM_ERROR, WorkflowState.RUNNING),
        ],
    )
    def test_invalid_terminal_transitions(self, service, from_state, to_state):
        """Should return False for transitions from terminal states."""
        assert service._is_valid_transition(from_state, to_state) is False

    @pytest.mark.parametrize(
        "from_state,to_state",
        [
            (WorkflowState.RUNNING, WorkflowState.QUEUED),
            (WorkflowState.RUNNING, WorkflowState.INITIALIZING),
            (WorkflowState.UNKNOWN, WorkflowState.COMPLETE),
            (WorkflowState.QUEUED, WorkflowState.COMPLETE),
            (WorkflowState.PAUSED, WorkflowState.COMPLETE),
        ],
    )
    def test_invalid_non_terminal_transitions(self, service, from_state, to_state):
        """Should return False for invalid non-terminal transitions."""
        assert service._is_valid_transition(from_state, to_state) is False


class TestHandleOmicsStateChangeIntegration:
    """Integration tests for handle_omics_state_change orchestrator."""

    @pytest.mark.asyncio
    async def test_successful_state_transition(self, service, mock_db, sample_run):
        """Should process a valid state change end-to-end."""
        sample_run.state = WorkflowState.RUNNING
        sample_run.system_logs = []
        payload = OmicsStateChangeCallback(
            wes_run_id=sample_run.id,
            omics_run_id="omics-123",
            status="COMPLETED",
            event_time=datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC),
            event_id="evt-complete",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_run
        mock_db.execute.return_value = mock_result

        result = await service.handle_omics_state_change(payload)

        assert result.success is True
        assert result.previous_state == "RUNNING"
        assert result.new_state == "COMPLETE"
        assert result.already_processed is False

    @pytest.mark.asyncio
    async def test_duplicate_event_returns_early(self, service, mock_db, sample_run):
        """Should short-circuit for duplicate events."""
        sample_run.last_event_id = "evt-dup"
        sample_run.state = WorkflowState.COMPLETE
        payload = OmicsStateChangeCallback(
            wes_run_id=sample_run.id,
            omics_run_id="omics-123",
            status="COMPLETED",
            event_time=datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC),
            event_id="evt-dup",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_run
        mock_db.execute.return_value = mock_result

        result = await service.handle_omics_state_change(payload)

        assert result.success is True
        assert result.already_processed is True

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self, service, mock_db):
        """Should raise 404 when run doesn't exist."""
        payload = OmicsStateChangeCallback(
            wes_run_id="00000000-0000-0000-0000-000000000000",
            status="COMPLETED",
            event_time=datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await service.handle_omics_state_change(payload)

        assert exc_info.value.status_code == 404
