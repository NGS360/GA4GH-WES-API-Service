"""
The WES operations, described as data.

Each function here says what one endpoint looks like on the wire -- method, path,
parameters, and the model it returns -- without performing any I/O. The async and
sync clients both build their requests from these, so there is exactly one
definition of "where does ListRuns live and what does it return", and adding an
endpoint means adding it here plus two delegating methods rather than writing the
request twice.

The clients still declare explicit typed signatures rather than forwarding
**kwargs. That repeats the parameter names, but it is what makes the client
usable from an editor and type-checkable by callers, and mypy catches a signature
that drifts from the operation it delegates to.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel

from wes_schemas import (
    CallbackResponse,
    RunId,
    RunListResponse,
    RunLog,
    RunProgress,
    RunStatus,
    ServiceInfo,
    State,
    TaskListResponse,
    TaskLog,
)
from wes_client._transport import build_filters, drop_none, json_field

# A file to attach to a run submission: (filename, content).
Attachment = tuple[str, bytes]


@dataclass(frozen=True)
class Operation:
    """One WES call, fully described and not yet sent."""

    method: str
    path: str
    model: type[BaseModel]
    params: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    files: list[tuple[str, tuple[str, bytes]]] = field(default_factory=list)
    # A JSON request body, for the endpoints that take one. Distinct from
    # ``data``, which is the form encoding RunWorkflow requires -- the two are
    # mutually exclusive on one request.
    json_body: dict[str, Any] | None = None


def _segment(value: str) -> str:
    """
    Escape a value being interpolated into the URL path.

    Run and task ids come from the service, but they also come from user input on
    the CLI and from route parameters in APIServer. An unescaped id containing a
    slash or a question mark would silently address a different endpoint.
    """
    return quote(value, safe="")


def get_service_info() -> Operation:
    return Operation("GET", "/service-info", ServiceInfo)


def list_runs(
    *,
    page_size: int | None = None,
    page_token: str | None = None,
    project: str | None = None,
    state: State | str | None = None,
    workflow_url: str | None = None,
    task_name: str | None = None,
    parent_run_id: str | None = None,
    tags: dict[str, str] | None = None,
) -> Operation:
    return Operation(
        "GET",
        "/runs",
        RunListResponse,
        params=drop_none(
            {
                "page_size": page_size,
                "page_token": page_token,
                "filters": build_filters(
                    project=project,
                    state=state,
                    workflow_url=workflow_url,
                    task_name=task_name,
                    parent_run_id=parent_run_id,
                    tags=tags,
                ),
            }
        ),
    )


def submit_run(
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
) -> Operation:
    """
    Describe a RunWorkflow submission.

    WES takes this as a form body in which several fields are JSON-encoded
    strings. Callers pass real dicts for those and the encoding happens here, so
    the wire representation does not leak into calling code.
    """
    return Operation(
        "POST",
        "/runs",
        RunId,
        data=drop_none(
            {
                "workflow_url": workflow_url,
                "workflow_type": workflow_type,
                "workflow_type_version": workflow_type_version,
                "workflow_params": json_field(workflow_params),
                "tags": json_field(tags),
                "workflow_engine": workflow_engine,
                "workflow_engine_version": workflow_engine_version,
                "workflow_engine_parameters": json_field(workflow_engine_parameters),
            }
        ),
        files=[("workflow_attachment", (name, content)) for name, content in (attachments or ())],
    )


def get_run(run_id: str) -> Operation:
    return Operation("GET", f"/runs/{_segment(run_id)}", RunLog)


def get_run_status(run_id: str) -> Operation:
    return Operation("GET", f"/runs/{_segment(run_id)}/status", RunStatus)


def get_run_progress(run_id: str) -> Operation:
    return Operation("GET", f"/runs/{_segment(run_id)}/progress", RunProgress)


def cancel_run(run_id: str) -> Operation:
    return Operation("POST", f"/runs/{_segment(run_id)}/cancel", RunId)


def report_executor_state(
    *,
    wes_run_id: str,
    executor: str,
    status: str,
    event_time: datetime | str,
    executor_run_id: str | None = None,
    status_message: str | None = None,
    failure_reason: str | None = None,
    exit_code: int | None = None,
    event_id: str | None = None,
    log_urls: dict[str, Any] | None = None,
) -> Operation:
    """
    Describe a state report to WES's internal executor callback.

    Inbound-only for most consumers: the caller here is whatever submitted the
    job -- NGS360 APIServer for launcher containers on AWS Batch -- reporting the
    executor's job id, its status, and where its logs are. Requires an internal
    credential (ServiceKeyAuth), not a user token.
    """
    return Operation(
        "POST",
        "/internal/callbacks/executor-state-change",
        CallbackResponse,
        json_body=drop_none(
            {
                "wes_run_id": wes_run_id,
                "executor": executor,
                "status": status,
                "event_time": (
                    event_time.isoformat()
                    if isinstance(event_time, datetime)
                    else event_time
                ),
                "executor_run_id": executor_run_id,
                "status_message": status_message,
                "failure_reason": failure_reason,
                "exit_code": exit_code,
                "event_id": event_id,
                "log_urls": log_urls,
            }
        ),
    )


def list_tasks(
    run_id: str,
    *,
    page_size: int | None = None,
    page_token: str | None = None,
) -> Operation:
    return Operation(
        "GET",
        f"/runs/{_segment(run_id)}/tasks",
        TaskListResponse,
        params=drop_none({"page_size": page_size, "page_token": page_token}),
    )


def get_task(run_id: str, task_id: str) -> Operation:
    return Operation("GET", f"/runs/{_segment(run_id)}/tasks/{_segment(task_id)}", TaskLog)
