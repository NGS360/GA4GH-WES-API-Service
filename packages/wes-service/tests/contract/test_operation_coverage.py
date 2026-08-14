"""
Structural contract tests: does the client still describe this server?

This is the drift detection that a generated client would have given us for free.
Rather than regenerate code from the OpenAPI document, we assert the hand-written
operations agree with it -- so renaming a route, or changing what it returns,
fails here in the server's own CI instead of surfacing as a 502 in NGS360
APIServer after deploy.

Three directions, each catching a different mistake:

1. Every client operation points at a route the server actually serves.
   Catches a server route being renamed or removed.
2. Every route the server serves has a client operation.
   Catches a new endpoint shipping without client support.
3. Every operation parses into the model the server declares it returns.
   Catches a response model being swapped without the client following.
"""

from __future__ import annotations

import re

import pytest

from wes_client import _operations as ops
from wes_client._operations import Operation
from wes_client._transport import API_PREFIX
from wes_service.main import create_app

# Sentinels distinctive enough that substituting them back into path templates
# cannot collide with a literal path segment.
RUN_ID = "run-id-sentinel"
TASK_ID = "task-id-sentinel"

# Every operation the client exposes, paired with the path template it should
# resolve to on the server. Adding a client method means adding a row here; that
# is deliberate, because a method nobody asserted against the spec is a method
# nobody has checked.
OPERATIONS: list[tuple[str, Operation, str]] = [
    ("get_service_info", ops.get_service_info(), "/service-info"),
    ("list_runs", ops.list_runs(), "/runs"),
    (
        "submit_run",
        ops.submit_run(
            workflow_url="wf-1",
            workflow_type="CWL",
            workflow_type_version="v1.0",
        ),
        "/runs",
    ),
    ("get_run", ops.get_run(RUN_ID), "/runs/{run_id}"),
    ("get_run_status", ops.get_run_status(RUN_ID), "/runs/{run_id}/status"),
    ("cancel_run", ops.cancel_run(RUN_ID), "/runs/{run_id}/cancel"),
    ("list_tasks", ops.list_tasks(RUN_ID), "/runs/{run_id}/tasks"),
    ("get_task", ops.get_task(RUN_ID, TASK_ID), "/runs/{run_id}/tasks/{task_id}"),
]

# Server paths with no client operation, and why. Anything not listed here must
# be covered by the client, so a new endpoint cannot be added silently.
UNCLIENTED_PATHS = {
    # Called by an AWS Lambda reacting to EventBridge, not by any Python
    # consumer of this package. Giving it a client method would advertise an
    # inbound-only endpoint as something callers should use.
    f"{API_PREFIX}/internal/callbacks/omics-state-change",
    f"{API_PREFIX}/internal/callbacks/health",
}


@pytest.fixture(scope="module")
def spec() -> dict:
    """The server's own OpenAPI document -- the thing being agreed with."""
    return create_app().openapi()


def _as_template(path: str) -> str:
    """Turn a concrete operation path back into the server's path template."""
    return path.replace(RUN_ID, "{run_id}").replace(TASK_ID, "{task_id}")


@pytest.mark.parametrize(
    ("name", "op", "template"),
    OPERATIONS,
    ids=[name for name, _, _ in OPERATIONS],
)
def test_operation_targets_a_real_route(name: str, op: Operation, template: str, spec: dict) -> None:
    """Each operation's method and path exist in the server's OpenAPI document."""
    assert _as_template(op.path) == template, (
        f"{name} builds path {op.path!r}, which does not match its declared template"
    )

    full_path = f"{API_PREFIX}{template}"
    assert full_path in spec["paths"], (
        f"{name} targets {full_path}, which this server does not serve. "
        f"Served paths: {sorted(spec['paths'])}"
    )
    assert op.method.lower() in spec["paths"][full_path], (
        f"{name} uses {op.method} {full_path}, but the server only accepts "
        f"{sorted(spec['paths'][full_path])}"
    )


@pytest.mark.parametrize(
    ("name", "op", "template"),
    OPERATIONS,
    ids=[name for name, _, _ in OPERATIONS],
)
def test_operation_parses_the_declared_response_model(
    name: str, op: Operation, template: str, spec: dict
) -> None:
    """
    Each operation parses into the schema the server says that route returns.

    Compared by schema name rather than by walking the whole JSON Schema: the
    models are literally the same class objects on both sides, so agreeing on the
    name is sufficient. What this catches is a route's response_model being
    changed to a different class without the client's Operation following.
    """
    operation_spec = spec["paths"][f"{API_PREFIX}{template}"][op.method.lower()]
    schema = operation_spec["responses"]["200"]["content"]["application/json"]["schema"]

    ref = schema.get("$ref")
    assert ref is not None, f"{name}: server route declares an inline schema, expected a $ref"

    server_model = ref.rsplit("/", 1)[-1]
    assert server_model == op.model.__name__, (
        f"{name} parses into {op.model.__name__}, but the server returns {server_model}"
    )


