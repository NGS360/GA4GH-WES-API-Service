"""Tests for task endpoints."""

from fastapi.testclient import TestClient

from src.wes_service.db.models import TaskLog, WorkflowRun, WorkflowState


class TestListTasks:
    """Tests for GET /runs/{run_id}/tasks endpoint."""

    def test_list_tasks_run_not_found(self, client: TestClient):
        """Test listing tasks for non-existent run."""
        response = client.get("/ga4gh/wes/v1/runs/nonexistent/tasks")
        assert response.status_code == 404

    async def test_list_tasks_empty(self, client: TestClient, test_db):
        """Test listing tasks when none exist."""
        run = WorkflowRun(
            id="test-run-no-tasks",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            user_id="test_user",
        )
        test_db.add(run)
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs/test-run-no-tasks/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "task_logs" in data
        assert len(data["task_logs"]) == 0
        assert data["next_page_token"] == ""

    async def test_list_tasks_with_data(self, client: TestClient, test_db):
        """Test listing tasks with data."""
        run = WorkflowRun(
            id="test-run-with-tasks",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            user_id="test_user",
        )
        test_db.add(run)
        await test_db.commit()

        # Add tasks
        task1 = TaskLog(
            id="task-1",
            run_id="test-run-with-tasks",
            name="Download inputs",
            cmd=["wget", "http://example.com/input.txt"],
        )
        task2 = TaskLog(
            id="task-2",
            run_id="test-run-with-tasks",
            name="Process data",
            cmd=["python", "process.py"],
        )
        test_db.add(task1)
        test_db.add(task2)
        await test_db.commit()

        response = client.get("/ga4gh/wes/v1/runs/test-run-with-tasks/tasks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["task_logs"]) == 2
        assert data["task_logs"][0]["id"] == "task-1"
        assert data["task_logs"][1]["id"] == "task-2"

    async def test_list_tasks_with_pagination(self, client: TestClient, test_db):
        """Test listing tasks with pagination."""
        run = WorkflowRun(
            id="test-run-paginated",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            user_id="test_user",
        )
        test_db.add(run)
        await test_db.commit()

        # Add multiple tasks
        for i in range(5):
            task = TaskLog(
                id=f"task-{i}",
                run_id="test-run-paginated",
                name=f"Task {i}",
                cmd=["echo", f"{i}"],
            )
            test_db.add(task)
        await test_db.commit()

        # Request with page size
        response = client.get(
            "/ga4gh/wes/v1/runs/test-run-paginated/tasks",
            params={"page_size": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["task_logs"]) == 2
        assert data["next_page_token"] != ""


class TestGetTask:
    """Tests for GET /runs/{run_id}/tasks/{task_id} endpoint."""

    def test_get_task_run_not_found(self, client: TestClient):
        """Test getting task for non-existent run."""
        response = client.get(
            "/ga4gh/wes/v1/runs/nonexistent/tasks/task-1"
        )
        assert response.status_code == 404

    async def test_get_task_not_found(self, client: TestClient, test_db):
        """Test getting non-existent task."""
        run = WorkflowRun(
            id="test-run-task",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            user_id="test_user",
        )
        test_db.add(run)
        await test_db.commit()

        response = client.get(
            "/ga4gh/wes/v1/runs/test-run-task/tasks/nonexistent"
        )
        assert response.status_code == 404

    async def test_get_task_success(self, client: TestClient, test_db):
        """Test getting existing task."""
        run = WorkflowRun(
            id="test-run-get-task",
            state=WorkflowState.RUNNING,
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_url="https://example.com/workflow.cwl",
            tags={},
            user_id="test_user",
        )
        test_db.add(run)
        await test_db.commit()

        task = TaskLog(
            id="task-detail",
            run_id="test-run-get-task",
            name="Test Task",
            cmd=["echo", "hello"],
            exit_code=0,
            stdout_url="file:///tmp/stdout.txt",
            stderr_url="file:///tmp/stderr.txt",
        )
        test_db.add(task)
        await test_db.commit()

        response = client.get(
            "/ga4gh/wes/v1/runs/test-run-get-task/tasks/task-detail"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "task-detail"
        assert data["name"] == "Test Task"
        assert data["cmd"] == ["echo", "hello"]
        assert data["exit_code"] == 0
        assert data["stdout"] == "file:///tmp/stdout.txt"