"""Internal callback endpoints."""

import logging

from fastapi import APIRouter, status

from src.wes_service.api.deps import DatabaseSession
from src.wes_service.core.callback_auth import CallbackAuth
from src.wes_service.schemas.callback import CallbackResponse, OmicsStateChangeCallback
from src.wes_service.services.callback_service import CallbackService

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


@router.get(
    "/health",
    summary="Callback endpoint health check",
    description="Health check for callback endpoint availability",
)
async def callback_health() -> dict[str, str]:
    """Health check for callback endpoints."""
    return {"status": "healthy", "endpoint": "callbacks"}
