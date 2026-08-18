"""Tests for workflow runs endpoints."""

import io
import json
from fastapi.testclient import TestClient

from wes_service.db.models import WorkflowRun, WorkflowState

WORKFLOW_SUBMIT_PATCH = (
    'wes_service.services.workflow_submission_service'
    '.LambdaWorkflowSubmissionService.submit_workflow'
)


class TestPAMLFunctions:
    """Tests endpoint as PAML would do.."""

    async def test_paml_get_task_state(self, client: TestClient, test_db):
        """Test get task state through PAML"""
        # Mimic inputs of PAML get_task_state()
        task = {
            "id": "test-get-state"
        }

        # Mock run
        run = WorkflowRun(
            id=task["id"],
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="123456",
            tags={},
            user_id="test_user",
            project="test-project",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        # Verify task state
        response = client.get("/ga4gh/wes/v1/runs/"+task["id"]+"/status")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == task["id"]
        assert data["state"] == "COMPLETE"

    async def test_paml_get_task_output(self, client: TestClient, test_db):
        """Test getting specific task outputs as PAML would do."""
        # Mimic inputs of PAML get_task_output()
        task = {
            "id": "test-get-output"
        }
        output_name = "output1"

        # Mock run
        run = WorkflowRun(
            id=task["id"],
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="123456",
            outputs={
                "omics_run_id": "omics-runid-test",
                "output_location": "s3://bucket/output/",
                "output_mapping": {
                    "output1": "s3://bucket/output/output_file1",
                    "output2": "s3://bucket/output/output_file2",
                }
            },
            tags={},
            user_id="test_user",
            project="test-project",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs/"+task["id"]+'/')
        assert response.status_code == 200
        data = response.json()

        # Verify run output
        output_mapping = data["outputs"]["output_mapping"]
        result_file_output = output_mapping.get(output_name)
        assert result_file_output == "s3://bucket/output/output_file1"

        # Simulate PAML getting a non-existent output
        nonexistent_output = output_mapping.get("nonexistent")
        assert nonexistent_output is None

    async def test_paml_get_task_outputs(self, client: TestClient, test_db):
        """Test getting specific task outputs as PAML would do."""
        # Mimic inputs of PAML get_task_outputs()
        task = {
            "id": "test-get-outputs"
        }

        # Mock run
        run = WorkflowRun(
            id=task["id"],
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="123456",
            outputs={
                "omics_run_id": "omics-runid-test",
                "output_location": "s3://bucket/output/",
                "output_mapping": {
                    "output1": "s3://bucket/output/output_file1",
                    "output2": "s3://bucket/output/output_file2",
                    "output3": "s3://bucket/output/output_file3",
                }
            },
            tags={},
            user_id="test_user",
            project="test-project",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs/"+task["id"]+'/')
        assert response.status_code == 200
        data = response.json()

        # Verify run output
        output_mapping = data["outputs"]["output_mapping"]
        task_outputs = list(output_mapping.keys())
        assert task_outputs == ["output1", "output2", "output3"]

    async def test_paml_get_tasks_by_name(self, client: TestClient, test_db):
        """Test getting specific task outputs as PAML would do."""
        # Mimic inputs of PAML get_tasks_by_name()
        project = {
            "name": "test_project_name",
            "id": "test_project_id",
        }
        task_name = "test-get-task-name"

        # Mock runs
        run1 = WorkflowRun(
            id='test-get-task1',
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="123456",
            user_id="test_user",
            tags={
                "ProjectId": project["id"],
                "TaskName": task_name
            },
            project=project["id"],
            task_name=task_name,
        )
        test_db.add(run1)
        run2 = WorkflowRun(
            id='test-get-task2',
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="123456",
            user_id="test_user",
            tags={
                "ProjectId": "test-other-project-names",
                "TaskName": task_name
            },
            project="test-other-project-names",
            task_name=task_name,
        )
        test_db.add(run2)
        run3 = WorkflowRun(
            id='test-get-task3',
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="123456",
            user_id="test_user",
            tags={
                "ProjectId": project["id"],
                "TaskName": "test-other-task-names"
            },
            project=project["id"],
            task_name="test-other-task-names",
        )
        test_db.add(run3)
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs")
        assert response.status_code == 200
        data = response.json()

        # Verify runs and tasks
        assert "runs" in data
        assert isinstance(data["runs"], list)
        assert len(data["runs"]) == 3
        tasks = []
        for run in data["runs"]:
            if run["tags"]["ProjectId"] == project["id"]:
                if run["tags"]["TaskName"] == task_name:
                    tasks += [run]
        assert len(tasks) == 1
        assert tasks[0]["run_id"] == "test-get-task1"


class TestSubmitWorkflow:
    """Tests for POST /runs endpoint."""

    def test_submit_workflow_minimal(self, client: TestClient):
        """Test submitting a workflow with minimal parameters."""
        response = client.post(
            "/ga4gh/wes/v1/runs",
            data={
                "workflow_url": "https://example.com/workflow.cwl",
                "workflow_type": "CWL",
                "workflow_type_version": "v1.0",
                "tags": json.dumps({"ProjectId": "test_project"}),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert isinstance(data["run_id"], str)

    def test_submit_workflow_with_params(self, client: TestClient):
        """Test submitting a workflow with parameters."""
        params = {"input_file": "s3://bucket/input.txt"}

        response = client.post(
            "/ga4gh/wes/v1/runs",
            data={
                "workflow_url": "https://example.com/workflow.cwl",
                "workflow_type": "CWL",
                "workflow_type_version": "v1.0",
                "workflow_params": json.dumps(params),
                "tags": json.dumps({
                    "ProjectId": "test",
                    "TaskName": "example_workflow"
                }),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data

    def test_submit_workflow_with_attachments(self, client: TestClient):
        """Test submitting a workflow with file attachments."""
        files = [
            ("workflow_attachment", ("workflow.cwl", io.BytesIO(b"content1"))),
            ("workflow_attachment", ("inputs.json", io.BytesIO(b"content2"))),
        ]

        response = client.post(
            "/ga4gh/wes/v1/runs",
            data={
                "workflow_url": "workflow.cwl",
                "workflow_type": "CWL",
                "workflow_type_version": "v1.0",
                "tags": json.dumps({"ProjectId": "test_project"}),
            },
            files=files,
        )
        assert response.status_code == 200

    def test_submit_workflow_missing_required_field(self, client: TestClient):
        """Test submitting workflow without required fields."""
        response = client.post(
            "/ga4gh/wes/v1/runs",
            data={
                "workflow_type": "CWL",
                # Missing workflow_url and workflow_type_version
            },
        )
        assert response.status_code == 400


class TestListRuns:
    """Tests for GET /runs endpoint."""

    def test_list_runs_empty(self, client: TestClient):
        """Test listing runs when none exist."""
        response = client.get("/ga4gh/wes/v1/runs")
        assert response.status_code == 200
        data = response.json()
        assert "runs" in data
        assert isinstance(data["runs"], list)
        assert len(data["runs"]) == 0

    def test_list_runs_with_pagination(self, client: TestClient):
        """Test listing runs with pagination parameters."""
        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"page_size": 10, "page_token": "0"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "runs" in data
        assert "next_page_token" in data

    def test_list_runs_pagination_limit(self, client: TestClient):
        """Test pagination with maximum page size."""
        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"page_size": 1000},  # Should be capped at 100
        )
        assert response.status_code == 200

    async def test_list_runs_filter_by_tag(self, client: TestClient, test_db):
        """Test listing runs filtered by tags."""
        # Create test runs with different tags
        run1 = WorkflowRun(
            id="run1",
            state=WorkflowState.QUEUED,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow1.cwl",
            tags={"ProjectId": "test", "type": "A"},
            user_id="test_user",
            project="test",
            task_name="test-task-A",
        )
        test_db.add(run1)
        run2 = WorkflowRun(
            id="run2",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow2.cwl",
            tags={"ProjectId": "test", "type": "B"},
            user_id="test_user",
            project="test",
            task_name="test-task-B",
        )
        test_db.add(run2)
        run3 = WorkflowRun(
            id="run3",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow2.cwl",
            tags={"ProjectId": "another_test", "type": "B"},
            user_id="test_user",
            project="another_test",
            task_name="test-task-B",
        )
        test_db.add(run3)
        await test_db.commit()

        # Filter by tag type=A
        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"filters": json.dumps({"tags": {"type": "A"}})},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["run_id"] == "run1"

        # Filter by tag ProjectId=test
        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"filters": json.dumps({"tags": {"ProjectId": "test"}})},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["runs"]) == 2
        run_ids = {run["run_id"] for run in data["runs"]}
        assert run_ids == {"run1", "run2"}

        # Filter by 2 tags, ProjectId=test and type=B
        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"filters": json.dumps({"tags": {"ProjectId": "test", "type": "B"}})},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["run_id"] == "run2"

    async def test_list_runs_exposes_project_workflow_url_and_submitter(
        self,
        client: TestClient,
        test_db,
    ):
        """Summaries carry the fields a project workflow table renders."""
        run = WorkflowRun(
            id="run-summary-fields",
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="6b2d5fc97c0d41e4a2efc0cb4d8c4585:5",
            tags={"ProjectId": "P-20230314-0004", "TaskName": "sampleA"},
            user_id="chienm2",
            project="P-20230314-0004",
            task_name="sampleA",
        )
        test_db.add(run)
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs")
        assert response.status_code == 200
        summary = response.json()["runs"][0]

        assert summary["project"] == "P-20230314-0004"
        assert summary["submitted_by"] == "chienm2"
        assert summary["name"] == "sampleA"
        # The pipeline version rides on the workflow_url suffix; the descriptor
        # version (workflow_type_version) is a different thing entirely.
        assert summary["workflow_url"] == "6b2d5fc97c0d41e4a2efc0cb4d8c4585:5"

    async def test_list_runs_filter_by_project_column(
        self,
        client: TestClient,
        test_db,
    ):
        """The project column is filterable directly, not just via tags.ProjectId."""
        for run_id, project in (("in-project", "P-1"), ("other-project", "P-2")):
            test_db.add(
                WorkflowRun(
                    id=run_id,
                    state=WorkflowState.RUNNING,
                    workflow_type="CWL",
                    workflow_type_version="v1.0",
                    workflow_url="wf-1",
                    tags={"ProjectId": project},
                    user_id="test_user",
                    project=project,
                    task_name=run_id,
                )
            )
        await test_db.commit()

        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"filters": json.dumps({"project": "P-1"})},
        )
        assert response.status_code == 200
        data = response.json()
        assert [run["run_id"] for run in data["runs"]] == ["in-project"]

    async def test_list_runs_total_count_spans_every_page(
        self,
        client: TestClient,
        test_db,
    ):
        """total_count counts all matching runs, not just the page returned."""
        for index in range(5):
            test_db.add(
                WorkflowRun(
                    id=f"counted-{index}",
                    state=WorkflowState.RUNNING,
                    workflow_type="CWL",
                    workflow_type_version="v1.0",
                    workflow_url="wf-1",
                    tags={"ProjectId": "P-1"},
                    user_id="test_user",
                    project="P-1",
                    task_name=f"task-{index}",
                )
            )
        await test_db.commit()

        first = client.get("/ga4gh/wes/v1/runs", params={"page_size": 2}).json()
        assert len(first["runs"]) == 2
        assert first["total_count"] == 5

        # The total is stable as the client pages, so a page count computed from
        # it does not shift underneath the table.
        last = client.get(
            "/ga4gh/wes/v1/runs",
            params={"page_size": 2, "page_token": first["next_page_token"]},
        ).json()
        assert last["total_count"] == 5

    async def test_list_runs_total_count_reflects_filters(
        self,
        client: TestClient,
        test_db,
    ):
        """The count is of the filtered set, not the whole table."""
        for run_id, project in (("a", "P-1"), ("b", "P-1"), ("c", "P-2")):
            test_db.add(
                WorkflowRun(
                    id=run_id,
                    state=WorkflowState.RUNNING,
                    workflow_type="CWL",
                    workflow_type_version="v1.0",
                    workflow_url="wf-1",
                    tags={"ProjectId": project},
                    user_id="test_user",
                    project=project,
                    task_name=run_id,
                )
            )
        await test_db.commit()

        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"filters": json.dumps({"project": "P-1"})},
        )
        assert response.status_code == 200
        assert response.json()["total_count"] == 2

    async def test_list_runs_total_count_is_zero_when_nothing_matches(
        self,
        client: TestClient,
        test_db,
    ):
        """An empty project reports 0 rather than omitting the count."""
        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"filters": json.dumps({"project": "P-does-not-exist"})},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["runs"] == []
        assert data["total_count"] == 0


