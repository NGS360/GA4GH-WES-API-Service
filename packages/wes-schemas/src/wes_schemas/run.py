"""Run-related schemas."""

from typing import Any

from pydantic import BaseModel, Field

from wes_schemas.common import State


class RunId(BaseModel):
    """Workflow run ID response."""

    run_id: str = Field(..., description="Workflow run ID")


class RunStatus(BaseModel):
    """State information of a workflow run."""

    run_id: str = Field(..., description="Workflow run ID")
    state: State | None = Field(None, description="Current workflow state")


class RunSummary(RunStatus):
    """Small description of a workflow run."""

    start_time: str | None = Field(
        None,
        description='When the run started, in ISO 8601 format "%Y-%m-%dT%H:%M:%SZ"',
    )
    end_time: str | None = Field(
        None,
        description='When the run stopped, in ISO 8601 format "%Y-%m-%dT%H:%M:%SZ"',
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary key/value tags added by the client",
    )
    name: str | None = Field(
        None,
        description="Caller-supplied label for the run, from the TaskName tag",
    )
    project: str | None = Field(
        None,
        description="Project this run belongs to, from the required ProjectId tag",
    )
    workflow_url: str | None = Field(
        None,
        description=(
            "The workflow this run executed, as NGS360WORKFLOWID[:ALIAS_OR_VERSION]. "
            "The optional suffix carries the pipeline version; note that "
            "workflow_type_version is the CWL/WDL descriptor version instead"
        ),
    )
    submitted_by: str | None = Field(
        None,
        description="User who submitted the run",
    )
    parent_run_id: str | None = Field(
        None,
        description=(
            "The launcher run that submitted this run, from the ParentRunId tag. "
            "None for runs submitted directly"
        ),
    )


class RunRequest(BaseModel):
    """Workflow run request."""

    workflow_params: dict[str, Any] | None = Field(
        None,
        description="The workflow run parameterizations (JSON encoded)",
    )
    workflow_type: str = Field(
        ...,
        description='The workflow descriptor type, must be "CWL" or "WDL"',
    )
    workflow_type_version: str = Field(
        ...,
        description="The workflow descriptor type version",
    )
    tags: dict[str, str] | None = Field(
        None,
        description="Arbitrary key/value tags",
    )
    workflow_engine_parameters: dict[str, str] | None = Field(
        None,
        description="Additional parameters for the workflow engine",
    )
    workflow_engine: str | None = Field(
        None,
        description="The workflow engine (required if engine_version provided)",
    )
    workflow_engine_version: str | None = Field(
        None,
        description="The workflow engine version",
    )
    workflow_url: str = Field(
        ...,
        description="The workflow CWL or WDL document URL",
    )


class Log(BaseModel):
    """Log and other info."""

    name: str | None = Field(None, description="The task or workflow name")
    cmd: list[str] | None = Field(
        None,
        description="The command line that was executed",
    )
    start_time: str | None = Field(
        None,
        description='When the command started, in ISO 8601 format',
    )
    end_time: str | None = Field(
        None,
        description='When the command stopped, in ISO 8601 format',
    )
    stdout: str | None = Field(
        None,
        description="A URL to retrieve standard output logs",
    )
    stderr: str | None = Field(
        None,
        description="A URL to retrieve standard error logs",
    )
    exit_code: int | None = Field(
        None,
        description="Exit code of the program",
    )
    system_logs: list[str] | None = Field(
        None,
        description="System logs relevant to the workflow",
    )


class RunLog(BaseModel):
    """Complete log of a workflow run."""

    run_id: str = Field(..., description="Workflow run ID")
    request: RunRequest = Field(..., description="Original run request")
    state: State | None = Field(None, description="Current workflow state")
    name: str | None = Field(
        None,
        description="Caller-supplied label for the run, from the TaskName tag",
    )
    run_log: Log | None = Field(None, description="Overall workflow log")
    task_logs_url: str | None = Field(
        None,
        description="URL to obtain paginated list of task logs",
    )
    task_logs: list[Any] | None = Field(
        None,
        deprecated=True,
        description="Deprecated: Use task_logs_url instead",
    )
    outputs: dict[str, Any] | None = Field(
        None,
        description="The outputs from the workflow run",
    )
    parent_run_id: str | None = Field(
        None,
        description=(
            "The launcher run that submitted this run, from the ParentRunId tag. "
            "None for runs submitted directly"
        ),
    )


class RunProgress(BaseModel):
    """
    Progress of a launcher run, rolled up from the runs it submitted.

    The launcher's own `state` is its process lifecycle and is deliberately kept
    separate from the child counts: a launcher that dies while its children keep
    running reports a failed state alongside children still RUNNING, which is
    the orphan condition an operator needs to see rather than have smoothed over.
    """

    run_id: str = Field(..., description="The launcher run ID")
    state: State | None = Field(
        None,
        description="The launcher run's own state, not an aggregate of its children",
    )
    children_total: int = Field(
        0,
        description="Number of runs submitted by this run (direct children only)",
    )
    children_by_state: dict[str, int] = Field(
        default_factory=dict,
        description="Child run counts keyed by state, including states with a count of zero",
    )
    children_last_update: str | None = Field(
        None,
        description=(
            "The most recent child update time, in ISO 8601 format. "
            "None when there are no children"
        ),
    )


class RunListResponse(BaseModel):
    """Response for listing workflow runs."""

    runs: list[RunSummary] = Field(
        default_factory=list,
        description="List of workflow runs",
    )
    next_page_token: str | None = Field(
        None,
        description="Token for next page of results (empty if no more items)",
    )
    total_count: int | None = Field(
        None,
        description=(
            "Total runs matching the request's filters, ignoring pagination. "
            "Lets a client compute a page count instead of walking every page"
        ),
    )
