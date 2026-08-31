"""Callback schemas for internal endpoints."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class OmicsRunStatus(str, Enum):
    """Valid AWS HealthOmics run statuses."""
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    CANCELLED_RUNNING = "CANCELLED_RUNNING"
    CANCELLED_STARTING = "CANCELLED_STARTING"
    RUNNING = "RUNNING"
    STARTING = "STARTING"
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    STOPPING = "STOPPING"
    TERMINATING = "TERMINATING"


class OmicsStateChangeCallback(BaseModel):
    """Schema for AWS HealthOmics state change callback.

    This is called by Lambda functions in response to EventBridge
    notifications from AWS HealthOmics.
    """

    omics_run_id: Optional[str] = Field(
        None,
        description="AWS HealthOmics run ID",
        min_length=1,
        max_length=50,
    )

    status: OmicsRunStatus = Field(
        ...,
        description="Current HealthOmics run status"
    )

    wes_run_id: str = Field(
        ...,
        description="GA4GH WES run ID to update",
        min_length=36,
        max_length=36,
    )

    event_time: datetime = Field(
        ...,
        description="Timestamp of the state change event from EventBridge",
    )

    status_message: Optional[str] = Field(
        None,
        description="Additional status information from HealthOmics",
        max_length=1000,
    )

    failure_reason: Optional[str] = Field(
        None,
        description="Failure reason if status indicates failure",
        max_length=2000,
    )

    output_mapping: Optional[dict[str, Any]] = Field(
        None,
        description="Workflow outputs if status is COMPLETED",
    )

    event_id: Optional[str] = Field(
        None,
        description="EventBridge event ID for idempotency",
        min_length=1,
        max_length=100,
    )

    log_urls: Optional[dict[str, Any]] = Field(
        None,
        description="URLs to access workflow logs",
    )


class ExecutorStateChangeCallback(BaseModel):
    """Schema for a state change reported by any execution backend.

    The executor-agnostic form of OmicsStateChangeCallback: `executor` selects
    the status vocabulary to translate from, so one endpoint serves AWS Batch
    launcher jobs and HealthOmics runs alike. `status` is left as a string
    rather than an enum for that reason -- an unknown status is rejected by the
    service with the list of statuses that executor does accept.
    """

    wes_run_id: str = Field(
        ...,
        description="GA4GH WES run ID to update",
        min_length=1,
        max_length=36,
    )

    executor: str = Field(
        ...,
        description='The execution backend reporting the change, e.g. "awsbatch" or "omics"',
        min_length=1,
        max_length=50,
    )

    status: str = Field(
        ...,
        description="The executor's own status name, e.g. RUNNABLE for AWS Batch",
        min_length=1,
        max_length=50,
    )

    executor_run_id: Optional[str] = Field(
        None,
        description=(
            "The run's ID in the execution backend, e.g. an AWS Batch jobId. "
            "Recorded on the run the first time it is reported"
        ),
        min_length=1,
        max_length=50,
    )

    event_time: datetime = Field(
        ...,
        description="Timestamp of the state change event",
    )

    status_message: Optional[str] = Field(
        None,
        description="Additional status information from the executor",
        max_length=1000,
    )

    failure_reason: Optional[str] = Field(
        None,
        description="Failure reason if the status indicates failure",
        max_length=2000,
    )

    exit_code: Optional[int] = Field(
        None,
        description="Exit code of the executor's container, if it ran",
    )

    event_id: Optional[str] = Field(
        None,
        description="Event source's event ID, for idempotency",
        min_length=1,
        max_length=100,
    )

    log_urls: Optional[dict[str, Any]] = Field(
        None,
        description=(
            'URLs and identifiers for the run\'s logs. A "log_stream_name" key is '
            "turned into a console link and kept verbatim for log viewers"
        ),
    )


class CallbackResponse(BaseModel):
    """Response from callback endpoint."""

    success: bool = Field(..., description="Whether the callback was processed successfully")
    wes_run_id: str = Field(..., description="WES run ID that was updated")
    previous_state: str = Field(..., description="Previous workflow state")
    new_state: str = Field(..., description="New workflow state after callback")
    message: str = Field(..., description="Human-readable message about the update")
    already_processed: bool = Field(
        default=False,
        description="True if this event was already processed (idempotency check)",
    )