def test_every_server_route_has_a_client_operation(spec: dict) -> None:
    """
    No WES endpoint is reachable only by hand-rolling HTTP.

    Fails when an endpoint is added to the server without a client method, which
    is the moment a consumer would otherwise start bypassing this package.
    """
    served = {
        path
        for path in spec["paths"]
        # Only the WES API surface. /healthcheck and / are operational endpoints,
        # not part of the contract this client implements.
        if path.startswith(API_PREFIX)
    }
    covered = {f"{API_PREFIX}{template}" for _, _, template in OPERATIONS}

    uncovered = served - covered - UNCLIENTED_PATHS
    assert not uncovered, (
        f"Server routes with no client operation: {sorted(uncovered)}. "
        "Add an operation in wes_client._operations and a row in OPERATIONS, or "
        "record the path in UNCLIENTED_PATHS with a reason."
    )


def test_uncliented_paths_still_exist(spec: dict) -> None:
    """
    The exemption list does not outlive the routes it exempts.

    Without this, a deleted endpoint leaves a stale entry that would silently
    exempt a future endpoint reusing the same path.
    """
    stale = {path for path in UNCLIENTED_PATHS if path not in spec["paths"]}
    assert not stale, f"UNCLIENTED_PATHS lists paths the server no longer serves: {sorted(stale)}"


@pytest.mark.parametrize(
    ("name", "op", "template"),
    OPERATIONS,
    ids=[name for name, _, _ in OPERATIONS],
)
def test_error_responses_are_declared_as_error_response(
    name: str, op: Operation, template: str, spec: dict
) -> None:
    """
    Every declared error status returns ErrorResponse.

    The service has one error shape, so the document should say so on every route.
    A route declaring some other model, or FastAPI's default `detail` shape, means
    the two have drifted.
    """
    operation_spec = spec["paths"][f"{API_PREFIX}{template}"][op.method.lower()]

    declared = {
        status: response
        for status, response in operation_spec["responses"].items()
        # 422 is FastAPI's own validation error, which is structured per-field and
        # deliberately not flattened into ErrorResponse.
        if status.startswith(("4", "5")) and status != "422"
    }
    assert declared, f"{name}: no error responses declared"

    for status, response in declared.items():
        schema = response["content"]["application/json"]["schema"]
        assert schema.get("$ref", "").endswith("/ErrorResponse"), (
            f"{name}: {status} declares {schema}, expected a ref to ErrorResponse"
        )


def test_path_parameters_are_escaped() -> None:
    """
    Ids are URL-escaped when interpolated into a path.

    An id containing a slash would otherwise address a different endpoint
    entirely, and ids reach this client from CLI arguments and from APIServer
    route parameters, not only from the service.
    """
    op = ops.get_run("../../etc/passwd")
    assert op.path == "/runs/..%2F..%2Fetc%2Fpasswd"
    assert not re.search(r"/runs/.*/", op.path)

    op = ops.get_task("a/b", "c?d")
    assert op.path == "/runs/a%2Fb/tasks/c%3Fd"


def test_client_version_matches_its_distribution() -> None:
    """
    The reported version is the installed one, not a hardcoded literal.

    A hardcoded __version__ drifts from pyproject.toml at the first release that
    forgets to update both, and the wrong value then goes out in the User-Agent
    on every request -- the one place this is visible when debugging production.
    """
    from importlib.metadata import version

    import wes_client

    assert wes_client.__version__ == version("wes-client")


def test_client_reexports_resolve_against_the_installed_schemas() -> None:
    """
    Every name wes_client re-exports actually exists in the wes-schemas it has.

    Guards the failure mode that a stale wes-schemas satisfied wes-client's
    dependency: the symbol was missing from the installed build, and the only
    symptom was an ImportError when the CLI started. Importing the package here
    is not enough on its own -- __all__ can name things the module never bound --
    so each name is looked up.
    """
    import wes_client

    missing = [name for name in wes_client.__all__ if not hasattr(wes_client, name)]
    assert not missing, f"wes_client.__all__ names symbols it does not export: {missing}"
