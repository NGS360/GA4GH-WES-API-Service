"""Tests for workflow runs endpoints."""

import io
import json
from fastapi.testclient import TestClient

from src.wes_service.db.models import WorkflowRun, WorkflowState


class TestPAMLFunctions:
    """Tests endpoint as PAML would do.."""

    async def test_paml_submit_task(self, client: TestClient):
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

        # Mock run
        workflow_engine_parameters = {
            "cacheId": execution_settings["cacheId"],
            "name": name
        }
        tags = {
            "Name": name,
            "Project": project["name"],
        }
        response = client.post(
            "/ga4gh/wes/v1/runs",
            data={
                "workflow_url": workflow,
                "workflow_type": "CWL",
                "workflow_type_version": "v1.0",
                "workflow_params": json.dumps(parameters),
                "workflow_engine_parameters": json.dumps(workflow_engine_parameters),
                "tags": json.dumps(tags),
            },
        )

        # Verify run was created correctly and added to db
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert isinstance(data["run_id"], str)

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
            user_id="test_user"
        )
        test_db.add(run)
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs/"+task["id"]+'/')
        assert response.status_code == 200
        data = response.json()

        # Verify run output
        output_mapping = data["outputs"]["output_mapping"]
        result_file_output = output_mapping.get("output1")
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
            user_id="test_user"
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
                "Project": "test_project_name",
                "Name": "test-get-task-name"
            }
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
                "Project": "test-other-project-names",
                "Name": "test-get-task-name"
            }
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
                "Project": "test_project_name",
                "Name": "test-other-task-names"
            }
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
             if (run["tags"]["Project"] == "test_project_name"
                 and run["tags"]["Name"] == "test-get-task-name"):
                tasks+=[run]
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
                    "project": "test",
                    "name": "example_workflow"
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
            tags={"project": "test"},
            user_id="test_user",
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
        )
        test_db.add(run)
        await test_db.commit()

        response = client.post("/ga4gh/wes/v1/runs/test-run-complete/cancel")
        assert response.status_code == 400
