"""Tests for run service."""

import pytest
import json
from unittest.mock import AsyncMock, patch

from src.wes_service.db.models import WorkflowRun, WorkflowState
from src.wes_service.services.run_service import RunService
from src.wes_service.services.workflow_submission_service import WorkflowSubmissionService


class MockWorkflowSubmissionService(WorkflowSubmissionService):
    """Mock workflow submission service for testing."""

    def __init__(self):
        """Initialize mock service without requiring real settings."""
        # Mock the settings dependency to avoid real configuration requirements
        self.ngs360_api_url = "http://mock-ngs360-api.test"

    async def submit_workflow(self, run) -> dict:
        """Mock workflow submission that returns a fake omics_run_id."""
        # Mock the NGS360 API call within submit_workflow
        engine_id = await self._get_engine_id_from_ngs360(run.workflow_url)
        return {"omics_run_id": f"omics-{run.id}", "statusCode": 200}

    async def _get_engine_id_from_ngs360(self, workflow_id: str) -> str:
        """Mock NGS360 API call that returns a fake engine_id."""
        return f"mock-engine-{workflow_id}"


@pytest.fixture
def mock_workflow_submission():
    """Fixture for mock workflow submission service."""
    return MockWorkflowSubmissionService()


@pytest.mark.asyncio
class TestRunService:
    """Tests for RunService."""

    async def test_paml_submit_task(self, test_db, mock_storage, mock_workflow_submission):
        """Test submit task through PAML"""
        # Mimic inputs of PAML submit_task()
        name = "test_wes_run"
        project = {
            "name": "test_project_name",
            "id": "test_project_id",
        }
        workflow = "1234567"
        parameters = {
            "input_file": "s3://bucket/input.fastq",
            "reference_genome": "s3://bucket/reference.fa"
        }
        execution_settings = {"cacheId": "12345"}

        # Mock run service
        service = RunService(test_db, mock_storage)

        workflow_engine_parameters = {
            "cacheId": execution_settings["cacheId"],
            "name": name
        }
        run_id = await service.create_run(
            workflow_params=json.dumps(parameters),
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url=workflow,
            tags=json.dumps({"Name": name, "Project": project["id"]}),
            workflow_engine_parameters=json.dumps(
                workflow_engine_parameters
            ),
            workflow_attachments=None,
            workflow_engine="CWL",
            workflow_engine_version="v1.0",
            user_id="ngs360",
        )

        # Verify run was created correctly and added to db
        assert run_id is not None
        assert isinstance(run_id, str)
        result = await test_db.get(WorkflowRun, run_id)
        assert result is not None
        assert result.workflow_type == "CWL"
        assert result.state == WorkflowState.QUEUED

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
                "Name": "test_name",
                "Project": "test_project"
            },
        )
        test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage, mock_workflow_submission)

        # Get task status
        status = await service.get_run_status(task["id"], None)

        assert status.run_id == "test-get-state"
        assert status.state.value == "COMPLETE"

    async def test_create_run(self, test_db, mock_storage, mock_workflow_submission):
        """Test creating a new workflow run."""
        service = RunService(test_db, mock_storage)

        run_id = await service.create_run(
            workflow_params='{"input": "value"}',
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            workflow_attachments=None,
            tags='{"project": "test"}',
            workflow_engine="cwltool",
            workflow_engine_version="3.1",
            workflow_engine_parameters=None,
            user_id="testuser",
        )

        assert run_id is not None
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
        )
        test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage)
        status = await service.get_run_status("test-status", None)

        assert status.run_id == "test-status"
        assert status.state.value == "RUNNING"

    async def test_cancel_run(self, test_db, mock_storage):
        """Test canceling a run."""
        run = WorkflowRun(
            id="test-cancel",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
        )
        test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage)
        result = await service.cancel_run("test-cancel", None)

        assert result == "test-cancel"

        # Verify state changed
        await test_db.refresh(run)
        assert run.state == WorkflowState.CANCELING

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
            )
            for i in range(4)
        ]
        for run in runs:
            test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage, mock_workflow_submission)
        counts = await service.get_system_state_counts()

        assert isinstance(counts, dict)
        assert counts["QUEUED"] == 2
        assert counts["RUNNING"] == 2
        assert counts["COMPLETE"] == 0
