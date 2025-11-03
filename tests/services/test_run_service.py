"""Tests for run service."""

import pytest

from src.wes_service.db.models import WorkflowRun, WorkflowState
from src.wes_service.services.run_service import RunService


@pytest.mark.asyncio
class TestRunService:
    """Tests for RunService."""

    async def test_create_run(self, test_db, mock_storage):
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

        service = RunService(test_db, mock_storage)
        counts = await service.get_system_state_counts()

        assert isinstance(counts, dict)
        assert counts["QUEUED"] == 2
        assert counts["RUNNING"] == 2
        assert counts["COMPLETE"] == 0
