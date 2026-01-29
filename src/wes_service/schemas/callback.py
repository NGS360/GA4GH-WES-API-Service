"""Callback schemas for internal endpoints."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class OmicsStateChangeCallback(BaseModel):
    """Schema for AWS HealthOmics state change callback.
    
    This is called by Lambda functions in response to EventBridge
    notifications from AWS HealthOmics.
    """
    
    omics_run_id: str = Field(
        ...,
        description="AWS HealthOmics run ID",
        min_length=1,
        max_length=50,
    )
    
    status: str = Field(
        ...,
        description="Current HealthOmics run status",
        pattern="^(COMPLETED|FAILED|CANCELLED|CANCELLED_RUNNING|CANCELLED_STARTING|RUNNING|STARTING|PENDING|QUEUED|STOPPING|TERMINATING)$",
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
    
    event_id: str = Field(
        ...,
        description="EventBridge event ID for idempotency",
        min_length=1,
        max_length=100,
    )

    log_urls: Optional[dict[str, Any]] = Field(
        None,
        description="URLs to access workflow logs",
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
