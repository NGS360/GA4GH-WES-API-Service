"""Tests for run service."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.wes_service.db.models import WorkflowRun, WorkflowState
from src.wes_service.services.run_service import RunService
from src.wes_service.services.workflow_submission_service import WorkflowSubmissionService

# cancel_run builds the submission service itself, so patch it where it is
# looked up rather than where it is defined.
RUN_SERVICE_SUBMISSION_PATCH = (
    'src.wes_service.services.run_service.LambdaWorkflowSubmissionService'
)


class MockWorkflowSubmissionService(WorkflowSubmissionService):
    """Mock workflow submission service for testing."""

    def __init__(self):
        """Initialize mock service without requiring real settings."""
        # Mock the settings dependency to avoid real configuration requirements
        self.ngs360_api_url = "http://mock-ngs360-api.test"

    async def submit_workflow(self, run, db, auth_token=None) -> dict:
        """Mock workflow submission that returns a fake omics_run_id."""
        # Mock the NGS360 API call within submit_workflow
        return {"omics_run_id": f"omics-{run.id}", "statusCode": 200}

    async def cancel_omics_run(self, wes_run_id: str, omics_run_id: str) -> None:
        """No-op: required by the abstract base class."""


@pytest.fixture
def mock_workflow_submission():
    """Fixture for mock workflow submission service."""
    return MockWorkflowSubmissionService()


@pytest.mark.asyncio
class TestRunService:
    """Tests for RunService."""
    async def test_paml_get_task_state(self, test_db, mock_storage):
        """Test get task state through PAML"""
        # Mimic inputs of PAML get_task_state()
        task = {
            "id": "test-get-state"
        }

        # Mock run record
        run = WorkflowRun(
            id=task["id"],
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="123456",
            tags={
                "TaskName": "test_name",
                "ProjectId": "test_project"
            },
            project="test_project",
            task_name="test_name",
        )
        test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage)

        # Get task status
        status = await service.get_run_status(task["id"], None)

        assert status.run_id == "test-get-state"
        assert status.state.value == "COMPLETE"

    async def test_create_run(self, test_db, mock_storage):
        """Test creating a new workflow run."""
        service = RunService(test_db, mock_storage)

        workflow_run = await service.create_run(
            workflow_params='{"input": "value"}',
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            workflow_attachments=None,
            tags='{"ProjectId": "test"}',
            workflow_engine="cwltool",
            workflow_engine_version="3.1",
            workflow_engine_parameters=None,
            user_id="testuser",
        )

        assert workflow_run is not None
        run_id = workflow_run.id
        assert isinstance(run_id, str)

        # Verify run was created in database
        result = await test_db.get(WorkflowRun, run_id)
        assert result is not None
        assert result.workflow_type == "CWL"
        assert result.state == WorkflowState.QUEUED

    async def test_list_runs_empty(self, test_db, mock_storage):
        """Test listing runs when none exist."""
        service = RunService(test_db, mock_storage)

        result = await service.list_runs(
            page_size=10,
            page_token=None,
            user_id=None,
        )

        assert result.runs == []
        assert result.next_page_token == ""

    async def test_get_run_status(self, test_db, mock_storage):
        """Test getting run status."""
        run = WorkflowRun(
            id="test-status",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            project="test-project",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage)
        status = await service.get_run_status("test-status", None)

        assert status.run_id == "test-status"
        assert status.state.value == "RUNNING"

    async def test_cancel_run(self, test_db, mock_storage):
        """Test canceling a run asks the backend to stop it."""
        run = WorkflowRun(
            id="test-cancel",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            # Required: a run is only cancellable once the backend has
            # reported its run id, which is what CancelRun needs.
            workflow_run_id="omics-run-123",
            tags={},
            project="test-project",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage)
        with patch(RUN_SERVICE_SUBMISSION_PATCH) as mock_service:
            cancel_calls = []

            async def mock_cancel_omics_run(wes_run_id, omics_run_id):
                cancel_calls.append((wes_run_id, omics_run_id))

            mock_instance = MagicMock()
            mock_instance.cancel_omics_run = mock_cancel_omics_run
            mock_service.return_value = mock_instance

            result = await service.cancel_run("test-cancel", None)

        assert result == "test-cancel"
        assert cancel_calls == [("test-cancel", "omics-run-123")]

        # State is CANCELING, not CANCELED: the move to CANCELED happens when
        # the backend reports a terminal status through the callback endpoint.
        await test_db.refresh(run)
        assert run.state == WorkflowState.CANCELING

    async def test_cancel_run_without_backend_run_id(self, test_db, mock_storage):
        """A run with no backend run id is refused, not marked CANCELED."""
        run = WorkflowRun(
            id="test-cancel-no-id",
            state=WorkflowState.QUEUED,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            workflow_run_id=None,
            tags={},
            project="test-project",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage)
        with patch(RUN_SERVICE_SUBMISSION_PATCH) as mock_service:
            with pytest.raises(HTTPException) as exc_info:
                await service.cancel_run("test-cancel-no-id", None)

        assert exc_info.value.status_code == 400
        assert "cannot be canceled yet" in exc_info.value.detail
        mock_service.assert_not_called()

        await test_db.refresh(run)
        assert run.state == WorkflowState.QUEUED

    async def test_get_system_state_counts(self, test_db, mock_storage):
        """Test getting system state counts."""
        # Create runs in different states
        runs = [
            WorkflowRun(
                id=f"run-{i}",
                state=WorkflowState.QUEUED if i % 2 == 0 else WorkflowState.RUNNING,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                tags={},
                project="test-project",
                task_name=f"test-task-{i}",
            )
            for i in range(4)
        ]
        for run in runs:
            test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage)
        counts = await service.get_system_state_counts()

        assert isinstance(counts, dict)
        assert counts["QUEUED"] == 2
        assert counts["RUNNING"] == 2
        assert counts["COMPLETE"] == 0
