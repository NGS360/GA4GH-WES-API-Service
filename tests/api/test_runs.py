"""Tests for workflow runs endpoints."""

import io
import json
from fastapi.testclient import TestClient

from src.wes_service.db.models import WorkflowRun, WorkflowState


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
