"""Integration tests for complete workflow lifecycle."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from wes_service.db.models import WorkflowRun, WorkflowState


@pytest.mark.integration
class TestWorkflowLifecycle:
    """Integration tests for complete workflow execution lifecycle."""

    async def test_complete_workflow_lifecycle(self, client: TestClient, test_db):
        """Test submitting, monitoring, and completing a workflow."""
        # Mock the workflow submission service to avoid real API calls
        with patch(
            'wes_service.api.routes.runs.get_submission_service'
        ) as mock_factory:
            # Create mock instance with async support
            mock_instance = MagicMock()

            # Make submit_workflow return a coroutine that resolves to the expected value
            async def mock_submit_workflow(run, db):
                return {
                    "omics_run_id": "mock-omics-123",
                    "statusCode": 200
                }
            mock_instance.submit_workflow = mock_submit_workflow
            mock_factory.return_value = mock_instance

            # 1. Submit workflow
            response = client.post(
                "/ga4gh/wes/v1/runs",
                data={
                    "workflow_url": "https://example.com/workflow.cwl",
                    "workflow_type": "CWL",
                    "workflow_type_version": "v1.0",
                    "workflow_params": '{"input": "test.txt"}',
                    "tags": '{"ProjectId": "test_project", "env": "test", "user": "tester"}',
                },
            )
            assert response.status_code == 200
            run_id = response.json()["run_id"]

        # 2. Check run appears in list
        response = client.get("/ga4gh/wes/v1/runs")
        assert response.status_code == 200
        runs = response.json()["runs"]
        assert any(run["run_id"] == run_id for run in runs)

        # 3. Get run status
        response = client.get(f"/ga4gh/wes/v1/runs/{run_id}/status")
        assert response.status_code == 200
        status = response.json()
        assert status["run_id"] == run_id
        assert status["state"] == "QUEUED"

        # 4. Get full run log
        response = client.get(f"/ga4gh/wes/v1/runs/{run_id}")
        assert response.status_code == 200
        log = response.json()
        assert log["run_id"] == run_id
        assert log["request"]["workflow_type"] == "CWL"
        assert log["request"]["workflow_params"]["input"] == "test.txt"

        # 5. Simulate workflow execution (normally done by daemon)
        run = await test_db.get(WorkflowRun, run_id)
        run.state = WorkflowState.RUNNING
        await test_db.commit()

        response = client.get(f"/ga4gh/wes/v1/runs/{run_id}/status")
        assert response.json()["state"] == "RUNNING"

        # 6. Cancel the workflow
        response = client.post(f"/ga4gh/wes/v1/runs/{run_id}/cancel")
        assert response.status_code == 200

        # 7. Verify it's canceling
        response = client.get(f"/ga4gh/wes/v1/runs/{run_id}/status")
        assert response.json()["state"] == "CANCELING"

    def test_workflow_with_multiple_tasks(self, client: TestClient, test_db):
        """Test workflow with multiple task logs."""
        # Mock the workflow submission service
        with patch(
            'wes_service.api.routes.runs.get_submission_service'
        ) as mock_factory:
            mock_instance = MagicMock()

            # Make submit_workflow return a coroutine that resolves to the expected value
            async def mock_submit_workflow(run, db):
                return {
                    "omics_run_id": "mock-omics-456",
                    "statusCode": 200
                }
            mock_instance.submit_workflow = mock_submit_workflow
            mock_factory.return_value = mock_instance

            # Submit workflow
            response = client.post(
                "/ga4gh/wes/v1/runs",
                data={
                    "workflow_url": "https://example.com/workflow.cwl",
                    "workflow_type": "CWL",
                    "workflow_type_version": "v1.0",
                    "tags": '{"ProjectId": "test_project"}',
                },
            )
            run_id = response.json()["run_id"]

        # Add some tasks (simulating daemon execution)
        from wes_service.db.models import TaskLog

        for i in range(3):
            task = TaskLog(
                id=f"task-{i}",
                run_id=run_id,
                name=f"Step {i+1}",
                cmd=["echo", f"step{i}"],
            )
            test_db.add(task)
        test_db.commit()

        # List tasks
        response = client.get(f"/ga4gh/wes/v1/runs/{run_id}/tasks")
        assert response.status_code == 200
        tasks = response.json()["task_logs"]
        assert len(tasks) == 3

        # Get individual task
        response = client.get(f"/ga4gh/wes/v1/runs/{run_id}/tasks/task-0")
        assert response.status_code == 200
        task = response.json()
        assert task["name"] == "Step 1"

    def test_pagination_workflow(self, client: TestClient):
        """Test pagination across multiple workflow runs."""
        # Mock the workflow submission service
        with patch(
            'wes_service.api.routes.runs.get_submission_service'
        ) as mock_factory:
            mock_instance = MagicMock()

            # Make submit_workflow return a coroutine that resolves to the expected value
            async def mock_submit_workflow(run, db):
                return {
                    "omics_run_id": "mock-omics-789",
                    "statusCode": 200
                }
            mock_instance.submit_workflow = mock_submit_workflow
            mock_factory.return_value = mock_instance

            # Submit multiple workflows
            run_ids = []
            for i in range(15):
                response = client.post(
                    "/ga4gh/wes/v1/runs",
                    data={
                        "workflow_url": f"https://example.com/workflow-{i}.cwl",
                        "workflow_type": "CWL",
                        "workflow_type_version": "v1.0",
                        "tags": f'{{"ProjectId": "test_project", "batch": "{i//5}"}}',
                    },
                )
                run_ids.append(response.json()["run_id"])

        # Get first page
        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={"page_size": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["runs"]) == 5
        assert data["next_page_token"] != ""

        # Get second page
        response = client.get(
            "/ga4gh/wes/v1/runs",
            params={
                "page_size": 5,
                "page_token": data["next_page_token"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["runs"]) == 5

    async def test_launcher_lifecycle_with_children(self, client: TestClient):
        """
        A launcher run and the three runs it submits, driven the way production will.

        The submission *factory* is left real, so the launcher genuinely takes
        the external-dispatch path and is left QUEUED for its submitter; only
        the children's HealthOmics call is stubbed out. State then arrives only
        through the executor callback, the same path EventBridge and APIServer
        use.
        """
        callback_key = "integration-callback-key"
        with (
            patch("wes_service.core.callback_auth.get_settings") as mock_settings,
            patch(
                "wes_service.services.workflow_submission_service"
                ".LambdaWorkflowSubmissionService.submit_workflow",
                new=AsyncMock(return_value={"omics_run_id": "mock-omics", "statusCode": 200}),
            ),
        ):
            settings = mock_settings.return_value
            settings.enable_callback_endpoint = True
            settings.enable_service_auth = False
            settings.INTERNAL_CALLBACK_API_KEY = callback_key
            headers = {"X-Internal-API-Key": callback_key}

            # 1. The launcher itself. No AWS call is made for it, and it stays
            #    QUEUED until whoever submits the Batch job reports back.
            response = client.post(
                "/ga4gh/wes/v1/runs",
                data={
                    "workflow_url": "RNASEQ-LAUNCHER:2.4.0",
                    "workflow_type": "CWL",
                    "workflow_type_version": "v1.0",
                    "workflow_engine": "awsbatch",
                    "workflow_params": '{"reference_model": "GRCh38"}',
                    "tags": '{"ProjectId": "P-1", "TaskName": "rnaseq-launcher"}',
                },
            )
            assert response.status_code == 200
            parent_id = response.json()["run_id"]
            assert client.get(f"/ga4gh/wes/v1/runs/{parent_id}/status").json()["state"] == "QUEUED"

            progress = client.get(f"/ga4gh/wes/v1/runs/{parent_id}/progress").json()
            assert progress["children_total"] == 0

            # 2. The Batch job starts, reported by the relay Lambda.
            response = client.post(
                "/ga4gh/wes/v1/internal/callbacks/executor-state-change",
                json={
                    "wes_run_id": parent_id,
                    "executor": "awsbatch",
                    "status": "RUNNING",
                    "executor_run_id": "batch-job-1",
                    "event_time": "2024-01-15T14:00:00Z",
                    "event_id": "evt-parent-running",
                    "log_urls": {"log_stream_name": "launcher/default/stream-1"},
                },
                headers=headers,
            )
            assert response.status_code == 200

            run_log = client.get(f"/ga4gh/wes/v1/runs/{parent_id}").json()
            assert run_log["state"] == "RUNNING"
            assert run_log["run_log"]["stdout"].startswith("https://")

            # 3. The launcher fans out, tagging each child with its own run id.
            child_ids = []
            for sample in ("sampleA", "sampleB", "sampleC"):
                response = client.post(
                    "/ga4gh/wes/v1/runs",
                    data={
                        "workflow_url": "https://example.com/rnaseq.cwl",
                        "workflow_type": "CWL",
                        "workflow_type_version": "v1.0",
                        "workflow_engine": "awshealthomics",
                        "tags": (
                            '{"ProjectId": "P-1", "TaskName": "' + sample + '", '
                            '"ParentRunId": "' + parent_id + '"}'
                        ),
                    },
                )
                assert response.status_code == 200
                child_ids.append(response.json()["run_id"])

            progress = client.get(f"/ga4gh/wes/v1/runs/{parent_id}/progress").json()
            assert progress["state"] == "RUNNING"
            assert progress["children_total"] == 3
            assert progress["children_by_state"]["QUEUED"] == 3

            # Listing by parent is how the launcher rediscovers its own work
            # after a restart.
            listed = client.get(
                "/ga4gh/wes/v1/runs",
                params={"filters": '{"parent_run_id": "' + parent_id + '"}'},
            ).json()
            assert sorted(run["run_id"] for run in listed["runs"]) == sorted(child_ids)

            # 4. The children run; two finish, one fails. Reported through the
            #    same generic callback with the Omics status vocabulary.
            for index, (child_id, final_status) in enumerate(
                zip(child_ids, ("COMPLETED", "COMPLETED", "FAILED"))
            ):
                for stage, status_name in enumerate(("RUNNING", final_status)):
                    response = client.post(
                        "/ga4gh/wes/v1/internal/callbacks/executor-state-change",
                        json={
                            "wes_run_id": child_id,
                            "executor": "omics",
                            "status": status_name,
                            "executor_run_id": f"omics-{index}",
                            "event_time": "2024-01-15T15:00:00Z",
                            "event_id": f"evt-child-{index}-{stage}",
                        },
                        headers=headers,
                    )
                    assert response.status_code == 200

            progress = client.get(f"/ga4gh/wes/v1/runs/{parent_id}/progress").json()
            assert progress["children_by_state"]["COMPLETE"] == 2
            assert progress["children_by_state"]["EXECUTOR_ERROR"] == 1
            assert progress["children_last_update"] is not None

            # 5. The launcher's Batch job ends. Its own state is its own: a
            #    failed child does not make the launcher fail, and vice versa.
            response = client.post(
                "/ga4gh/wes/v1/internal/callbacks/executor-state-change",
                json={
                    "wes_run_id": parent_id,
                    "executor": "awsbatch",
                    "status": "SUCCEEDED",
                    "event_time": "2024-01-15T16:00:00Z",
                    "event_id": "evt-parent-done",
                },
                headers=headers,
            )
            assert response.status_code == 200

            progress = client.get(f"/ga4gh/wes/v1/runs/{parent_id}/progress").json()
            assert progress["state"] == "COMPLETE"
            assert progress["children_by_state"]["EXECUTOR_ERROR"] == 1

    async def test_service_info_reflects_system_state(
        self,
        client: TestClient,
        test_db,
    ):
        """Test that service info reflects current system state."""
        # Create runs in different states
        from wes_service.db.models import WorkflowRun

        for i in range(2):
            run = WorkflowRun(
                id=f"queued-{i}",
                state=WorkflowState.QUEUED,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                tags={},
                project="test-project",
                task_name=f"test-task-queued-{i}",
            )
            test_db.add(run)

        for i in range(3):
            run = WorkflowRun(
                id=f"complete-{i}",
                state=WorkflowState.COMPLETE,
                workflow_type="CWL",
                workflow_type_version="v1.0",
                workflow_url="https://example.com/workflow.cwl",
                tags={},
                project="test-project",
                task_name=f"test-task-complete-{i}",
            )
            test_db.add(run)
        await test_db.commit()

        # Check service info
        response = client.get("/ga4gh/wes/v1/service-info")
        assert response.status_code == 200
        counts = response.json()["system_state_counts"]

        assert counts["QUEUED"] == 2
        assert counts["COMPLETE"] == 3
        assert counts["RUNNING"] == 0
