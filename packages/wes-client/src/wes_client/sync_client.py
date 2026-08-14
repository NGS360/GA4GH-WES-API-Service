"""
Synchronous WES client.

For the CLI and for ordinary scripts, where an event loop would be pure
ceremony. It is a real synchronous implementation over httpx.Client rather than
``asyncio.run`` wrapped around the async client -- that approach would build and
tear down an event loop and a connection pool on every call, and would raise
outright if called from code that already has a loop running.

The two clients duplicate their method signatures and nothing else: request
construction lives in _operations, and response interpretation in _transport, so
both go through the same logic.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import httpx

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
from wes_client.client import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_USER_AGENT,
)


class WesClient:
    """
    Synchronous client for a GA4GH Workflow Execution Service.

    Same surface as AsyncWesClient without the awaits. See that class for what
    the arguments mean.

    Example:
        >>> with WesClient("http://localhost:8000", auth=BasicAuth("u", "p")) as client:
        ...     for run in client.iter_runs(project="P-1"):
        ...         print(run.run_id, run.state)
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        auth: httpx.Auth | None = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        http_client: httpx.Client | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if http_client is None and not base_url:
            raise ValueError("base_url is required unless http_client is provided")

        self._on_behalf_of: str | None = None

        if http_client is not None:
            self._http = http_client
            self._owns_http = False
            return

        assert base_url is not None  # guarded above
        self._http = httpx.Client(
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

    def on_behalf_of(self, username: str | None) -> WesClient:
        """
        Return a view of this client that asserts an acting user to WES.

        See AsyncWesClient.on_behalf_of; the identity is trusted for audit only
        and is never an authorization input.
        """
        view = object.__new__(type(self))
        view.__dict__.update(self.__dict__)
        view._on_behalf_of = username.strip() if username else None
        view._owns_http = False
        return view

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        """Close the connection pool, if this client owns it."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> WesClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- transport --------------------------------------------------------

    def _send(self, op: Operation) -> Any:
        """Send one operation and return its parsed model."""
        headers = {"X-On-Behalf-Of": self._on_behalf_of} if self._on_behalf_of else None

        try:
            response = self._http.request(
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

    def get_service_info(self) -> ServiceInfo:
        """Return the service's capabilities, supported workflow types, and state counts."""
        return self._send(ops.get_service_info())

    # -- runs -------------------------------------------------------------

    def list_runs(
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
        """Return one page of workflow runs, newest first. See AsyncWesClient.list_runs."""
        return self._send(
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

    def iter_runs(
        self,
        *,
        page_size: int | None = None,
        project: str | None = None,
        state: State | str | None = None,
        workflow_url: str | None = None,
        task_name: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> Iterator[RunSummary]:
        """Yield every matching run, following pagination. See AsyncWesClient.iter_runs."""
        token: str | None = None
        while True:
            page = self.list_runs(
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
            yield from page.runs
            if not page.next_page_token:
                return
            token = page.next_page_token

    def submit_run(
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
        """Submit a workflow for execution. See AsyncWesClient.submit_run."""
        return self._send(
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

    def get_run(self, run_id: str) -> RunLog:
        """Return a run's full record: request, state, logs, and outputs."""
        return self._send(ops.get_run(run_id))

    def get_run_status(self, run_id: str) -> RunStatus:
        """Return just a run's state. Cheaper than get_run; use this for polling."""
        return self._send(ops.get_run_status(run_id))

    def cancel_run(self, run_id: str) -> RunId:
        """Cancel a run. Runs in a terminal state cannot be canceled."""
        return self._send(ops.cancel_run(run_id))

    # -- tasks ------------------------------------------------------------

    def list_tasks(
        self,
        run_id: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> TaskListResponse:
        """Return one page of the tasks executed as part of a run."""
        return self._send(ops.list_tasks(run_id, page_size=page_size, page_token=page_token))

    def get_task(self, run_id: str, task_id: str) -> TaskLog:
        """Return one task's command, timing, exit code, and log URLs."""
        return self._send(ops.get_task(run_id, task_id))
