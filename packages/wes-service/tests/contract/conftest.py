"""
Fixtures that run the client against the real server, with no socket.

httpx.ASGITransport hands requests straight to the FastAPI app in-process, so
these tests exercise the whole stack the client depends on -- routing, form
parsing, dependency injection, response models, error handlers -- while staying
as fast as a unit test.

This is why the client accepts an injected http_client. Mocking the transport
would only prove the client agrees with the mock; here it has to agree with the
server, which is the thing that can actually break.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from wes_client import AsyncWesClient, WesClient


@pytest.fixture
async def asgi_http(app: Any) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An httpx client wired directly to the WES app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://wes.test") as http:
        yield http


@pytest.fixture
async def wes(asgi_http: httpx.AsyncClient) -> AsyncWesClient:
    """An AsyncWesClient talking to the real app."""
    return AsyncWesClient(http_client=asgi_http)


@pytest.fixture
def sync_wes(client: TestClient) -> WesClient:
    """
    A synchronous WesClient talking to the real app, covering the CLI's path.

    Starlette's TestClient is itself an httpx.Client whose transport drives the
    ASGI app from a worker thread, so it drops straight into the same injection
    point the async client uses.
    """
    return WesClient(http_client=client)


@pytest.fixture
def no_lambda_submit() -> Any:
    """
    Stop run submission from reaching AWS.

    The route fires LambdaWorkflowSubmissionService after persisting a run and
    swallows its failures, so leaving it unpatched would still pass -- but it
    would make these tests depend on boto3's retry timings. Patched to keep them
    hermetic and fast.
    """
    target = (
        "wes_service.services.workflow_submission_service"
        ".LambdaWorkflowSubmissionService.submit_workflow"
    )
    with patch(target, new_callable=AsyncMock) as mock:
        mock.return_value = {"omics_run_id": "omics-test-1"}
        yield mock
