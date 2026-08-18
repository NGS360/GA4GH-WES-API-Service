"""Internal callback endpoints."""

import logging

from fastapi import APIRouter, status

from wes_service.api.deps import DatabaseSession
from wes_service.api.routes._responses import BAD_REQUEST, DISABLED, ERRORS, NOT_FOUND
from wes_service.core.callback_auth import CallbackAuth, CallbackOrServiceAuth
from wes_schemas.callback import (
    CallbackResponse,
    ExecutorStateChangeCallback,
    OmicsStateChangeCallback,
)
from wes_service.services.callback_service import CallbackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/callbacks", tags=["Internal Callbacks"])


@router.post(
    "/omics-state-change",
    response_model=CallbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Handle AWS HealthOmics state change",
    description="""
    Internal endpoint for AWS Lambda to report HealthOmics workflow state changes.

    This endpoint is NOT part of the GA4GH WES API specification.
    It is a custom extension for event-driven state updates.

    **Authentication**: Requires X-Internal-API-Key header.

    **Source**: Called by Lambda function in response to EventBridge notifications.
    """,
)
async def handle_omics_state_change(
    payload: OmicsStateChangeCallback,
    db: DatabaseSession,
    _auth: CallbackAuth,  # Validates API key
) -> CallbackResponse:
    """
    Handle AWS HealthOmics state change callback.

    This endpoint is called by a Lambda function when EventBridge receives
    a state change notification from AWS HealthOmics.

    Args:
        payload: State change information
        db: Database session
        _auth: Authentication (validated by dependency)

    Returns:
        CallbackResponse with update details
    """
    logger.info(
        f"Received Omics state change callback for run {payload.wes_run_id}"
    )

    service = CallbackService(db)
    response = await service.handle_omics_state_change(payload)

    return response


@router.post(
    "/executor-state-change",
    response_model=CallbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Handle an executor state change",
    description="""
    Internal endpoint for reporting a run's state from its execution backend.

    This endpoint is NOT part of the GA4GH WES API specification.
    It is a custom extension for event-driven state updates, and the
    executor-agnostic form of /omics-state-change: `executor` selects the status
    vocabulary, so AWS Batch launcher jobs and HealthOmics runs share one path.

    **Authentication**: Requires either X-Internal-API-Key (the relay Lambda) or
    X-Internal-Service-Key (NGS360 APIServer, which submits launcher jobs and so
    is what reports a job ID binding or a submission failure).

    **Source**: Called by the Lambda reacting to EventBridge Batch job state
    changes, and by whichever service submitted the job.
    """,
    responses=ERRORS | {400: BAD_REQUEST, 404: NOT_FOUND, 503: DISABLED},
)
async def handle_executor_state_change(
    payload: ExecutorStateChangeCallback,
    db: DatabaseSession,
    _auth: CallbackOrServiceAuth,  # Validates either internal key
) -> CallbackResponse:
    """
    Handle a state change reported by an execution backend.

    Args:
        payload: State change information, including which executor sent it
        db: Database session
        _auth: Authentication (validated by dependency)

    Returns:
        CallbackResponse with update details
    """
    logger.info(
        f"Received {payload.executor} state change callback "
        f"for run {payload.wes_run_id}"
    )

    service = CallbackService(db)
    return await service.handle_executor_state_change(payload)


@router.get(
    "/health",
    summary="Callback endpoint health check",
    description="Health check for callback endpoint availability",
)
async def callback_health() -> dict[str, str]:
    """Health check for callback endpoints."""
    return {"status": "healthy", "endpoint": "callbacks"}