class TestGetRunStatus:
    """Tests for GET /runs/{run_id}/status endpoint."""

    def test_get_run_status_not_found(self, client: TestClient):
        """Test getting status of non-existent run."""
        response = client.get("/ga4gh/wes/v1/runs/nonexistent/status")
        assert response.status_code == 404

    async def test_get_run_status_success(
        self,
        client: TestClient,
        test_db,
    ):
        """Test getting status of existing run."""
        # Create a test run
        run = WorkflowRun(
            id="test-run-123",
            state=WorkflowState.QUEUED,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            user_id="test_user",
            project="test-project",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs/test-run-123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "test-run-123"
        assert data["state"] == "QUEUED"


class TestGetRunLog:
    """Tests for GET /runs/{run_id} endpoint."""

    def test_get_run_log_not_found(self, client: TestClient):
        """Test getting log of non-existent run."""
        response = client.get("/ga4gh/wes/v1/runs/nonexistent")
        assert response.status_code == 404

    async def test_get_run_log_success(self, client: TestClient, test_db):
        """Test getting log of existing run."""
        run = WorkflowRun(
            id="test-run-456",
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            workflow_params={"input": "value"},
            tags={"ProjectId": "test"},
            user_id="test_user",
            project="test",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs/test-run-456")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "test-run-456"
        assert data["state"] == "COMPLETE"
        assert "request" in data
        assert data["request"]["workflow_type"] == "CWL"


class TestLauncherLineage:
    """Tests for parent/child runs and GET /runs/{run_id}/progress."""

    def test_submit_child_run_with_parent_run_id_tag(self, client: TestClient):
        """A ParentRunId tag on submission links the child to its launcher."""
        parent = client.post(
            "/ga4gh/wes/v1/runs",
            data={
                "workflow_url": "LAUNCHER:1.0.0",
                "workflow_type": "CWL",
                "workflow_type_version": "v1.0",
                "workflow_engine": "awsbatch",
                "tags": json.dumps({"ProjectId": "P-1", "TaskName": "launcher"}),
            },
        )
        assert parent.status_code == 200
        parent_id = parent.json()["run_id"]

        child = client.post(
            "/ga4gh/wes/v1/runs",
            data={
                "workflow_url": "https://example.com/workflow.cwl",
                "workflow_type": "CWL",
                "workflow_type_version": "v1.0",
                "tags": json.dumps(
                    {"ProjectId": "P-1", "TaskName": "sampleA", "ParentRunId": parent_id}
                ),
            },
        )
        assert child.status_code == 200
        child_id = child.json()["run_id"]

        run_log = client.get(f"/ga4gh/wes/v1/runs/{child_id}")
        assert run_log.status_code == 200
        assert run_log.json()["parent_run_id"] == parent_id

    def test_submit_child_run_with_unknown_parent_is_rejected(self, client: TestClient):
        """A ParentRunId naming no run is a client error, not a 500."""
        response = client.post(
            "/ga4gh/wes/v1/runs",
            data={
                "workflow_url": "https://example.com/workflow.cwl",
                "workflow_type": "CWL",
                "workflow_type_version": "v1.0",
                "tags": json.dumps({"ProjectId": "P-1", "ParentRunId": "no-such-run"}),
            },
        )
        assert response.status_code == 400
        # The error handler renders every HTTPException as ErrorResponse, so the
        # message the caller sees lives in `msg`, not FastAPI's `detail`.
        assert "ParentRunId" in response.json()["msg"]

    def test_submit_run_with_unsupported_engine_is_rejected(self, client: TestClient):
        """
        An engine service-info does not advertise is a 400 naming the ones it does.

        Previously a misspelled launcher engine was accepted and dispatched to
        HealthOmics, which failed later with a message about a service the caller
        never asked for.
        """
        response = client.post(
            "/ga4gh/wes/v1/runs",
            data={
                "workflow_url": "https://example.com/workflow.cwl",
                "workflow_type": "CWL",
                "workflow_type_version": "v1.0",
                "workflow_engine": "aws-batch",
                "tags": json.dumps({"ProjectId": "P-1"}),
            },
        )
        assert response.status_code == 400
        msg = response.json()["msg"]
        assert "aws-batch" in msg
        assert "awsbatch" in msg and "awshealthomics" in msg

    def test_service_info_advertises_the_engines_runs_may_use(self, client: TestClient):
        """
        What service-info advertises is exactly what POST /runs accepts.

        The spec makes service-info the discovery mechanism for workflow_engine,
        so a client that reads it and submits what it found must not be rejected.
        """
        engines = client.get("/ga4gh/wes/v1/service-info").json()[
            "workflow_engine_versions"
        ]

        for engine in engines:
            response = client.post(
                "/ga4gh/wes/v1/runs",
                data={
                    "workflow_url": "https://example.com/workflow.cwl",
                    "workflow_type": "CWL",
                    "workflow_type_version": "v1.0",
                    "workflow_engine": engine,
                    "tags": json.dumps({"ProjectId": "P-1"}),
                },
            )
            assert response.status_code == 200, engine

    async def test_list_runs_filter_by_parent_run_id(self, client: TestClient, test_db):
        """?filters={"parent_run_id": …} returns only that launcher's children."""
        runs = [
            WorkflowRun(
                id="launcher-x",
                state=WorkflowState.RUNNING,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="LAUNCHER:1.0.0",
                tags={"ProjectId": "P-1"},
                user_id="test_user",
                project="P-1",
                task_name="launcher-x",
            ),
            WorkflowRun(
                id="x-child-1",
                state=WorkflowState.QUEUED,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                tags={"ProjectId": "P-1"},
                user_id="test_user",
                project="P-1",
                task_name="sampleA",
                parent_run_id="launcher-x",
            ),
            WorkflowRun(
                id="unrelated",
                state=WorkflowState.QUEUED,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                tags={"ProjectId": "P-1"},
                user_id="test_user",
                project="P-1",
                task_name="sampleB",
            ),
        ]
        for run in runs:
            test_db.add(run)
        await test_db.commit()

        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"filters": json.dumps({"parent_run_id": "launcher-x"})},
        )
        assert response.status_code == 200
        data = response.json()
        assert [run["run_id"] for run in data["runs"]] == ["x-child-1"]
        assert data["total_count"] == 1

    async def test_get_run_progress(self, client: TestClient, test_db):
        """Progress reports the launcher's own state and its children by state."""
        parent = WorkflowRun(
            id="launcher-y",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="LAUNCHER:1.0.0",
            tags={"ProjectId": "P-1"},
            user_id="test_user",
            project="P-1",
            task_name="launcher-y",
        )
        test_db.add(parent)
        for index, state in enumerate(
            [WorkflowState.COMPLETE, WorkflowState.RUNNING, WorkflowState.EXECUTOR_ERROR]
        ):
            test_db.add(
                WorkflowRun(
                    id=f"y-child-{index}",
                    state=state,
                    workflow_type="CWL",
                    workflow_type_version="v1.0",
                    workflow_url="https://example.com/workflow.cwl",
                    tags={"ProjectId": "P-1"},
                    user_id="test_user",
                    project="P-1",
                    task_name=f"sample-{index}",
                    parent_run_id="launcher-y",
                )
            )
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs/launcher-y/progress")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "launcher-y"
        assert data["state"] == "RUNNING"
        assert data["children_total"] == 3
        assert data["children_by_state"]["COMPLETE"] == 1
        assert data["children_by_state"]["RUNNING"] == 1
        assert data["children_by_state"]["EXECUTOR_ERROR"] == 1
        assert data["children_by_state"]["QUEUED"] == 0

    def test_get_run_progress_not_found(self, client: TestClient):
        """Progress for a run that does not exist is a 404."""
        response = client.get("/ga4gh/wes/v1/runs/nonexistent/progress")
        assert response.status_code == 404


class TestCancelRun:
    """Tests for POST /runs/{run_id}/cancel endpoint."""

    def test_cancel_run_not_found(self, client: TestClient):
        """Test canceling non-existent run."""
        response = client.post("/ga4gh/wes/v1/runs/nonexistent/cancel")
        assert response.status_code == 404

    async def test_cancel_run_success(self, client: TestClient, test_db):
        """Test canceling a running workflow."""
        run = WorkflowRun(
            id="test-run-789",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            user_id="test_user",
            project="test-project",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        response = client.post("/ga4gh/wes/v1/runs/test-run-789/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "test-run-789"

        # Verify state changed - need to re-query from a fresh session
        test_db.expire(run)
        await test_db.refresh(run)
        assert run.state == WorkflowState.CANCELING

    async def test_cancel_completed_run(self, client: TestClient, test_db):
        """Test that completed runs cannot be canceled."""
        run = WorkflowRun(
            id="test-run-complete",
            state=WorkflowState.COMPLETE,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            user_id="test_user",
            project="test-project",
            task_name="test-task",
        )
        test_db.add(run)
        await test_db.commit()

        response = client.post("/ga4gh/wes/v1/runs/test-run-complete/cancel")
        assert response.status_code == 400
