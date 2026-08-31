"""Tests for run service."""

import pytest

from wes_service.db.models import WorkflowRun, WorkflowState
from wes_service.services.run_service import RunService
from wes_service.services.workflow_submission_service import WorkflowSubmissionService


class MockWorkflowSubmissionService(WorkflowSubmissionService):
    """Mock workflow submission service for testing."""

    def __init__(self):
        """Initialize mock service without requiring real settings."""
        # Mock the settings dependency to avoid real configuration requirements
        self.ngs360_api_url = "http://mock-ngs360-api.test"

    async def submit_workflow(self, run, db) -> dict:
        """Mock workflow submission that returns a fake omics_run_id."""
        # Mock the NGS360 API call within submit_workflow
        return {"omics_run_id": f"omics-{run.id}", "statusCode": 200}


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
            workflow_engine="awshealthomics",
            workflow_engine_version="2022-11-28",
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

    async def test_create_run_without_engine_is_allowed(self, test_db, mock_storage):
        """A run naming no engine is legal and means this instance's default."""
        service = RunService(test_db, mock_storage)

        workflow_run = await service.create_run(
            workflow_params=None,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            workflow_attachments=None,
            tags='{"ProjectId": "test"}',
            workflow_engine=None,
            workflow_engine_version=None,
            workflow_engine_parameters=None,
            user_id="testuser",
        )

        assert workflow_run.workflow_engine is None

    @pytest.mark.parametrize("engine", ["aws-batch", "AWS Batch", "cwltool", "batch"])
    async def test_create_run_rejects_unadvertised_engine(
        self, test_db, mock_storage, engine
    ):
        """
        An engine service-info does not advertise is a 400, not a default.

        Dispatch is keyed on this value, so accepting a name nobody advertised
        sends the run to whichever backend happens to be the fallback.
        """
        service = RunService(test_db, mock_storage)

        with pytest.raises(ValueError, match="Unsupported workflow engine"):
            await service.create_run(
                workflow_params=None,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                workflow_attachments=None,
                tags='{"ProjectId": "test"}',
                workflow_engine=engine,
                workflow_engine_version=None,
                workflow_engine_parameters=None,
                user_id="testuser",
            )

    @pytest.mark.parametrize("engine", ["awsbatch", "AWSBatch", "  awshealthomics  "])
    async def test_create_run_accepts_advertised_engine_any_case(
        self, test_db, mock_storage, engine
    ):
        """Case and padding are presentation; the engine name still resolves."""
        service = RunService(test_db, mock_storage)

        workflow_run = await service.create_run(
            workflow_params=None,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            workflow_attachments=None,
            tags='{"ProjectId": "test"}',
            workflow_engine=engine,
            workflow_engine_version=None,
            workflow_engine_parameters=None,
            user_id="testuser",
        )

        assert workflow_run.workflow_engine == engine

    async def test_create_run_rejects_engine_version_without_engine(
        self, test_db, mock_storage
    ):
        """The spec requires workflow_engine when workflow_engine_version is given."""
        service = RunService(test_db, mock_storage)

        with pytest.raises(ValueError, match="workflow_engine is required"):
            await service.create_run(
                workflow_params=None,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                workflow_attachments=None,
                tags='{"ProjectId": "test"}',
                workflow_engine=None,
                workflow_engine_version="2022-11-28",
                workflow_engine_parameters=None,
                user_id="testuser",
            )

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
        """Test canceling a run."""
        run = WorkflowRun(
            id="test-cancel",
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
        result = await service.cancel_run("test-cancel", None)

        assert result == "test-cancel"

        # Verify state changed
        await test_db.refresh(run)
        assert run.state == WorkflowState.CANCELING

    async def test_create_run_promotes_parent_run_id_tag(self, test_db, mock_storage):
        """A ParentRunId tag becomes the indexed parent_run_id column."""
        service = RunService(test_db, mock_storage)

        parent = await service.create_run(
            workflow_params=None,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="LAUNCHER:1.0.0",
            workflow_attachments=None,
            tags='{"ProjectId": "test", "TaskName": "launcher"}',
            workflow_engine="awsbatch",
            workflow_engine_version=None,
            workflow_engine_parameters=None,
            user_id="testuser",
        )

        child = await service.create_run(
            workflow_params=None,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            workflow_attachments=None,
            tags=(
                '{"ProjectId": "test", "TaskName": "sampleA", '
                f'"ParentRunId": "{parent.id}"}}'
            ),
            workflow_engine="awshealthomics",
            workflow_engine_version=None,
            workflow_engine_parameters=None,
            user_id="testuser",
        )

        assert parent.parent_run_id is None
        assert child.parent_run_id == parent.id
        # The tag is kept as well as promoted, so the submitted request stays
        # reproducible from the record.
        assert child.tags["ParentRunId"] == parent.id

    async def test_create_run_rejects_unknown_parent(self, test_db, mock_storage):
        """A ParentRunId naming no run is refused rather than orphaning a child."""
        service = RunService(test_db, mock_storage)

        with pytest.raises(ValueError, match="ParentRunId"):
            await service.create_run(
                workflow_params=None,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                workflow_attachments=None,
                tags='{"ProjectId": "test", "ParentRunId": "no-such-run"}',
                workflow_engine="awshealthomics",
                workflow_engine_version=None,
                workflow_engine_parameters=None,
                user_id="testuser",
            )

    async def test_parent_run_id_is_reported_by_reads(self, test_db, mock_storage):
        """Lineage is visible in both the listing and the full run record, via the
        spec-compliant tags field rather than a bespoke response field."""
        parent = WorkflowRun(
            id="launcher-1",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="LAUNCHER:1.0.0",
            tags={},
            project="test-project",
            task_name="launcher",
        )
        child = WorkflowRun(
            id="child-1",
            state=WorkflowState.QUEUED,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={"ParentRunId": "launcher-1"},
            project="test-project",
            task_name="sampleA",
            parent_run_id="launcher-1",
        )
        test_db.add_all([parent, child])
        await test_db.commit()

        service = RunService(test_db, mock_storage)

        run_log = await service.get_run_log("child-1", None)
        assert run_log.request.tags["ParentRunId"] == "launcher-1"

        listing = await service.list_runs(page_size=10, page_token=None, user_id=None)
        by_id = {summary.run_id: summary for summary in listing.runs}
        assert by_id["child-1"].tags["ParentRunId"] == "launcher-1"
        assert "ParentRunId" not in by_id["launcher-1"].tags

    async def test_list_runs_filters_on_parent_run_id(self, test_db, mock_storage):
        """The promoted column is filterable, which is how a launcher finds its own children."""
        runs = [
            WorkflowRun(
                id="launcher-a",
                state=WorkflowState.RUNNING,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="LAUNCHER:1.0.0",
                tags={},
                project="test-project",
                task_name="launcher-a",
            ),
            WorkflowRun(
                id="launcher-b",
                state=WorkflowState.RUNNING,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="LAUNCHER:1.0.0",
                tags={},
                project="test-project",
                task_name="launcher-b",
            ),
            WorkflowRun(
                id="a-child",
                state=WorkflowState.QUEUED,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                tags={},
                project="test-project",
                task_name="sampleA",
                parent_run_id="launcher-a",
            ),
            WorkflowRun(
                id="b-child",
                state=WorkflowState.QUEUED,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                tags={},
                project="test-project",
                task_name="sampleB",
                parent_run_id="launcher-b",
            ),
        ]
        test_db.add_all(runs)
        await test_db.commit()

        service = RunService(test_db, mock_storage)
        result = await service.list_runs(
            page_size=10,
            page_token=None,
            user_id=None,
            filters={"parent_run_id": "launcher-a"},
        )

        assert [summary.run_id for summary in result.runs] == ["a-child"]

    async def test_get_run_progress_rolls_up_children(self, test_db, mock_storage):
        """Progress counts direct children by state, and the launcher's state stays its own."""
        parent = WorkflowRun(
            id="launcher-1",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="LAUNCHER:1.0.0",
            tags={},
            project="test-project",
            task_name="launcher",
        )
        children = [
            WorkflowRun(
                id=f"child-{i}",
                state=state,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                tags={},
                project="test-project",
                task_name=f"sample-{i}",
                parent_run_id="launcher-1",
            )
            for i, state in enumerate(
                [WorkflowState.COMPLETE, WorkflowState.COMPLETE, WorkflowState.RUNNING]
            )
        ]
        # A grandchild: counted under its own parent, not rolled up into the
        # launcher's totals.
        grandchild = WorkflowRun(
            id="grandchild",
            state=WorkflowState.QUEUED,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            project="test-project",
            task_name="sub-sample",
            parent_run_id="child-0",
        )
        test_db.add_all([parent, *children, grandchild])
        await test_db.commit()

        service = RunService(test_db, mock_storage)
        progress = await service.get_run_progress("launcher-1", None)

        assert progress.run_id == "launcher-1"
        assert progress.state.value == "RUNNING"
        assert progress.children_total == 3
        assert progress.children_by_state["COMPLETE"] == 2
        assert progress.children_by_state["RUNNING"] == 1
        # Every state is reported, so a caller can render a full breakdown
        # without knowing which states happen to be occupied.
        assert progress.children_by_state["EXECUTOR_ERROR"] == 0
        assert progress.children_last_update is not None

    async def test_get_run_progress_with_no_children(self, test_db, mock_storage):
        """An ordinary run reports zero children rather than failing."""
        run = WorkflowRun(
            id="solo",
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            project="test-project",
            task_name="solo",
        )
        test_db.add(run)
        await test_db.commit()

        service = RunService(test_db, mock_storage)
        progress = await service.get_run_progress("solo", None)

        assert progress.children_total == 0
        assert progress.children_last_update is None
        assert set(progress.children_by_state.values()) == {0}

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
