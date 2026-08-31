"""
Client library for the GA4GH Workflow Execution Service.

Import a client, give it a base URL and a credential, call methods:

    from wes_client import AsyncWesClient, ServiceKeyAuth

    client = AsyncWesClient("http://wes:8000", auth=ServiceKeyAuth(key))
    runs = await client.on_behalf_of(username).list_runs(project="P-123", page_size=10)

The wire schemas are re-exported here so a consumer needs one dependency and one
import root. They are the same class objects the server declares as its response
models -- not copies generated from a spec -- so ``run.state`` type-checks
identically on both sides of the call and a contract change is a type error
rather than a runtime surprise.
"""

from wes_schemas import (
    TERMINAL_STATES,
    CallbackResponse,
    DefaultWorkflowEngineParameter,
    ErrorResponse,
    Log,
    RunId,
    RunListResponse,
    RunLog,
    RunProgress,
    RunRequest,
    RunStatus,
    RunSummary,
    ServiceInfo,
    State,
    TaskListResponse,
    TaskLog,
    WorkflowEngineVersion,
    WorkflowTypeVersion,
)
from wes_client._transport import API_PREFIX
from wes_client.auth import BasicAuth, BearerAuth, ServiceKeyAuth
from wes_client.client import AsyncWesClient
from wes_client.errors import (
    WesAuthError,
    WesBadRequest,
    WesError,
    WesNotFound,
    WesProtocolError,
    WesResponseError,
    WesServerError,
    WesTimeout,
    WesUnavailable,
)
from wes_client._version import __version__
from wes_client.sync_client import WesClient

__all__ = [
    "API_PREFIX",
    "__version__",
    # Clients
    "AsyncWesClient",
    "WesClient",
    # Auth
    "BasicAuth",
    "BearerAuth",
    "ServiceKeyAuth",
    # Errors
    "WesError",
    "WesTimeout",
    "WesUnavailable",
    "WesProtocolError",
    "WesResponseError",
    "WesAuthError",
    "WesNotFound",
    "WesBadRequest",
    "WesServerError",
    # Schemas
    "TERMINAL_STATES",
    "CallbackResponse",
    "DefaultWorkflowEngineParameter",
    "ErrorResponse",
    "Log",
    "RunId",
    "RunListResponse",
    "RunLog",
    "RunProgress",
    "RunRequest",
    "RunStatus",
    "RunSummary",
    "ServiceInfo",
    "State",
    "TaskListResponse",
    "TaskLog",
    "WorkflowEngineVersion",
    "WorkflowTypeVersion",
]
