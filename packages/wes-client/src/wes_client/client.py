"""
Asynchronous WES client.

The client a long-lived service should use. Construct one per process, keep it
for the process lifetime, and close it on shutdown -- one client means one
connection pool, so calls reuse established connections instead of renegotiating
TCP and TLS on every request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from wes_schemas import (
    RunId,
    RunListResponse,
    RunLog,
    RunStatus,
    RunSummary,
    ServiceInfo,
    State,
    TaskListResponse,
    TaskLog,
)
from wes_client import _operations as ops
from wes_client._operations import Attachment, Operation
from wes_client._transport import API_PREFIX, parse, translate_transport_error
from wes_client._version import __version__

ModelT = TypeVar("ModelT", bound=BaseModel)

DEFAULT_USER_AGENT = f"wes-client/{__version__}"
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 30.0


class AsyncWesClient:
    """
    Asynchronous client for a GA4GH Workflow Execution Service.

    Args:
        base_url: The service root, without the GA4GH path prefix -- the prefix
            is this client's business, not the caller's. Required unless
            ``http_client`` is given.
        auth: Credential to attach to every request. See wes_client.auth.
        connect_timeout: Seconds to wait for a connection.
        read_timeout: Seconds to wait for a response. Higher than the connect
            timeout because run submission does real work before answering.
        http_client: A preconfigured httpx.AsyncClient to use instead of building
            one. Two uses: a caller that needs its own transport settings
            (proxies, TLS material, retries), and the contract tests, which pass
            a client wired to an httpx.ASGITransport so the whole client is
            exercised against the real WES app with no socket in between. A
            client supplied here is NOT closed by ``aclose`` -- whoever created it
            owns it.
        user_agent: Sent on every request. Worth setting per consumer; it is what
            makes WES's access logs attributable.

    Example:
        >>> client = AsyncWesClient("http://wes:8000", auth=ServiceKeyAuth(key))
        >>> runs = await client.on_behalf_of("alice").list_runs(project="P-1")
        >>> await client.aclose()
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        auth: httpx.Auth | None = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        http_client: httpx.AsyncClient | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if http_client is None and not base_url:
            raise ValueError("base_url is required unless http_client is provided")

        self._on_behalf_of: str | None = None

        if http_client is not None:
            self._http = http_client
            # Not ours to close. A view or a caller shutting down this wrapper
            # must not tear down a pool someone else is still using.
            self._owns_http = False
            return

        assert base_url is not None  # guarded above
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            auth=auth,
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=connect_timeout,
                pool=connect_timeout,
            ),
            headers={"User-Agent": user_agent},
        )
        self._owns_http = True

    # -- identity ---------------------------------------------------------

    def on_behalf_of(self, username: str | None) -> AsyncWesClient:
        """
        Return a view of this client that asserts an acting user to WES.

        A view, not a new client: it shares the underlying connection pool, so a
        service can serve concurrent requests for many different users without
        building a pool per user. Cheap enough to call per request.

        WES records the asserted identity for its audit trail and TRUSTS it
        without verification -- holding the service key is what earns that trust.
        It is therefore never an authorization input. Whether this user may see
        the runs being requested has to have been decided by the caller before
        getting here.

        Closing a view does not close the shared pool; close the client the view
        came from.
        """
        view = object.__new__(type(self))
        view.__dict__.update(self.__dict__)
        view._on_behalf_of = username.strip() if username else None
        view._owns_http = False
        return view

    # -- lifecycle --------------------------------------------------------

    async def aclose(self) -> None:
        """Close the connection pool, if this client owns it."""
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncWesClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # -- transport --------------------------------------------------------

    async def _send(self, op: Operation) -> Any:
        """
        Send one operation and return its parsed model.

        The single place where this client touches the network, so the mapping
        from transport failure to exception exists once.
        """
        headers = {"X-On-Behalf-Of": self._on_behalf_of} if self._on_behalf_of else None

        try:
            response = await self._http.request(
                op.method,
                f"{API_PREFIX}{op.path}",
                params=op.params or None,
                data=op.data or None,
                files=op.files or None,
                headers=headers,
            )
        except Exception as exc:
            raise translate_transport_error(exc) from exc

        return parse(response, op.model)

    # -- service ----------------------------------------------------------

    async def get_service_info(self) -> ServiceInfo:
        """Return the service's capabilities, supported workflow types, and state counts."""
        return await self._send(ops.get_service_info())

    # -- runs -------------------------------------------------------------

    async def list_runs(
        self,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        project: str | None = None,
        state: State | str | None = None,
        workflow_url: str | None = None,
        task_name: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> RunListResponse:
        """
        Return one page of workflow runs, newest first.

        Ordering is the service's and is not configurable.

        Args:
            page_size: Maximum runs to return. WES caps this at 100; asking for
                more returns 100.
            page_token: Continuation token from a previous response's
                ``next_page_token``. Opaque -- currently a stringified offset,
                but do not rely on that.
            project: Filter to one project. Uses WES's indexed ``project``
                column; prefer this over passing ProjectId in ``tags``.
            state: Filter to one workflow state.
            workflow_url: Filter to one workflow.
            task_name: Filter on the TaskName tag.
            tags: Filter on arbitrary tag key/value pairs.
        """
        return await self._send(
            ops.list_runs(
                page_size=page_size,
                page_token=page_token,
                project=project,
                state=state,
                workflow_url=workflow_url,
                task_name=task_name,
                tags=tags,
            )
        )

    async def iter_runs(
        self,
        *,
        page_size: int | None = None,
        project: str | None = None,
        state: State | str | None = None,
        workflow_url: str | None = None,
        task_name: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> AsyncIterator[RunSummary]:
        """
        Yield every matching run, following pagination.

        For callers that want all results rather than a page -- reconciliation
        jobs, CLI listings, exports. A UI should page explicitly with
        ``list_runs`` instead, so it does not hold a request open across an
        unbounded number of round trips.

        Stops on a missing or empty ``next_page_token``, and also stops if a page
        comes back empty, so a service that returned a stable non-empty token
        could not spin here forever.
        """
        token: str | None = None
        while True:
            page = await self.list_runs(
                page_size=page_size,
                page_token=token,
                project=project,
                state=state,
                workflow_url=workflow_url,
                task_name=task_name,
                tags=tags,
            )
            if not page.runs:
                return
            for run in page.runs:
                yield run
            if not page.next_page_token:
                return
            token = page.next_page_token

    async def submit_run(
        self,
        *,
        workflow_url: str,
        workflow_type: str,
        workflow_type_version: str,
        workflow_params: dict[str, Any] | str | None = None,
        tags: dict[str, str] | str | None = None,
        workflow_engine: str | None = None,
        workflow_engine_version: str | None = None,
        workflow_engine_parameters: dict[str, str] | str | None = None,
        attachments: Sequence[Attachment] | None = None,
    ) -> RunId:
        """
        Submit a workflow for execution and return its run id.

        Args:
            workflow_url: The workflow to run. Absolute URL, an engine-specific
                id, or a filename matching one of ``attachments``.
            workflow_type: Descriptor type, "CWL" or "WDL".
            workflow_type_version: Descriptor version, not the pipeline version.
            workflow_params: Workflow inputs. Passed as a dict and JSON-encoded
                for the wire.
            tags: Arbitrary key/value tags. NGS360 requires a ``ProjectId`` tag
                for a run to be attributable to a project.
            workflow_engine: Execution backend, e.g. "awshealthomics".
            workflow_engine_version: Backend version. Requires
                ``workflow_engine``.
            workflow_engine_parameters: Extra backend parameters.
            attachments: Files to upload with the run, as (filename, bytes).

        Returns:
            The new run's id.
        """
        return await self._send(
            ops.submit_run(
                workflow_url=workflow_url,
                workflow_type=workflow_type,
                workflow_type_version=workflow_type_version,
                workflow_params=workflow_params,
                tags=tags,
                workflow_engine=workflow_engine,
                workflow_engine_version=workflow_engine_version,
                workflow_engine_parameters=workflow_engine_parameters,
                attachments=attachments,
            )
        )

    async def get_run(self, run_id: str) -> RunLog:
        """Return a run's full record: request, state, logs, and outputs."""
        return await self._send(ops.get_run(run_id))

    async def get_run_status(self, run_id: str) -> RunStatus:
        """
        Return just a run's state.

        Cheaper than ``get_run``; use this for polling.
        """
        return await self._send(ops.get_run_status(run_id))

    async def cancel_run(self, run_id: str) -> RunId:
        """
        Cancel a run.

        Runs already in a terminal state cannot be canceled and the service
        rejects the attempt.
        """
        return await self._send(ops.cancel_run(run_id))

    # -- tasks ------------------------------------------------------------

    async def list_tasks(
        self,
        run_id: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> TaskListResponse:
        """Return one page of the tasks executed as part of a run."""
        return await self._send(ops.list_tasks(run_id, page_size=page_size, page_token=page_token))

    async def get_task(self, run_id: str, task_id: str) -> TaskLog:
        """Return one task's command, timing, exit code, and log URLs."""
        return await self._send(ops.get_task(run_id, task_id))
