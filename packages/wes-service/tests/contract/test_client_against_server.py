"""
Functional contract tests: the client driving the real server.

Every test here goes through routing, form or query parsing, the service layer,
the response model, and back through the client's parsing -- so they fail if
either side of the contract moves. Complements test_operation_coverage.py, which
checks the shapes agree statically; these check the calls actually work.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from wes_client import AsyncWesClient, State, WesBadRequest, WesClient, WesNotFound

PROJECT = "P-CONTRACT-1"


async def _submit(wes: AsyncWesClient, **overrides: Any) -> str:
    """Submit a minimal valid run and return its id."""
    params: dict[str, Any] = {
        "workflow_url": "wf-contract-test",
        "workflow_type": "CWL",
        "workflow_type_version": "v1.0",
        "tags": {"ProjectId": PROJECT, "TaskName": "contract-test"},
        "workflow_params": {"input_file": "s3://bucket/sample.fastq"},
    }
    params.update(overrides)
    return (await wes.submit_run(**params)).run_id


class TestServiceInfo:
    """GetServiceInfo, the simplest full round trip."""

    async def test_returns_parsed_service_info(self, wes: AsyncWesClient) -> None:
        info = await wes.get_service_info()

        # Parsing into ServiceInfo is itself the assertion: a shape change on the
        # server would raise WesProtocolError before reaching here.
        assert info.workflow_type_versions
        assert info.supported_wes_versions


class TestRunSubmission:
    """
    RunWorkflow, the endpoint most likely to break in a hand-written client.

    It takes a form body with JSON-encoded string fields and an optional file
    array. These tests pin down that the client's encoding is what the server's
    Form and File parameters actually accept -- both with and without
    attachments, because those take different code paths in httpx (urlencoded
    versus multipart).
    """

    async def test_submits_without_attachments(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        run_id = await _submit(wes)
        assert run_id

    async def test_submits_with_attachments(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        run_id = await _submit(
            wes,
            attachments=[
                ("workflow.cwl", b"cwlVersion: v1.0\nclass: Workflow\n"),
                ("inputs.json", b'{"x": 1}'),
            ],
        )
        assert run_id

    async def test_dict_fields_survive_the_round_trip(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        """
        Dicts passed for JSON-encoded form fields come back as dicts.

        This is the client's main ergonomic promise on this endpoint -- callers
        pass real dicts and never see the wire encoding. If the encoding were
        wrong the values would come back as strings, or double-encoded.
        """
        run_id = await _submit(wes)

        run = await wes.get_run(run_id)
        assert run.request.workflow_params == {"input_file": "s3://bucket/sample.fastq"}
        assert run.request.tags == {"ProjectId": PROJECT, "TaskName": "contract-test"}

    async def test_engine_parameters_are_encoded(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        run_id = await _submit(
            wes,
            workflow_engine="awshealthomics",
            workflow_engine_parameters={"priority": "high"},
        )

        run = await wes.get_run(run_id)
        assert run.request.workflow_engine == "awshealthomics"

        # Compared by subset, not equality: the server derives an `outputUri`
        # from the ProjectId tag and adds it to the engine parameters. Asserting
        # equality here would make this test fail whenever the server adds
        # another derived parameter, which is not a client concern.
        assert run.request.workflow_engine_parameters is not None
        assert run.request.workflow_engine_parameters["priority"] == "high"


class TestRunRetrieval:
    """GetRunLog and GetRunStatus."""

    async def test_get_run_returns_the_submitted_request(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        run_id = await _submit(wes)

        run = await wes.get_run(run_id)
        assert run.run_id == run_id
        assert run.request.workflow_url == "wf-contract-test"
        assert run.request.workflow_type == "CWL"

    async def test_get_run_status_returns_a_known_state(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        run_id = await _submit(wes)

        status = await wes.get_run_status(run_id)
        assert status.run_id == run_id
        # Parsed into the enum, not left as a string -- so a state the client does
        # not know about is caught here rather than downstream.
        assert isinstance(status.state, State)

    async def test_missing_run_raises_not_found(self, wes: AsyncWesClient) -> None:
        """
        A 404 arrives as WesNotFound, not as a generic error.

        This is the distinction consumers branch on, so it needs to survive the
        real server's error handling rather than only a mock's.
        """
        with pytest.raises(WesNotFound) as caught:
            await wes.get_run("no-such-run")

        assert caught.value.status_code == 404
        # The service's own message is preserved, not replaced with a placeholder.
        assert caught.value.message
        assert "not found" in caught.value.message.lower()

    async def test_errors_use_the_single_error_shape(
        self, asgi_http: httpx.AsyncClient
    ) -> None:
        """
        Errors are ErrorResponse, including those raised as HTTPException.

        Checked on the raw response rather than through the client, because the
        client understands both the old and the new shape by design -- so only a
        direct look at the body can catch the server regressing to FastAPI's
        `detail`. That regression would silently make the OpenAPI error
        declarations untrue.
        """
        response = await asgi_http.get("/ga4gh/wes/v1/runs/no-such-run")

        assert response.status_code == 404
        body = response.json()
        assert set(body) == {"msg", "status_code"}
        assert body["status_code"] == 404


class TestRunListing:
    """
    ListRuns, including the filter encoding.

    The client builds WES's JSON `filters` query parameter from keyword
    arguments. These tests confirm the encoding is one the server actually
    parses -- a silently ignored filter would otherwise look like "no runs
    matched" or, worse, like every run matching.
    """

    async def test_lists_a_submitted_run(self, wes: AsyncWesClient, no_lambda_submit: Any) -> None:
        run_id = await _submit(wes)

        page = await wes.list_runs(page_size=10)
        assert run_id in {run.run_id for run in page.runs}

    async def test_project_filter_selects(self, wes: AsyncWesClient, no_lambda_submit: Any) -> None:
        run_id = await _submit(wes)

        page = await wes.list_runs(project=PROJECT)
        assert run_id in {run.run_id for run in page.runs}

    async def test_project_filter_excludes(self, wes: AsyncWesClient, no_lambda_submit: Any) -> None:
        """
        A filter that should match nothing matches nothing.

        Without this, a filter the server ignored entirely would still pass
        test_project_filter_selects.
        """
        await _submit(wes)

        page = await wes.list_runs(project="P-DOES-NOT-EXIST")
        assert page.runs == []

    async def test_task_name_filter(self, wes: AsyncWesClient, no_lambda_submit: Any) -> None:
        run_id = await _submit(wes)

        matched = await wes.list_runs(task_name="contract-test")
        assert run_id in {run.run_id for run in matched.runs}
        assert not (await wes.list_runs(task_name="some-other-task")).runs

    async def test_state_filter_accepts_enum_and_string(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        run_id = await _submit(wes)
        state = (await wes.get_run_status(run_id)).state
        assert state is not None

        by_enum = await wes.list_runs(state=state)
        by_string = await wes.list_runs(state=state.value)
        assert {run.run_id for run in by_enum.runs} == {run.run_id for run in by_string.runs}
        assert run_id in {run.run_id for run in by_enum.runs}

    async def test_iter_runs_yields_every_match_across_pages(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        """
        Pagination is followed, with a page size small enough to force several pages.

        Exercises the client's token handling against the server's real tokens
        rather than tokens a mock invented.
        """
        submitted = {await _submit(wes) for _ in range(5)}

        seen = [run.run_id async for run in wes.iter_runs(page_size=2, project=PROJECT)]

        assert submitted <= set(seen)
        # No run yielded twice -- an off-by-one in token handling would duplicate.
        assert len(seen) == len(set(seen))


class TestRunCancellation:
    """CancelRun."""

    async def test_cancels_a_run(self, wes: AsyncWesClient, no_lambda_submit: Any) -> None:
        run_id = await _submit(wes)

        canceled = await wes.cancel_run(run_id)
        assert canceled.run_id == run_id

        assert (await wes.get_run_status(run_id)).state in (State.CANCELED, State.CANCELING)


class TestTasks:
    """ListTasks and GetTask."""

    async def test_lists_tasks_for_a_run(self, wes: AsyncWesClient, no_lambda_submit: Any) -> None:
        run_id = await _submit(wes)

        # A freshly submitted run has no tasks yet; parsing an empty page is
        # still a contract check, and is the shape the UI sees most often.
        response = await wes.list_tasks(run_id)
        assert response.task_logs == []

    async def test_missing_task_raises_not_found(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        run_id = await _submit(wes)

        with pytest.raises(WesNotFound):
            await wes.get_task(run_id, "no-such-task")


class TestLauncherLineage:
    """GetRunProgress, the parent filter, and the executor callback."""

    async def test_progress_counts_the_children_of_a_launcher(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        parent_id = await _submit(wes, workflow_engine="awsbatch")
        for sample in ("sampleA", "sampleB"):
            await _submit(
                wes,
                tags={"ProjectId": PROJECT, "TaskName": sample, "ParentRunId": parent_id},
            )

        progress = await wes.get_run_progress(parent_id)

        assert progress.run_id == parent_id
        assert progress.children_total == 2
        assert progress.children_by_state["QUEUED"] == 2
        # The launcher's own state is reported, not an aggregate of the children.
        assert progress.state is State.QUEUED

    async def test_parent_filter_selects_only_that_launchers_children(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        parent_id = await _submit(wes, workflow_engine="awsbatch")
        child_id = await _submit(
            wes, tags={"ProjectId": PROJECT, "TaskName": "child", "ParentRunId": parent_id}
        )
        await _submit(wes, tags={"ProjectId": PROJECT, "TaskName": "unrelated"})

        page = await wes.list_runs(parent_run_id=parent_id)

        assert [run.run_id for run in page.runs] == [child_id]
        assert page.runs[0].tags["ParentRunId"] == parent_id

    async def test_report_executor_state_moves_the_run(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        """
        The whole submitter-side path: bind the job id, then report its state.

        The callback auth dependency reads settings directly, so it is patched
        here; everything else -- routing, the status vocabulary, the state
        machine -- is the real thing.
        """
        run_id = await _submit(wes, workflow_engine="awsbatch")

        with patch("wes_service.core.callback_auth.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.enable_callback_endpoint = True
            settings.enable_service_auth = True
            settings.INTERNAL_CALLBACK_API_KEY = ""
            settings.INTERNAL_SERVICE_API_KEY = "contract-service-key"
            wes._http.headers["X-Internal-Service-Key"] = "contract-service-key"

            response = await wes.report_executor_state(
                wes_run_id=run_id,
                executor="awsbatch",
                status="RUNNING",
                executor_run_id="batch-job-contract-1",
                event_time=datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC),
                event_id="evt-contract-1",
            )

        assert response.success is True
        assert response.new_state == "RUNNING"
        assert (await wes.get_run_status(run_id)).state is State.RUNNING

    async def test_report_executor_state_rejects_an_unknown_executor(
        self, wes: AsyncWesClient, no_lambda_submit: Any
    ) -> None:
        """A bad executor name comes back as a client error the client can catch."""
        run_id = await _submit(wes, workflow_engine="awsbatch")

        with patch("wes_service.core.callback_auth.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.enable_callback_endpoint = True
            settings.enable_service_auth = True
            settings.INTERNAL_CALLBACK_API_KEY = ""
            settings.INTERNAL_SERVICE_API_KEY = "contract-service-key"
            wes._http.headers["X-Internal-Service-Key"] = "contract-service-key"

            with pytest.raises(WesBadRequest):
                await wes.report_executor_state(
                    wes_run_id=run_id,
                    executor="slurm",
                    status="RUNNING",
                    event_time=datetime(2024, 1, 15, 14, 0, 0, tzinfo=UTC),
                )


class TestIdentityAssertion:
    """X-On-Behalf-Of, and the view semantics around it."""

    async def test_on_behalf_of_reaches_the_server(self, wes: AsyncWesClient) -> None:
        """The asserted identity is sent, and the server accepts the request with it."""
        view = wes.on_behalf_of("alice")

        # The test app overrides authentication, so what this proves is that the
        # header is well-formed and does not break the request. That the server
        # honours it is covered by tests/core/test_security.py.
        assert (await view.get_service_info()).workflow_type_versions

    async def test_view_shares_the_parent_pool(self, wes: AsyncWesClient) -> None:
        view = wes.on_behalf_of("alice")
        assert view._http is wes._http

    async def test_view_does_not_close_the_shared_pool(self, wes: AsyncWesClient) -> None:
        """
        Closing a view must leave the parent usable.

        A view that closed the shared pool would break every other in-flight
        request in a service that creates one view per user request.
        """
        view = wes.on_behalf_of("alice")
        await view.aclose()

        assert (await wes.get_service_info()).workflow_type_versions

    async def test_parent_identity_is_unchanged_by_a_view(self, wes: AsyncWesClient) -> None:
        wes.on_behalf_of("alice")
        assert wes._on_behalf_of is None


class TestSyncClient:
    """
    The synchronous client, over the same app.

    The CLI runs on this path, so it needs the same coverage as the async client
    rather than being assumed equivalent.
    """

    def test_service_info(self, sync_wes: WesClient) -> None:
        assert sync_wes.get_service_info().workflow_type_versions

    def test_submit_and_get(self, sync_wes: WesClient, no_lambda_submit: Any) -> None:
        run_id = sync_wes.submit_run(
            workflow_url="wf-sync-test",
            workflow_type="CWL",
            workflow_type_version="v1.0",
            tags={"ProjectId": PROJECT},
        ).run_id

        assert sync_wes.get_run(run_id).request.workflow_url == "wf-sync-test"

    def test_iter_runs(self, sync_wes: WesClient, no_lambda_submit: Any) -> None:
        run_id = sync_wes.submit_run(
            workflow_url="wf-sync-iter",
            workflow_type="CWL",
            workflow_type_version="v1.0",
            tags={"ProjectId": PROJECT},
        ).run_id

        assert run_id in {run.run_id for run in sync_wes.iter_runs(page_size=2, project=PROJECT)}

    def test_missing_run_raises_not_found(self, sync_wes: WesClient) -> None:
        with pytest.raises(WesNotFound):
            sync_wes.get_run("no-such-run")
