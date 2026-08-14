"""
Request construction and response interpretation, shared by both clients.

Everything here is synchronous and I/O-free on purpose. The async and sync
clients are then identical except for the one line that actually sends the
request, so there is a single place where a status code becomes an exception and
a single place where a body becomes a model. Duplicating that logic across two
clients is how they drift.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from wes_client.errors import (
    WesProtocolError,
    WesTimeout,
    WesUnavailable,
    response_error,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

# GA4GH mounts the API under a fixed prefix. Callers configure the service root
# and this is appended, so no caller has to remember it.
API_PREFIX = "/ga4gh/wes/v1"

# Enough of a failing body to diagnose from, bounded so a stray HTML error page
# or an S3 redirect dump cannot flood the logs.
_BODY_EXCERPT = 500


def json_field(value: Any) -> str | None:
    """
    Encode a form field that WES expects as a JSON-encoded string.

    Several fields on the run-submission endpoint (workflow_params, tags,
    workflow_engine_parameters) are declared as form strings whose contents are
    JSON. Callers pass real dicts and this does the encoding, so the wire format
    stays inside the client instead of leaking into every call site.
    """
    if value is None:
        return None
    if isinstance(value, str):
        # Already encoded by the caller; pass it through rather than
        # double-encoding into a JSON string containing JSON.
        return value
    return json.dumps(value)


def translate_transport_error(exc: Exception) -> Exception:
    """
    Convert an httpx transport failure into this package's exception type.

    Timeouts are separated from other transport failures because they mean
    different things operationally: a timeout usually means the service is
    overloaded and still processing, while a connect failure means it is not
    reachable at all.
    """
    if isinstance(exc, httpx.TimeoutException):
        return WesTimeout(f"WES request timed out: {exc}")
    if isinstance(exc, httpx.RequestError):
        return WesUnavailable(f"WES request failed: {exc}")
    return exc


def _error_message(response: httpx.Response) -> str:
    """
    Pull the most useful message out of a failing response.

    WES sends two error shapes -- its own ErrorResponse (``msg``) from the
    exception handlers, and FastAPI's ``detail`` from HTTPException. Both are
    checked so the caller gets the service's actual message either way, with the
    raw body as a last resort when the response is not JSON at all.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text[:_BODY_EXCERPT].strip() or response.reason_phrase

    if isinstance(body, dict):
        for key in ("msg", "detail", "message"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
            # FastAPI validation errors put a list of per-field objects in
            # `detail`; rendering it beats reporting an empty message.
            if value:
                return json.dumps(value)[:_BODY_EXCERPT]

    return response.text[:_BODY_EXCERPT].strip() or response.reason_phrase


def check_status(response: httpx.Response) -> None:
    """
    Raise the appropriate WesResponseError if the response is not successful.

    Raises:
        WesResponseError: A subclass matching the status code.
    """
    if response.is_success:
        return

    raise response_error(
        response.status_code,
        _error_message(response),
        response.text[:_BODY_EXCERPT],
    )


def parse(response: httpx.Response, model: type[ModelT]) -> ModelT:
    """
    Validate a successful response body into the model the endpoint returns.

    Raises:
        WesResponseError: If the response was not successful.
        WesProtocolError: If the body is not JSON, or does not match the model.
            Both mean client and server disagree about the contract, which is a
            deployment or code defect rather than a caller error -- hence a
            distinct exception type from a 4xx.
    """
    check_status(response)

    try:
        payload = response.json()
    except ValueError as exc:
        raise WesProtocolError(
            f"WES returned a non-JSON body for {response.request.method} "
            f"{response.request.url}: {response.text[:_BODY_EXCERPT]!r}"
        ) from exc

    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise WesProtocolError(
            f"WES response did not match {model.__name__} for "
            f"{response.request.method} {response.request.url}: {exc}"
        ) from exc


def drop_none(params: dict[str, Any]) -> dict[str, Any]:
    """
    Remove unset query parameters.

    Sending ``page_token=None`` would put the literal string "None" on the wire
    and WES would treat it as a real token.
    """
    return {key: value for key, value in params.items() if value is not None}


def build_filters(
    *,
    project: str | None = None,
    state: Any = None,
    workflow_url: str | None = None,
    task_name: str | None = None,
    tags: dict[str, str] | None = None,
) -> str | None:
    """
    Build the JSON ``filters`` query parameter for ListRuns.

    WES takes its run filters as one JSON-encoded query parameter. Exposing that
    raw would make every caller reproduce the key names and the encoding, so the
    client takes keyword arguments and assembles it.

    ``project`` filters on WES's promoted, indexed ``project`` column. Passing
    the same value inside ``tags`` as ``ProjectId`` reaches the same rows but
    cannot use the (project, created_at) index, so prefer ``project``.

    Returns:
        The encoded filter string, or None when no filters were given, so the
        parameter is omitted entirely rather than sent as an empty object.
    """
    filters: dict[str, Any] = {}
    if project is not None:
        filters["project"] = project
    if state is not None:
        # Accepts a State enum or a bare string; enums carry a str value.
        filters["state"] = getattr(state, "value", state)
    if workflow_url is not None:
        filters["workflow_url"] = workflow_url
    if task_name is not None:
        filters["task_name"] = task_name
    if tags:
        filters["tags"] = tags

    return json.dumps(filters) if filters else None
