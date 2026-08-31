"""Tests for the internal callback endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from wes_service.db.models import WorkflowRun, WorkflowState

CALLBACK_KEY = "callback-key-for-the-lambda"
SERVICE_KEY = "service-key-for-apiserver"
EXECUTOR_CALLBACK_URL = "/ga4gh/wes/v1/internal/callbacks/executor-state-change"


@pytest.fixture
def callback_settings():
    """
    Configure both internal credentials for the executor callback.

    The auth dependency reads settings directly rather than through FastAPI's
    dependency injection, so the app fixture's settings override does not reach
    it -- patching where it looks is what makes these tests independent of the
    developer's environment.
    """
    with patch("wes_service.core.callback_auth.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.enable_callback_endpoint = True
        settings.enable_service_auth = True
        settings.INTERNAL_CALLBACK_API_KEY = CALLBACK_KEY
        settings.INTERNAL_SERVICE_API_KEY = SERVICE_KEY
        yield settings


@pytest.fixture
async def launcher_run(test_db):
    """A QUEUED launcher run waiting to be told what its Batch job is doing."""
    run = WorkflowRun(
        id="launcher-run-1",
        state=WorkflowState.QUEUED,
        workflow_type="CWL",
        workflow_type_version="v1.0",
        workflow_url="LAUNCHER:1.0.0",
        workflow_engine="awsbatch",
        tags={"ProjectId": "P-1"},
        user_id="test_user",
        project="P-1",
        task_name="launcher",
        system_logs=[],
    )
    test_db.add(run)
    await test_db.commit()
    return run


def _payload(**overrides) -> dict:
    """A Batch job state change report."""
    return {
        "wes_run_id": "launcher-run-1",
        "executor": "awsbatch",
        "status": "RUNNING",
        "executor_run_id": "batch-job-abc123",
        "event_time": "2024-01-15T14:00:00Z",
        "event_id": "evt-1",
        **overrides,
    }


class TestExecutorStateChangeAuth:
    """The endpoint is shared by two callers holding two different secrets."""

    async def test_accepts_the_callback_key(
        self, client: TestClient, callback_settings, launcher_run
    ):
        """The relay Lambda's key is accepted."""
        response = client.post(
            EXECUTOR_CALLBACK_URL,
            json=_payload(),
            headers={"X-Internal-API-Key": CALLBACK_KEY},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["previous_state"] == "QUEUED"
        assert body["new_state"] == "RUNNING"

    async def test_accepts_the_service_key(
        self, client: TestClient, callback_settings, launcher_run
    ):
        """APIServer's key is accepted, because it is what knows the job ID."""
        response = client.post(
            EXECUTOR_CALLBACK_URL,
            json=_payload(status="STARTING", event_id="evt-2"),
            headers={"X-Internal-Service-Key": SERVICE_KEY},
        )

        assert response.status_code == 200
        assert response.json()["new_state"] == "INITIALIZING"

    async def test_rejects_a_wrong_key(
        self, client: TestClient, callback_settings, launcher_run
    ):
        """A wrong key is a 403 whichever header it arrives in."""
        for headers in (
            {"X-Internal-API-Key": "wrong"},
            {"X-Internal-Service-Key": "wrong"},
            {"X-Internal-API-Key": SERVICE_KEY},  # right key, wrong header
        ):
            response = client.post(EXECUTOR_CALLBACK_URL, json=_payload(), headers=headers)
            assert response.status_code == 403, headers

    async def test_rejects_no_credentials(
        self, client: TestClient, callback_settings, launcher_run
    ):
        """An unauthenticated call cannot move a run's state."""
        response = client.post(EXECUTOR_CALLBACK_URL, json=_payload())

        assert response.status_code == 403

    async def test_disabled_endpoint_reports_503(
        self, client: TestClient, callback_settings, launcher_run
    ):
        """A deployment with callbacks turned off says so, rather than 403."""
        callback_settings.enable_callback_endpoint = False

        response = client.post(
            EXECUTOR_CALLBACK_URL,
            json=_payload(),
            headers={"X-Internal-API-Key": CALLBACK_KEY},
        )

        assert response.status_code == 503


class TestExecutorStateChangeBehaviour:
    """End-to-end behaviour of the route, on top of the service-level tests."""

    async def test_binds_the_executor_job_id(
        self, client: TestClient, callback_settings, launcher_run, test_db
    ):
        """The reported job ID lands on the run, which is the operator's join key."""
        response = client.post(
            EXECUTOR_CALLBACK_URL,
            json=_payload(),
            headers={"X-Internal-API-Key": CALLBACK_KEY},
        )
        assert response.status_code == 200

        test_db.expire(launcher_run)
        await test_db.refresh(launcher_run)
        assert launcher_run.workflow_run_id == "batch-job-abc123"
        assert launcher_run.state == WorkflowState.RUNNING

    async def test_unknown_run_is_404(self, client: TestClient, callback_settings):
        """Reporting state for a run this service does not have is a 404."""
        response = client.post(
            EXECUTOR_CALLBACK_URL,
            json=_payload(wes_run_id="no-such-run"),
            headers={"X-Internal-API-Key": CALLBACK_KEY},
        )

        assert response.status_code == 404

    async def test_unknown_executor_is_400(
        self, client: TestClient, callback_settings, launcher_run
    ):
        """An executor with no status vocabulary is rejected as a client error."""
        response = client.post(
            EXECUTOR_CALLBACK_URL,
            json=_payload(executor="slurm"),
            headers={"X-Internal-API-Key": CALLBACK_KEY},
        )

        assert response.status_code == 400
        assert "Unknown executor" in response.json()["msg"]
